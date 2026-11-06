"""The parser and label extraction, on a small synthetic checkout."""

import pytest

from beacon.sources import algoritmekader as ak

MEASURE = """---
title: Test de werking
id: urn:nl:ak:mtr:ver-99
toelichting: Test de werking van het model.
onderwerp:
- technische-robuustheid
vereiste:
- aia-99-iets
sources:
  ADR: SV.1
---
<!-- tags -->

## Maatregel
Test [de werking](../x.md) van het **model**.

## Toelichting
Eerste alinea
loopt door.

- punt een

!!! example "Voorbeeld"

    Tekst in een blok.

## Bijbehorende vereiste(n) { data-search-exclude }
Sectie met label-informatie SV.1

## Bronnen
[Geheim antwoord](https://example.org)
"""

REQUIREMENT = """---
title: Hoog-risico eis
id: urn:nl:ak:ver:aia-99
toelichting: Een hoog-risico systeem moet getest worden.
---
## Vereiste
Testen is verplicht.
"""

NORMS = """nummer;maatregel;source
SV.1;"De werking is
getoetst.";Onderzoekskader Auditdienst Rijk
SV.2;Zonder koppeling.;Onderzoekskader Auditdienst Rijk
1.01;Norm van de Rekenkamer.;Toetsingskader Algemene Rekenkamer
"""

RELATIONS = """nummer,bron,maatregelen-ak,urn:nl:ak:mtr:ver-99
SV.1,ADR,['urn:nl:ak:mtr:ver-99'],1
SV.2,ADR,[],0
1.01,ARK,"['urn:nl:ak:mtr:ver-99', 'urn:nl:ak:mtr:ontbreekt']",1
"""


@pytest.fixture
def checkout(tmp_path):
    for folder in ("maatregelen", "vereisten", "hulpmiddelen"):
        (tmp_path / ak.CONTENT / folder).mkdir(parents=True)
    pages = tmp_path / ak.CONTENT
    (pages / "maatregelen" / "5-ver-99-test.md").write_text(MEASURE, encoding="utf-8")
    (pages / "maatregelen" / "index.md").write_text("---\ntitle: x\n---\n## A\nb", encoding="utf-8")
    (pages / "vereisten" / "aia-99-iets.md").write_text(REQUIREMENT, encoding="utf-8")
    (tmp_path / "script").mkdir()
    (tmp_path / ak.NORMS_FILE).write_text(NORMS, encoding="utf-8")
    (tmp_path / ak.RELATIONS_FILE).write_text(RELATIONS, encoding="utf-8")
    return tmp_path


def test_page_fields_and_markup_removal(checkout):
    pages = ak.load_pages(checkout)
    assert len(pages) == 2  # the index page is skipped
    measure = next(d for d, _, _ in pages if d.doc_type == "maatregel")
    assert measure.id == "urn:nl:ak:mtr:ver-99"
    assert measure.subjects == ["technische-robuustheid"]
    assert measure.url.endswith("/maatregelen/5-ver-99-test/")
    assert "Test de werking van het model." in measure.text
    assert "Eerste alinea loopt door." in measure.text
    assert "punt een" in measure.text
    assert "Tekst in een blok." in measure.text


def test_label_sections_are_not_indexed(checkout):
    measure = next(d for d, _, _ in ak.load_pages(checkout) if d.doc_type == "maatregel")
    assert "SV.1" not in measure.text
    assert "Geheim antwoord" not in measure.text
    assert "<!--" not in measure.text


def test_audit_queries_join_norm_text_and_mapping(checkout):
    rows = ak.audit_queries(checkout / ak.NORMS_FILE, checkout / ak.RELATIONS_FILE)
    by_id = {row["id"]: row for row in rows}
    assert set(by_id) == {"audit-ADR-SV.1", "audit-ARK-1.01"}
    assert by_id["audit-ADR-SV.1"]["query"] == "De werking is getoetst."
    assert by_id["audit-ARK-1.01"]["kind"] == "audit-ARK"


def test_requirement_queries_use_the_summary_and_reverse_links(checkout):
    rows = ak.requirement_queries(ak.load_pages(checkout))
    assert rows[0]["query"] == "Een hoog-risico systeem moet getest worden."
    assert rows[0]["relevant"] == {"urn:nl:ak:mtr:ver-99": 1}


def test_build_drops_labels_for_unknown_pages(checkout, tmp_path):
    from beacon.models import read_jsonl

    counts = ak.build(checkout, tmp_path / "out")
    assert counts["documents"] == 2
    rows = {r["id"]: r for r in read_jsonl(tmp_path / "out" / "queries-audit.jsonl")}
    assert list(rows["audit-ARK-1.01"]["relevant"]) == ["urn:nl:ak:mtr:ver-99"]


def test_split_is_stable_and_splits():
    ids = [f"q{i}" for i in range(200)]
    assert [ak.split_for(i) for i in ids] == [ak.split_for(i) for i in ids]
    assert 60 < sum(ak.split_for(i) == "test" for i in ids) < 140


def test_invisible_characters_do_not_survive_parsing():
    assert ak.clean_inline("to​ets") == "toets"
