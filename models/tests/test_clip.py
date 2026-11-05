import json

import numpy as np
import pytest

from clip_search import coco
from clip_search.backends import load_backend, normalize
from clip_search.es_export import export, mapping
from clip_search.evaluate import build_queries, evaluate_backend, write_results
from clip_search.index import ImageIndex, embed_paths
from clip_search.labels_nl import COCO_LABELS, FALSE_FRIENDS

Image = pytest.importorskip("PIL.Image")

OFFICIAL_COCO_80 = """person,bicycle,car,motorcycle,airplane,bus,train,truck,boat,traffic light,
fire hydrant,stop sign,parking meter,bench,bird,cat,dog,horse,sheep,cow,elephant,bear,zebra,giraffe,
backpack,umbrella,handbag,tie,suitcase,frisbee,skis,snowboard,sports ball,kite,baseball bat,
baseball glove,skateboard,surfboard,tennis racket,bottle,wine glass,cup,fork,knife,spoon,bowl,
banana,apple,sandwich,orange,broccoli,carrot,hot dog,pizza,donut,cake,chair,couch,potted plant,
bed,dining table,toilet,tv,laptop,mouse,remote,keyboard,cell phone,microwave,oven,toaster,sink,
refrigerator,book,clock,vase,scissors,teddy bear,hair drier,toothbrush"""


def official_names():
    return [name.strip() for name in OFFICIAL_COCO_80.replace("\n", "").split(",")]


def test_label_table_covers_exactly_the_coco_categories():
    assert set(COCO_LABELS) == set(official_names())
    assert len(COCO_LABELS) == 80
    assert all(en and nl for en, nl in COCO_LABELS.values())
    assert set(FALSE_FRIENDS.values()) <= set(COCO_LABELS)


def test_queries_use_the_right_language():
    assert build_queries("nl", ["dog"]) == ["een foto van een hond"]
    assert build_queries("en", ["dog"], template=False) == ["a dog"]


class ColorBackend:
    """Fake encoder that knows colour, and English only: enough to verify the experiment logic."""

    name = "fake-color"
    COLORS = {"dog": 0, "cat": 1, "bus": 2}

    def encode_images(self, images):
        return normalize(np.array([np.asarray(i, dtype=float).mean(axis=(0, 1)) for i in images])
                         + 1e-3)

    def encode_texts(self, texts):
        vectors = []
        for text in texts:
            vector = np.full(3, 0.1)
            for word, channel in self.COLORS.items():
                if word in text:
                    vector[channel] = 1.0
            vectors.append(vector)
        return normalize(np.array(vectors))


@pytest.fixture
def images(tmp_path):
    paths, labels = [], []
    rng = np.random.default_rng(0)
    for index in range(30):
        channel = index % 3
        pixels = rng.integers(0, 40, (24, 24, 3), dtype=np.uint8)
        pixels[:, :, channel] = 220
        path = tmp_path / f"{index}.png"
        Image.fromarray(pixels).save(path)
        paths.append(str(path))
        labels.append(channel)
    labels = np.array(labels)
    relevance = {"dog": labels == 0, "cat": labels == 1, "bus": labels == 2}
    return paths, relevance


def test_experiment_finds_a_planted_language_gap(images, tmp_path):
    paths, relevance = images
    backend = ColorBackend()
    vectors = embed_paths(backend, paths, batch_size=7)
    result = evaluate_backend(backend, paths, vectors, relevance, robustness_sample=12)
    table = {row["queries"]: row for row in result["language"]["table"]}
    assert table["en/template"]["map"] == 1.0
    assert table["nl/template"]["map"] < table["en/template"]["map"]
    assert result["language"]["en_minus_nl"]["difference"] > 0
    assert len(result["robustness"]) == 5
    report = write_results([result], tmp_path / "out", provenance="smoke", images=len(paths))
    assert report["meta"]["provenance"] == "smoke"
    assert (tmp_path / "out" / "report.md").exists()


def test_index_round_trip_and_search(tmp_path):
    vectors = normalize(np.eye(3))
    index = ImageIndex(vectors, ["a", "b", "c"])
    index.save(tmp_path)
    loaded = ImageIndex.load(tmp_path)
    assert loaded.search(np.array([0, 1.0, 0]), k=1)[0][0] == "b"


def test_es_bulk_export_is_valid_ndjson(tmp_path):
    index = ImageIndex(normalize(np.eye(2)), ["a.jpg", "b.jpg"])
    out = tmp_path / "bulk.ndjson"
    assert export(index, out) == 2
    lines = [json.loads(line) for line in out.read_text().splitlines()]
    assert lines[0]["index"]["_id"] == "a.jpg" and len(lines[1]["embedding"]) == 2
    assert mapping(2)["mappings"]["properties"]["embedding"]["dims"] == 2


def test_coco_annotation_parsing(tmp_path):
    path = tmp_path / "a.json"
    path.write_text(json.dumps({
        "images": [{"id": 9, "file_name": "b.jpg"}, {"id": 3, "file_name": "a.jpg"}],
        "categories": [{"id": 1, "name": "dog"}, {"id": 2, "name": "cat"}],
        "annotations": [{"image_id": 3, "category_id": 2}, {"image_id": 9, "category_id": 1},
                        {"image_id": 3, "category_id": 2}],
    }))
    names, relevance, ids = coco.load_annotations(path)
    assert names == ["a.jpg", "b.jpg"] and ids == [3, 9]
    assert relevance["cat"].tolist() == [True, False] and relevance["dog"].tolist() == [False, True]


def test_cli_end_to_end_with_coco_layout(images, tmp_path, monkeypatch):
    import sys

    from clip_search import cli

    paths, relevance = images
    coco_dir = tmp_path / "coco"
    (coco_dir / "annotations").mkdir(parents=True)
    (coco_dir / "val2017").mkdir()
    records, annotations = [], []
    categories = {"dog": 1, "cat": 2, "bus": 3}
    for index, path in enumerate(paths):
        name = f"{index}.png"
        (coco_dir / "val2017" / name).write_bytes(open(path, "rb").read())
        records.append({"id": index, "file_name": name})
        for category, category_id in categories.items():
            if relevance[category][index]:
                annotations.append({"image_id": index, "category_id": category_id})
    (coco_dir / "annotations" / "instances_val2017.json").write_text(json.dumps({
        "images": records, "annotations": annotations,
        "categories": [{"id": i, "name": n} for n, i in categories.items()],
    }))
    monkeypatch.setattr(cli, "load_backend", lambda spec: ColorBackend())
    out = tmp_path / "out"
    argv = ["cli", "--coco", str(coco_dir), "--out", str(out), "--model", "hf:fake",
            "--robustness-sample", "10"]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    assert "real" in (out / "report.json").read_text()
    assert (out / "index" / "hf_fake" / "embeddings.npy").exists()
    cli.main()  # the second run reuses the saved embeddings


def test_unknown_backend_spec():
    with pytest.raises(ValueError):
        load_backend("nope:x")


def test_gallery_search_ignores_blank_query(tmp_path):
    from clip_search.app import search_gallery

    backend = ColorBackend()
    index = ImageIndex(normalize(np.eye(3)), ["d.jpg", "c.jpg", "b.jpg"])
    assert search_gallery("   ", backend, index, tmp_path) == []
    assert search_gallery("dog", backend, index, tmp_path, k=1)[0][0].endswith("d.jpg")


@pytest.mark.torch
def test_real_clip_architecture_on_tiny_random_weights(images, tmp_path):
    pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    from clip_search.backends import HFClip

    vocab = {"<|startoftext|>": 0, "<|endoftext|>": 1, "a</w>": 2, "dog</w>": 3, "hond</w>": 4}
    (tmp_path / "v.json").write_text(json.dumps(vocab))
    (tmp_path / "m.txt").write_text("#version: 0.2\n")
    tokenizer = transformers.CLIPTokenizer(str(tmp_path / "v.json"), str(tmp_path / "m.txt"))
    config = transformers.CLIPConfig(
        text_config={"vocab_size": 10, "hidden_size": 16, "intermediate_size": 16,
                     "num_hidden_layers": 1, "num_attention_heads": 2,
                     "max_position_embeddings": 16},
        vision_config={"hidden_size": 16, "intermediate_size": 16, "num_hidden_layers": 1,
                       "num_attention_heads": 2, "image_size": 32, "patch_size": 16},
        projection_dim=8,
    )
    processor = transformers.CLIPProcessor(
        transformers.CLIPImageProcessor(size={"shortest_edge": 32},
                                        crop_size={"height": 32, "width": 32}),
        tokenizer,
    )
    backend = HFClip("tiny", device="cpu", model=transformers.CLIPModel(config),
                     processor=processor)
    vectors = embed_paths(backend, images[0][:4], batch_size=2)
    assert vectors.shape == (4, 8)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
    text = backend.encode_texts(["a dog", "a hond"])
    assert text.shape == (2, 8)
