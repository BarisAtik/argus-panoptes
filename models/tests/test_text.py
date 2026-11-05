import json

import numpy as np
import pytest

from text_nl import audit, behaviour, perturb
from text_nl.data import Split, load_jsonl
from text_nl.evaluate import compare, evaluate_model, f1_macro

GOOD = ["prachtig", "mooi", "spannend", "ontroerend", "geweldig", "boeiend", "knap", "sterk"]
BAD = ["saai", "slecht", "waardeloos", "vervelend", "rommelig", "flauw", "zwak", "matig"]
FILLER = ("dit boek las ik in de zomer en de schrijver vertelt over een gezin dat verhuist naar "
          "een dorp aan de kust waar veel gebeurt").split()


def toy_split(n=400, seed=0):
    rng = np.random.default_rng(seed)
    texts, labels = [], []
    for _ in range(n):
        label = int(rng.integers(2))
        words = list(rng.choice(FILLER, 25)) + list(rng.choice(GOOD if label else BAD, 3))
        rng.shuffle(words)
        texts.append(" ".join(words))
        labels.append(label)
    return Split(texts, labels)


def test_canonical_ignores_case_and_punctuation():
    assert audit.canonical("Geweldig, écht!") == audit.canonical("geweldig écht")


def test_language_guess():
    assert audit.language_guess("Ik vond dit boek niet zo goed want het was erg lang") == "nl"
    assert audit.language_guess("I think that this is one of the best in the world") == "en"
    assert audit.language_guess("kort") == "unclear"


def test_near_duplicates_found_and_unrelated_not():
    base = " ".join(f"woord{i}" for i in range(60))
    edited = base.replace("woord30", "anders")
    other = " ".join(f"ander{i}" for i in range(60))
    assert audit.near_duplicate_pairs([base, other, edited]) == [(0, 2)]


def test_duplicate_groups_chain_exact_and_near():
    base = " ".join(f"w{i}" for i in range(50))
    groups = audit.duplicate_groups([base, base.upper(), base + " extra", "iets heel anders dan"])
    assert groups[0] == groups[1] == groups[2] != groups[3]


def test_group_split_keeps_duplicates_together_and_stratifies():
    labels = [0, 1] * 500
    groups = np.repeat(np.arange(250), 4)
    fit, val = audit.group_split(labels, groups, 0.2, seed=0)
    assert set(groups[fit]).isdisjoint(set(groups[val]))
    assert len(fit) + len(val) == 1000
    assert 0.15 < len(val) / 1000 < 0.25
    share = np.mean([labels[i] for i in val])
    assert 0.4 < share < 0.6


def test_length_only_accuracy_spots_a_length_leak():
    long_pos = ["x " * 50] * 50 + ["y"] * 50
    assert audit.length_only_accuracy(long_pos, [1] * 50 + [0] * 50) == 1.0
    assert audit.length_only_accuracy(long_pos, [0] * 50 + [1] * 50) == 1.0


def test_audit_counts_leak_conflicts_and_url():
    train = Split(["goed boek hoor", "slecht boek hoor", "zie www.winkel.nl voor meer"], [1, 0, 1])
    test = Split(["Goed boek, hoor!", "totaal nieuw verhaal over iets"], [0, 1])
    report = audit.audit_splits(train, test, shingle=1)
    assert report["test_texts_also_in_train"] == 1
    assert report["_test_leaked"] == [0]
    assert report["groups_with_conflicting_labels"] == 1
    assert report["contains_url"] == 1


def test_typo_changes_one_word_shape_only_and_is_reproducible():
    text = "dit is een fantastisch geschreven verhaal over iets wonderlijks"
    typo = perturb.typos(text, rate=1.0, seed=3)
    assert typo != text and len(typo) == len(text)
    assert sorted(typo.replace(" ", "")) == sorted(text.replace(" ", ""))
    assert typo == perturb.typos(text, rate=1.0, seed=3)


def test_challenge_set_is_well_formed():
    items = behaviour.load_challenge()
    assert len(items) >= 80
    assert len({i["id"] for i in items}) == len(items)
    assert {i["label"] for i in items} == {0, 1}
    assert len({i["text"] for i in items}) == len(items)
    tests = {i["test"] for i in items}
    assert {"negation_of_positive", "sarcasm", "flemish_usage"} <= tests


def test_run_challenge_scores_a_keyword_model():
    items = [{"text": "goed", "test": "t", "label": 1}, {"text": "slecht", "test": "t", "label": 1}]
    predict = lambda ts: np.array([[0, 1] if "goed" in t else [1, 0] for t in ts])  # noqa: E731
    result = behaviour.run_challenge(predict, items)
    assert result["by_test"][0]["pass_rate"] == 0.5
    assert result["failures"][0]["text"] == "slecht"


def test_f1_macro():
    assert f1_macro(np.array([0, 0, 1, 1]), np.array([0, 0, 1, 1])) == 1
    assert f1_macro(np.array([0, 0, 1, 1]), np.array([0, 1, 1, 1])) == pytest.approx(
        (2 / 3 + 0.8) / 2
    )


def test_evaluate_model_flags_leak_row():
    split = toy_split(60)
    y = np.array(split.labels)
    logits = np.column_stack([1.0 - y, y.astype(float)]) * 2

    def predict(texts):
        return np.tile([0.2, 0.8], (len(texts), 1))

    result = evaluate_model("m", split.texts, split.labels, logits, logits, split.labels, predict,
                            leaked={0, 1})
    subsets = {row["subset"] for row in result["slices"]}
    assert "test texts NOT in train (the honest number)" in subsets
    assert result["accuracy"]["accuracy"] == 1
    assert compare([result, result])[0]["p_value"] == 1.0


def test_baseline_learns_and_probe_finds_flipped_labels():
    from text_nl import baseline

    split = toy_split(300)
    labels = list(split.labels)
    flipped = [0, 1, 2, 3, 4]
    for i in flipped:
        labels[i] = 1 - labels[i]
    probabilities = baseline.out_of_fold_probabilities(split.texts, labels,
                                                       np.arange(len(labels)))
    suspects = baseline.suspicious_labels(split.texts, labels, probabilities, top=10)
    assert len({s["index"] for s in suspects} & set(flipped)) >= 4


def test_baseline_only_experiment_writes_smoke_report(tmp_path):
    from text_nl.cli import run_experiment

    report = run_experiment(toy_split(300), toy_split(100, seed=1), tmp_path, provenance="smoke")
    assert report["models"][0]["accuracy"]["accuracy"] > 0.8
    assert (tmp_path / "report.md").read_text().startswith("> **SMOKE")
    assert json.loads((tmp_path / "suspicious_labels.json").read_text())


def test_load_jsonl(tmp_path):
    path = tmp_path / "x.jsonl"
    path.write_text('{"text": "a", "label": 1}\n', encoding="utf-8")
    assert load_jsonl(path).labels == [1]


def tiny_bert(tmp_path):
    transformers = pytest.importorskip("transformers")
    vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", *GOOD, *BAD, *sorted(set(FILLER))]
    vocab_file = tmp_path / "vocab.txt"
    vocab_file.write_text("\n".join(vocab), encoding="utf-8")
    tokenizer = transformers.BertTokenizer(str(vocab_file), do_lower_case=True)
    config = transformers.BertConfig(
        vocab_size=len(vocab), hidden_size=32, num_hidden_layers=1, num_attention_heads=2,
        intermediate_size=32, max_position_embeddings=64, num_labels=2,
    )
    return transformers.BertForSequenceClassification(config), tokenizer


@pytest.mark.torch
def test_head_tail_truncation_keeps_both_ends(tmp_path):
    pytest.importorskip("torch")
    from text_nl.train import encode

    _, tokenizer = tiny_bert(tmp_path)
    text = "prachtig " + "boek " * 40 + "saai"
    ids = encode(tokenizer, [text], 16, "head_tail")["input_ids"][0]
    assert len(ids) == 16
    decoded = tokenizer.decode(ids, skip_special_tokens=True)
    assert decoded.startswith("prachtig") and decoded.endswith("saai")
    head = encode(tokenizer, [text], 16, "head")["input_ids"][0]
    assert "saai" not in tokenizer.decode(head)
    with pytest.raises(ValueError):
        encode(tokenizer, [text], 16, "middle")


@pytest.mark.torch
def test_real_training_loop_learns_on_tiny_random_bert(tmp_path):
    pytest.importorskip("torch")
    from text_nl.cli import run_experiment
    from text_nl.train import TrainConfig

    model, tokenizer = tiny_bert(tmp_path)
    config = TrainConfig(model="tiny-random-bert", max_length=48, batch_size=16, lr=3e-3,
                         epochs=4, device="cpu", patience=3)
    report = run_experiment(toy_split(300), toy_split(100, seed=1), tmp_path / "run",
                            provenance="smoke", model_config=config, hf_model=model,
                            hf_tokenizer=tokenizer)
    accuracy = report["models"][1]["accuracy"]["accuracy"]
    assert accuracy > 0.8, "a planted-keyword task must be learnable"
    assert report["comparisons"][0]["a"] == "tfidf-logreg"
    assert (tmp_path / "run" / "checkpoint" / "train_history.json").exists()
