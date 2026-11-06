import itertools
import math
import random

import numpy as np
import pytest

from ner_nl import audit, perturb
from ner_nl.backends import Gazetteer
from ner_nl.data import Sentence, load_split, parse_conll2002
from ner_nl.label_map import SPACY_TO_CONLL
from ner_nl.metrics import entity_ece, missed_tokens, paired_f1_difference, recall_by_seen
from ner_nl.names import NAMES, swap_names
from ner_nl.spans import ALL_LABELS, bio_spans, count_by_doc, f1_interval, prf, spans_to_bio

SAMPLE = """-DOCSTART- -DOCSTART- O
De Art O
Jan N B-PER
Peeters N I-PER
woont V O
in Prep O
Gent N B-LOC
. Punc O

Hij Pron O
lacht V O

-DOCSTART- -DOCSTART- O
KU N B-ORG
Leuven N I-ORG
wint V O
"""


def sentences():
    return parse_conll2002(SAMPLE.splitlines(), "t")


def test_parse_keeps_articles_and_tags():
    parsed = sentences()
    assert [s.doc_id for s in parsed] == ["t-0001", "t-0001", "t-0002"]
    assert parsed[0].tags[1:3] == ("B-PER", "I-PER")


def test_parse_rejects_wrong_column_count():
    with pytest.raises(ValueError):
        parse_conll2002(["word O"])


def test_load_split_reads_the_utf8_file_nltk_ships(tmp_path):
    # Real shape: read as Latin-1, the second byte of `à` is a no-break space and splits the line.
    for name in ("ned.train", "ned.testa", "ned.testb"):
        (tmp_path / name).write_text("dàt V O\nJan N B-PER\n", encoding="utf-8")
    sentences = load_split("test", tmp_path)
    assert sentences[0].tokens == ("dàt", "Jan")


def test_spacy_backend_survives_sentences_emptied_by_transcript_style():
    spacy = pytest.importorskip("spacy")
    from ner_nl.backends import SpacyNER

    nlp = spacy.blank("nl")
    nlp.add_pipe("ner").add_label("PERSON")
    nlp.initialize()
    data = [Sentence((), (), "a"), Sentence(("Jan",), ("O",), "a")]
    out = SpacyNER("blank", nlp=nlp)(data)
    assert out[0] == [] and len(out[1]) == 1


def test_bio_spans_round_trip_and_stray_inside_tag():
    assert bio_spans(["O", "B-PER", "I-PER", "B-LOC"]) == [(1, 3, "PER"), (3, 4, "LOC")]
    assert bio_spans(["I-ORG", "I-ORG", "I-PER"]) == [(0, 2, "ORG"), (2, 3, "PER")]
    assert bio_spans(["B-PER", "B-PER"]) == [(0, 1, "PER"), (1, 2, "PER")]
    spans = [(0, 2, "ORG"), (3, 4, "PER")]
    assert bio_spans(spans_to_bio(spans, 5)) == spans


def test_scoring_needs_exact_span_and_label():
    s = Sentence(("a", "b", "c"), ("B-PER", "I-PER", "O"), "d")
    partly = ["B-PER", "O", "O"]
    wrong = ["B-ORG", "I-ORG", "O"]
    assert prf(count_by_doc([s], [s.tags])[0])["f1"] == 1.0
    assert prf(count_by_doc([s], [partly])[0])["f1"] == 0.0
    assert prf(count_by_doc([s], [wrong])[0])["tp"] == 0
    assert prf(count_by_doc([s], [wrong], ("PER",))[0])["fp"] == 0


def test_scoring_rejects_misaligned_predictions():
    s = Sentence(("a", "b"), ("O", "O"), "d")
    with pytest.raises(ValueError):
        count_by_doc([s], [["O"]])


def test_f1_interval_matches_prf_and_counts_articles():
    data = sentences()
    rows, docs = count_by_doc(data, [s.tags for s in data])
    interval = f1_interval(rows, docs)
    assert interval.estimate == pytest.approx(1.0)
    assert interval.n_clusters == 2


def test_paired_difference_zero_on_identical_and_sign_correct():
    a = np.array([[5, 0, 0], [5, 0, 0], [4, 1, 1], [5, 0, 0]], dtype=float)
    b = np.array([[3, 2, 2], [4, 1, 1], [2, 3, 3], [5, 0, 0]], dtype=float)
    docs = list("abcd")
    same = paired_f1_difference(a, a, docs, n_boot=200)
    assert same.difference == 0 and same.low == 0 and same.high == 0
    better = paired_f1_difference(a, b, docs, n_boot=500)
    assert better.difference > 0 and better.n_clusters == 4


def test_transcript_style_drops_punct_and_keeps_entities_valid():
    s = Sentence(("De", "A.", ".", "B", "!"), ("O", "B-ORG", "I-ORG", "I-ORG", "O"), "d")
    new = perturb.transcript_style([s])[0]
    assert new.tokens == ("de", "a.", "b")
    assert bio_spans(new.tags) == [(1, 3, "ORG")]


def test_transcript_style_handles_all_punct_entity_and_empty_sentence():
    s = Sentence(("-", "x"), ("B-MISC", "O"), "d")
    assert perturb.transcript_style([s])[0].tags == ("O",)
    empty = perturb.transcript_style([Sentence((".",), ("O",), "d")])[0]
    assert empty.tokens == () and empty.tags == ()


def test_lowercase_keeps_tags():
    s = sentences()[0]
    assert perturb.lowercase([s])[0].tags == s.tags


def test_swap_names_preserves_non_person_entities_and_validates_gold():
    data = sentences()
    new, mentions = swap_names(data, "turkish", seed=1)
    assert new[0].tokens[-2:] == ("Gent", ".")
    assert bio_spans(new[2].tags) == [(0, 2, "ORG")]
    assert len(mentions) == 1
    m = mentions[0]
    assert (m.start, m.end, "PER") in bio_spans(new[0].tags)
    assert new[0].tokens[m.end - 1] in NAMES["turkish"]["last"]


def test_swap_names_uses_same_design_for_every_group():
    data = sentences() * 3
    runs = {g: swap_names(data, g, seed=2)[1] for g in NAMES}
    shapes = {g: [(m.sentence, m.start, m.end) for m in ms] for g, ms in runs.items()}
    assert all(v == shapes["dutch"] for v in shapes.values())


def test_swap_names_is_consistent_within_article():
    s = Sentence(("Peeters", "zegt", "Peeters"), ("B-PER", "O", "B-PER"), "d")
    new, _ = swap_names([s], "polish", seed=3)
    assert new[0].tokens[0] == new[0].tokens[2]


def test_name_lists_are_balanced_and_disjoint():
    for group in NAMES.values():
        assert len(group["first"]) == 20 and len(group["last"]) == 20
    for a, b in itertools.combinations(NAMES, 2):
        assert not set(NAMES[a]["last"]) & set(NAMES[b]["last"])


def test_gazetteer_prefers_longest_match_and_majority_label():
    train = [
        Sentence(("New", "York"), ("B-LOC", "I-LOC"), "a"),
        Sentence(("York",), ("B-ORG",), "a"),
        Sentence(("York",), ("B-ORG",), "a"),
        Sentence(("York",), ("B-LOC",), "a"),
    ]
    tag = Gazetteer(train)
    test = [Sentence(("in", "New", "York", "en", "York"), ("O",) * 5, "b")]
    assert tag(test)[0] == ["O", "B-LOC", "I-LOC", "O", "B-ORG"]


def test_audit_finds_repeats_seen_entities_and_conflicts():
    train = [
        Sentence(("Gent", "is", "een", "mooie", "stad"), ("B-LOC", "O", "O", "O", "O"), "a"),
        Sentence(("Gent",), ("B-ORG",), "a"),
        Sentence(("Gent",), ("B-LOC",), "a"),
    ]
    test = [train[0], Sentence(("Brugge",), ("B-LOC",), "b")]
    leak = audit.leakage(train, test)
    assert leak["exact_repeats_of_train_sentences"] == 1
    assert leak["seen_share"] == 0.5
    conflict = audit.label_conflicts(train)
    assert conflict["strings_with_two_or_more_labels"] == 1
    assert conflict["minority_label_mentions"] == 1


def test_audit_counts_invalid_bio():
    assert audit.invalid_bio([Sentence(("a", "b"), ("O", "I-PER"), "d")]) == 1
    assert audit.invalid_bio([Sentence(("a", "b"), ("B-PER", "I-LOC"), "d")]) == 1
    assert audit.describe(sentences())["articles"] == 2


def test_recall_by_seen_splits_mentions():
    train = [Sentence(("Gent",), ("B-LOC",), "a")]
    test = [Sentence(("gent", "Brugge"), ("B-LOC", "B-LOC"), "b")]
    out = recall_by_seen(train, test, [["B-LOC", "O"]])
    assert out["recall_seen"] == 1.0 and out["recall_unseen"] == 0.0


def test_entity_ece_zero_when_confidence_matches_outcome():
    assert entity_ece(np.array([1.0, 1.0, 0.0, 0.0]), np.array([1.0, 1.0, 0.0, 0.0]), 2) == 0
    assert entity_ece(np.array([1.0, 1.0]), np.array([0.0, 0.0]), 1) == 1


def test_label_map_targets_are_conll_labels():
    assert set(SPACY_TO_CONLL.values()) <= set(ALL_LABELS)
    assert "DATE" not in SPACY_TO_CONLL and "CARDINAL" not in SPACY_TO_CONLL


torch_tests = pytest.mark.torch


def _tiny_model():
    pytest.importorskip("torch")
    import torch

    from ner_nl.tagger import BiLSTMCRF, Config, Encoder

    torch.manual_seed(0)
    index = {"jan": 1, "gent": 2, "in": 3}
    vectors = torch.randn(4, 6)
    vectors[0] = 0
    data = [
        Sentence(("Jan", "in", "Gent"), ("B-PER", "O", "B-LOC"), "a"),
        Sentence(("in", "Gent"), ("O", "B-LOC"), "a"),
    ]
    encoder = Encoder.build(data, index)
    model = BiLSTMCRF(vectors, len(encoder.chars) + 2, Config(hidden=8, char_filters=4))
    return model.eval(), encoder, data


@torch_tests
def test_crf_marginals_and_partition_match_brute_force():
    import torch

    from ner_nl.tagger import TAGS

    model, encoder, data = _tiny_model()
    batch = encoder.batch(data)
    with torch.no_grad():
        em = model.emissions(batch)
        marginals = model.marginals(em, batch["mask"])
        forward = model._forward_scores(em, batch["mask"])
    trans, start, end = model._trans(), model._start(), model.end
    for b, n in ((0, 3), (1, 2)):
        table = np.zeros((n, len(TAGS)))
        scores = []
        for path in itertools.product(range(len(TAGS)), repeat=n):
            s = start[path[0]] + em[b, 0, path[0]]
            for t in range(1, n):
                s = s + trans[path[t - 1], path[t]] + em[b, t, path[t]]
            scores.append((path, float((s + end[path[-1]]).detach())))
        total = float(torch.logsumexp(torch.tensor([x for _, x in scores]), 0))
        for path, value in scores:
            for t, tag in enumerate(path):
                table[t, tag] += math.exp(value - total)
        assert np.allclose(table, marginals[b, :n].numpy(), atol=1e-3)
        assert float(torch.logsumexp(forward[b, -1] + end, 0)) == pytest.approx(total, abs=1e-2)


@torch_tests
def test_viterbi_finds_the_best_path_and_never_emits_invalid_bio():
    import torch

    from ner_nl.tagger import TAGS

    model, encoder, data = _tiny_model()
    batch = encoder.batch(data)
    with torch.no_grad():
        em = model.emissions(batch)
        path = model.decode(em, batch["mask"])[0]
    trans, start, end = model._trans(), model._start(), model.end

    def value(p):
        s = start[p[0]] + em[0, 0, p[0]]
        for t in range(1, 3):
            s = s + trans[p[t - 1], p[t]] + em[0, t, p[t]]
        return float(s + end[p[-1]])

    best = max(itertools.product(range(len(TAGS)), repeat=3), key=value)
    assert value(path) == pytest.approx(value(best), abs=1e-4)
    assert audit.invalid_bio([Sentence(("a",) * 3, tuple(TAGS[p] for p in path), "d")]) == 0


@torch_tests
def test_training_learns_a_toy_rule_and_handles_empty_sentences():
    pytest.importorskip("torch")
    from ner_nl.tagger import predict, train

    rng = random.Random(0)
    towns = ["Gent", "Brugge", "Hasselt"]
    data = []
    for _ in range(60):
        town = rng.choice(towns)
        data.append(Sentence(("in", town, "wonen"), ("O", "B-LOC", "O"), "a"))
    index = {"in": 1, "wonen": 2}
    vectors = np.random.default_rng(0).normal(size=(3, 5)).astype(np.float32)
    model, encoder, info = train(
        data, data[:10], vectors, index, epochs=8, batch_size=8, patience=8, lr=0.02,
        log=lambda *_: None,
    )
    assert info["best_dev_f1"] > 0.9
    out = predict(model, encoder, [data[0], Sentence((), (), "x")])
    assert out[1] == [] and out[0][1] == "B-LOC"


def test_redact_validates_iban_and_bsn():
    from ner_nl.redact import bsn_valid, iban_valid, redact

    assert iban_valid("NL91 ABNA 0417 1643 00")
    assert not iban_valid("NL92 ABNA 0417 1643 00")
    assert bsn_valid("111222333") and not bsn_valid("111222334")
    text = "IBAN NL91ABNA0417164300, BSN 111222333, geen BSN: 123456789."
    out, hits = redact(text)
    assert out == "IBAN [IBAN], BSN [BSN], geen BSN: 123456789."
    assert {h.kind for h in hits} == {"IBAN", "BSN"}


@pytest.mark.parametrize(
    "text",
    ["06-12345678", "020 123 45 67", "+31 6 12345678", "0031 20 1234567", "+31 (0)20-1234567"],
)
def test_redact_finds_dutch_phone_formats(text):
    from ner_nl.redact import redact

    assert redact(f"Bel {text} nu")[0] == "Bel [TELEFOON] nu"


@pytest.mark.parametrize("text", ["2023-2024", "1234567", "100 000 000 euro", "12-03-2021"])
def test_redact_leaves_ordinary_numbers_alone(text):
    from ner_nl.redact import redact

    assert redact(text)[0] == text


def test_redact_other_patterns_and_overlap_priority():
    from ner_nl.redact import Hit, merge, redact

    text = "Mail a.b@voorbeeld.nl of kijk op https://x.nl/a, postcode 1234 AB, ip 10.0.0.1"
    out = redact(text)[0]
    assert out == "Mail [E-MAIL] of kijk op [URL], postcode [POSTCODE], ip [IP]"
    kept = merge([Hit(0, 5, "PERSOON", "model"), Hit(2, 4, "BSN", "pattern")])
    assert [h.kind for h in kept] == ["BSN"]


def test_redact_uses_a_model_when_given_one():
    from ner_nl.redact import redact

    class Ent:
        start_char, end_char, label_ = 4, 15, "PERSON"

    class Doc:
        ents = [Ent()]

    out, _ = redact("Bel Sanne Bakker", lambda _: Doc())
    assert out == "Bel [PERSOON]r"


def test_missed_tokens_ignore_label_but_not_coverage():
    s = Sentence(("Jan", "Peeters", "x"), ("B-PER", "I-PER", "O"), "d")
    missed, total, _ = missed_tokens([s], [["B-ORG", "O", "O"]])
    assert missed.sum() == 1 and total.sum() == 2
    assert missed_tokens([s], [["B-MISC", "I-MISC", "O"]])[0].sum() == 2


def test_deduce_adapter_maps_offsets_and_tags_to_tokens():
    from types import SimpleNamespace as NS

    from ner_nl.backends import Deduce

    class Engine:
        def deidentify(self, text):
            assert text == "Dr Jan Peeters in Gent"
            return NS(
                annotations=[
                    NS(start_char=3, end_char=14, tag="persoon"),
                    NS(start_char=18, end_char=22, tag="locatie"),
                    NS(start_char=0, end_char=2, tag="datum"),
                ]
            )

    tags = Deduce(Engine()).tag(["Dr", "Jan", "Peeters", "in", "Gent"])
    assert tags == ["O", "B-PER", "I-PER", "O", "B-LOC"]
    assert Deduce(Engine()).tag([]) == []
