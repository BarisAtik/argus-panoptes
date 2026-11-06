"""Scan pipeline: geometry, masks and audit. No OCR engine or model is needed."""

import numpy as np
import pytest

pytest.importorskip("cv2")
pytest.importorskip("PIL")

from pii_nl.generate import render  # noqa: E402
from scan_nl.audit import audit, error_rate, redact_words, truth_words, word_masks  # noqa: E402
from scan_nl.degrade import CONDITIONS, apply, corners  # noqa: E402
from scan_nl.mitigate import conf_masks, digit_masks, repair_digits, unread_regions  # noqa: E402
from scan_nl.ocr import OcrWord, assemble, parse_tsv, split_line  # noqa: E402
from scan_nl.render import gold_boxes, render_page  # noqa: E402

TEMPLATE = {
    "id": "x-1", "register": "brief",
    "text": "Geachte mevrouw {ACHTERNAAM},\n\nUw rekening {IBAN} staat op naam van {NAAM}. "
            "Het bedrag van {BEDRAG} is voldaan.\n\nMet vriendelijke groet,\n{NAAM2}",
}
DOC = render(TEMPLATE, "dutch", 0)
PAGE = render_page(DOC, "sans")


def ink(box, image):
    x0, y0, x1, y1 = box
    return (np.asarray(image)[y0:y1, x0:x1] < 128).mean()


def test_gold_boxes_sit_on_ink():
    for span in DOC.spans:
        for box in gold_boxes(PAGE, DOC, span.start, span.end):
            assert ink(box, PAGE.image) > 0.05


def test_value_inside_longer_token_gets_a_partial_box():
    # "{ACHTERNAAM}," is one token, the comma stays outside the value.
    span = DOC.spans[0]
    box = gold_boxes(PAGE, DOC, span.start, span.end)[-1]
    word = next(w for w in PAGE.words if w.start <= span.end - 1 < w.end)
    assert box[2] <= word.box[2]


@pytest.mark.parametrize("name", list(CONDITIONS))
def test_conditions_keep_gold_on_ink(name):
    image, matrix = apply(name, PAGE.image, 3)
    span = next(s for s in DOC.spans if s.kind == "IBAN")
    box = gold_boxes(PAGE, DOC, span.start, span.end)[0]
    quad = corners(box, matrix)
    x0, y0 = np.floor(quad.min(axis=0)).astype(int)
    x1, y1 = np.ceil(quad.max(axis=0)).astype(int)
    crop, around = image[y0:y1, x0:x1], np.median(image)
    assert 0 <= x0 and x1 <= image.shape[1] and y1 <= image.shape[0]
    assert crop.mean() < around - 8  # darker than the paper around it


def test_same_seed_same_damage():
    a, _ = apply("photocopy", PAGE.image, 5)
    b, _ = apply("photocopy", PAGE.image, 5)
    assert (a == b).all()


def test_full_masks_hide_everything_and_none_hide_nothing():
    image, matrix = apply("skew_4", PAGE.image, 1)
    words = truth_words(DOC, PAGE, matrix)
    full = audit(DOC, PAGE, matrix, image.shape[:2], words, list(range(len(words))), 4)
    empty = audit(DOC, PAGE, matrix, image.shape[:2], words, [], 4)
    def gold(rows):
        return [r for r in rows if not r["kind"].startswith("_")]

    assert all(r["pixel"] == 0 and r["text"] == 0 for r in gold(full))
    assert all(r["pixel"] == r["total"] and r["text"] > 0 for r in gold(empty))


def test_garbled_word_leaks_in_pixels_but_not_in_text_audit():
    image, matrix = apply("clean_300", PAGE.image, 1)
    words = truth_words(DOC, PAGE, matrix)
    iban = next(s for s in DOC.spans if s.kind == "IBAN")
    target = next(i for i, w in enumerate(PAGE.words) if w.start == iban.start)
    words[target].text = "NLXXGARBLED"
    rows = audit(DOC, PAGE, matrix, image.shape[:2], words, [], 4)
    row = next(r for r in rows if r["kind"] == "IBAN")
    assert row == {"kind": "IBAN", "pixel": 1, "text": 0, "total": 1}


def test_masks_reach_a_word_from_character_ranges():
    words = [OcrWord(t, [[0, 0], [1, 0], [1, 1], [0, 1]], 1.0, 0) for t in ("ab", "cd", "ef")]
    text, ranges = assemble(words)
    assert word_masks(words, ranges, [(text.index("cd"), text.index("cd") + 1)]) == [1]
    assert redact_words(words, lambda t: [(0, 2)])[0] == [0]


def test_assemble_keeps_blocks_and_joins_wrapped_lines():
    def word(text, y, line, x=0, w=400):
        return OcrWord(text, [[x, y], [x + w, y], [x + w, y + 30], [x, y + 30]], 1.0, line)

    text, ranges = assemble([word("een", 0, 0), word("twee", 40, 1), word("drie", 240, 2)])
    assert text == "een twee\ndrie"
    assert [text[a:b] for a, b in ranges] == ["een", "twee", "drie"]


def test_parse_tsv_real_shape():
    header = "\t".join(
        "level page_num block_num par_num line_num word_num left top width height conf text".split()
    ) + "\n"
    rows = "4\t1\t1\t1\t1\t0\t5\t5\t90\t20\t-1\t\n5\t1\t1\t1\t1\t1\t10\t5\t30\t20\t91.5\tDag\n"
    words = parse_tsv(header + rows)
    assert len(words) == 1 and words[0].poly[2] == [40.0, 25.0] and words[0].conf == 0.915


def test_split_line_shares_width_by_characters():
    quad = np.array([[0, 0], [100, 0], [100, 10], [0, 10]], dtype=float)
    a, b = split_line("abcd efgh i", quad, 0.9, 0)[:2]
    assert a.poly[1][0] == pytest.approx(100 * 4 / 11)
    assert b.poly[0][0] == pytest.approx(100 * 5 / 11)


def test_split_line_finds_real_word_edges():
    image = np.full((20, 200), 255, dtype=np.uint8)
    image[4:16, 10:30] = 0  # a short word
    image[4:16, 34:60] = 0  # small gap inside the second word
    image[4:16, 100:190] = 0
    quad = np.array([[0, 0], [200, 0], [200, 20], [0, 20]], dtype=float)
    a, b = split_line("abcd efgh", quad, 0.9, 0, image)
    assert 60 < a.poly[1][0] < 100 and a.poly[1][0] == b.poly[0][0]


def test_unread_ink_is_found_and_read_ink_is_not():
    image, matrix = apply("clean_300", PAGE.image, 1)
    words = truth_words(DOC, PAGE, matrix)
    assert unread_regions(image, words, 1.0) == ([], 0.0) or unread_regions(
        image, words, 1.0
    )[1] < 0.02
    regions, share = unread_regions(image, words[: len(words) // 2], 1.0)
    assert share > 0.2 and regions


def test_digit_masks_and_conf_masks():
    words = [OcrWord(t, [[0, 0]] * 4, c, 0) for t, c in
             (("NL91ABNA0417164300", 0.9), ("Jansen", 0.2), ("2025", 0.9), ("3223SO281", 0.9))]
    assert digit_masks(words, 5, 0.6) == [0, 3]
    assert conf_masks(words, 0.5) == [1]


def test_repair_digits_keeps_length_and_plain_words():
    text = "Burgerservicenummer 3223SO281 Bakker"
    fixed = repair_digits(text)
    assert len(fixed) == len(text)
    assert "322350281" in fixed and fixed.endswith("Bakker")


def test_error_rate():
    assert error_rate("abcd", "abcd") == 0
    assert error_rate("abcd  efg", "abxd efg") == pytest.approx(1 / 8)
