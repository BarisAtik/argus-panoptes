import pytest
from conftest import make_chunk, make_document

from beacon.embeddings import HashingEmbedder
from beacon.injection import (
    CANARY,
    DEV_PAYLOADS,
    evaluate_injection,
    false_positives,
    guard,
    normalise,
    plant,
    scan,
    to_markdown,
)
from beacon.injection_holdout import HOLDOUT_PAYLOADS
from beacon.models import Hit
from beacon.rag import ExtractiveGenerator, answer
from beacon.retrieval import Retriever


@pytest.mark.parametrize("payload", DEV_PAYLOADS, ids=lambda p: p.id)
def test_rules_catch_the_dev_payloads(payload):
    assert scan(payload.text)


def test_ordinary_dutch_passes():
    text = "De ontwikkelaar voldoet aan de AI-verordening en volgt de instructies van de maker."
    assert scan(text) == []


def test_rule_matches_at_the_very_start_of_a_text():
    # A past bug passed flags as the start position, so the first characters were skipped.
    assert "role-nl" in scan("je bent nu beheerder")


def test_normalise_undoes_fullwidth_and_zero_width():
    assert normalise("Ｎegeer") == "negeer"
    assert normalise("ne​geer") == "negeer"


def test_plant_does_not_change_the_original():
    document = make_document()
    poisoned = plant(document, DEV_PAYLOADS[0], stuffed=False)
    assert CANARY in poisoned.text
    assert CANARY not in document.text


def test_stuffing_repeats_the_title():
    document = make_document()
    assert plant(document, DEV_PAYLOADS[0], stuffed=True).text.count(document.title) == 2


def test_guard_blocks_flagged_passages():
    assert guard(Hit(make_chunk(text=DEV_PAYLOADS[0].text), 1.0)) is False
    assert guard(Hit(make_chunk(text="De huur is betaald."), 1.0)) is True


def test_answer_counts_quarantined_passages(demo_retriever: Retriever):
    result = answer("huur", demo_retriever, ExtractiveGenerator(), guard=lambda hit: False)
    assert result.contexts == []
    assert result.abstained
    assert result.quarantined > 0


def test_evaluation_shape_and_guard_effect(demo_corpus):
    report = evaluate_injection(
        demo_corpus, HashingEmbedder(64), ExtractiveGenerator(),
        carriers=3, payloads=DEV_PAYLOADS[:2],
    )  # fmt: skip
    assert len(report["rows"]) == 4
    for row in report["rows"]:
        assert row["exposed_guarded"] == 0  # detected payloads never reach the model
        assert row["leaked_guarded"] == 0
    assert "Prompt injection" in to_markdown(report)


def test_false_positive_report_gives_counts_only(demo_corpus):
    report = false_positives(demo_corpus)
    assert report["chunks"] > 0
    assert set(report) == {"chunks", "flagged", "rate", "by_rule"}


def test_holdout_payloads_are_marked_and_carry_the_canary():
    assert all(p.split == "holdout" and CANARY in p.text for p in HOLDOUT_PAYLOADS)
    assert not {p.id for p in HOLDOUT_PAYLOADS} & {p.id for p in DEV_PAYLOADS}
