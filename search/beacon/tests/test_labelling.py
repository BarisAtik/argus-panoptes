import tarfile

import pytest

from beacon.evaluate import pool
from beacon.labelling import label_pool
from beacon.model_fetch import FILES, extract, sha256
from beacon.models import Document, read_jsonl


def test_pool_is_a_union_ordered_by_best_rank():
    rankings = {"a": ["x", "y", "z"], "b": ["y", "w"]}
    assert pool(rankings, depth=2) == ["x", "y", "w"]


ROW = {"id": "q1", "query": "vraag", "kind": "k", "pool": ["d1", "d2", "d3"]}
DOCS = {name: Document(name, f"titel {name}") for name in ROW["pool"]}


def test_labels_are_saved_and_a_session_resumes(tmp_path):
    out = tmp_path / "labels.jsonl"
    answers = iter(["2", "bad", "q"])
    added = label_pool([ROW], DOCS, out, ask=lambda _: next(answers), show=lambda _: None)
    assert added == 1
    saved = next(read_jsonl(out))
    assert saved["relevant"] == {"d1": 2}

    answers = iter(["0", "1"])
    added = label_pool([ROW], DOCS, out, ask=lambda _: next(answers), show=lambda _: None)
    assert added == 2
    saved = next(read_jsonl(out))
    assert saved["relevant"] == {"d1": 2, "d3": 1}
    assert saved["judged"] == ["d1", "d2", "d3"]


def test_extract_rejects_a_changed_file(tmp_path):
    source = tmp_path / "source"
    (source / "package").mkdir(parents=True)
    for name in FILES:
        (source / "package" / name).write_bytes(b"tampered")
    tarball = tmp_path / "m.tgz"
    with tarfile.open(tarball, "w:gz") as archive:
        archive.add(source / "package", arcname="package")
    with pytest.raises(ValueError, match="hash mismatch"):
        extract(tarball, tmp_path / "out")
    assert not list((tmp_path / "out").glob("*.onnx"))


def test_sha256_of_a_known_value(tmp_path):
    path = tmp_path / "x"
    path.write_bytes(b"abc")
    assert sha256(path).startswith("ba7816bf")
