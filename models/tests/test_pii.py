"""Benchmark generator, scorer and rules. No models, no downloads."""

import re

from pii_nl.evaluate import rate, score_document, span_leaked
from pii_nl.generate import Span, generate, load_templates, render
from pii_nl.rules import redact, rule_hits

TEMPLATE = {
    "id": "x-1",
    "register": "brief",
    "text": "Geachte mevrouw {ACHTERNAAM}, uw IBAN {IBAN} en {BEDRAG} in {PLAATS}.",
}


def test_render_spans_point_at_their_values():
    doc = render(TEMPLATE, "dutch", 0)
    for span in doc.spans:
        assert doc.text[span.start : span.end].strip()
    assert "{" not in doc.text
    assert render(TEMPLATE, "dutch", 0) == doc


def test_groups_are_paired_on_everything_but_names():
    a = render(TEMPLATE, "polish", 3)
    b = render(TEMPLATE, "turkish", 3)
    assert a.spans[1:] != ()
    iban = [s for s in a.spans if s.slot == "IBAN"][0]
    iban_b = [s for s in b.spans if s.slot == "IBAN"][0]
    assert a.text[iban.start : iban.end] == b.text[iban_b.start : iban_b.end]


def test_generated_numbers_pass_format_checks():
    from ner_nl.redact import bsn_valid, iban_valid

    template = {"id": "n", "register": "brief", "text": "{BSN} {IBAN}"}
    for repeat in range(30):
        doc = render(template, "dutch", repeat)
        bsn, iban = [doc.text[s.start : s.end] for s in doc.spans]
        assert bsn_valid(bsn) and iban_valid(iban)


def test_transcript_values_are_spoken():
    template = {"id": "t", "register": "transcript", "text": "nummer {TELEFOON} mail {EMAIL}"}
    doc = render(template, "dutch", 1)
    assert not re.search(r"\d", doc.text)
    assert "apenstaartje" in doc.text


def test_partial_mask_counts_as_a_leak():
    text = "S. Bakker"
    span = Span(0, 9, "PERSOON", "INITIAAL")
    assert span_leaked(text, span, [(3, 9)])
    assert not span_leaked(text, span, [(0, 9)])


def test_score_document_keeps_neutral_towns_out():
    doc = render(TEMPLATE, "dutch", 0)
    town = [s for s in doc.spans if s.slot == "PLAATS"][0]
    result = score_document(doc, [(town.start, town.end)])
    assert result["outside"][0] == 0
    assert result["distractor"][0] == 0


def test_rate_uses_template_clusters():
    rows = [
        {"template": f"t{i}", "kind": "PERSOON", "leaked": i % 2, "total": 1} for i in range(10)
    ]
    out = rate(rows, kind=None)
    assert out["clusters"] == 10
    assert out["low"] < 0.5 < out["high"]


def test_templates_only_use_known_slots():
    for split in ("dev", "test", "test2"):
        docs = generate(split, repeats=1)
        assert docs


def test_split_sizes():
    assert len(load_templates("dev")) == 24
    assert len(load_templates("test")) == 36
    assert len(load_templates("test2")) == 36


def test_rules_mask_title_cue_and_propagate():
    out = redact("Mevrouw Yilmaz belde. Later zei yilmaz dat het goed was.")[0]
    assert "ilmaz" not in out
    assert "belde" in out


def test_rules_mask_spoken_number_but_not_the_words_after_it():
    out = redact("mijn nummer is nul zes een twee drie vier vijf zes als u wil bellen")[0]
    assert "vijf" not in out
    assert out.endswith("als u wil bellen")


def test_rules_find_mail_derived_names():
    out = redact("zeg het tegen sanne of mail sanne.bakker@example.nl")[0]
    assert "sanne" not in out


def test_rules_birth_date_needs_context():
    assert "1947" not in redact("Geb. 3 april 1947 te huis")[0]
    assert "2025" in redact("Op 3 april 2025 kwam de brief")[0]


def test_rules_address_plate_and_signature():
    out = redact("Ik woon op de Kerkstraat 12 met auto XB-123-K.\n\nGroet,\nJan de Boer")[0]
    assert "Kerkstraat" not in out and "XB-123-K" not in out and "Boer" not in out


def test_rule_hits_leave_plain_text_alone():
    assert rule_hits("de vergadering begint om negen uur in de grote zaal") == []


def test_truecase_keeps_offsets_and_skips_cased_lines():
    import pytest

    pytest.importorskip("wordfreq")
    from pii_nl.rules import truecase

    text = "ik heb ramdin gebeld over de rekening\nDe Heer Ramdin Belde Vandaag Ook Nog"
    out = truecase(text)
    assert len(out) == len(text)
    assert "Ramdin gebeld" in out and out.split("\n")[1] == text.split("\n")[1]
    assert "rekening" in out


def test_spoken_plate_needs_uncommon_letters():
    from pii_nl.rules import rule_hits

    assert any(h.kind == "KENTEKEN" for h in rule_hits("met de auto vt vier nul een b dus"))
    assert not any(h.kind == "KENTEKEN" for h in rule_hits("ik heb er twee drie maal in gezien"))
