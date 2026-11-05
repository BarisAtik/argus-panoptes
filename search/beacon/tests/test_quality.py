from datetime import date

from conftest import make_document

from beacon.quality import identifier_hints, is_bsn_like, report, to_markdown

# 111222333 passes the 11-test and is the example Dutch government documents use.
BSN = "111222333"


def test_eleven_test():
    assert is_bsn_like(BSN)
    assert not is_bsn_like("123456789")
    assert not is_bsn_like("000000000")
    assert not is_bsn_like("12345")


def test_identifier_hints():
    text = f"Mail a.b@example.nl of bel 06-12345678. IBAN NL91 ABNA 0417 1643 00. BSN {BSN}."
    hints = identifier_hints(text)
    assert hints == {"email": 1, "phone": 1, "iban": 1, "bsn_shaped": 1}


def test_dates_and_case_numbers_are_not_phone_numbers():
    assert identifier_hints("Op 12-03-2025, zaaknummer 200.123.456/01.") == {}


def test_report_finds_problems():
    documents = [
        make_document("a", text="Tekst " * 60, court="R", date="2025-01-01", subjects=["S"],
                      summary="Samenvatting."),
        make_document("a", text="Tekst " * 60),
        make_document("c", text="kort [verdachte]", date="2999-01-01"),
        make_document("d", text=""),
    ]
    result = report(documents, today=date(2026, 1, 1))
    issues = result["issues"]
    assert issues["duplicate_ids"] == 1
    assert issues["duplicate_texts"] == 1
    assert issues["empty_body"] == 1
    assert issues["short_body_under_50_words"] == 1
    assert issues["future_date"] == 1
    assert issues["missing_summary"] == 3
    assert result["privacy"]["pseudonym_markers"] == 1


def test_report_never_contains_the_identifier_itself():
    documents = [make_document(text=f"Mail a.b@example.nl, nummer {BSN}.")]
    output = to_markdown(report(documents))
    assert "a.b@example.nl" not in output
    assert BSN not in output
    assert "hint: email | 1" in output


def test_demo_corpus_is_clean(demo_corpus):
    result = report(demo_corpus)
    assert result["privacy"]["identifier_hints"] == {}
    assert result["issues"]["duplicate_texts"] == 0
