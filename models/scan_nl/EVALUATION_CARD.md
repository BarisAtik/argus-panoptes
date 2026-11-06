# Evaluation card: Dutch OCR-to-redaction

## What is tested

A page image goes through OCR, the text goes through the `pii_nl` redactor (`rules_lg_tc`), and the
words it marks are blacked out on the image. Pages are typeset here from generated documents, so
the true ink box of every word of every personal value is known. The audit asks a question that
text-only tests can't: is the true ink actually covered?

**Not tested:** real scans, handwriting, stamps, tables as real tables, multi-column pages, PDFs
with a text layer. Pixels here come from fonts and a damage model, not from paper.

## Data

- Generated with `pii_nl.generate`: reserved mail domains, random values, nothing committed.
- Four registers that exist on paper: `brief`, `mail`, `beschikking`, `notitie`.
- `dev`: the 16 `pii_nl` dev templates in those registers. Used freely, including to set every
  threshold below and to change the adapters.
- `blind`: 24 new templates in `scan_nl/templates/blind.jsonl`, written by a separate agent that
  could not see the redactor or this code, and committed before any scoring. Nobody read them here.
- Five name lists crossed with templates. Five fonts, assigned by hash. Twelve damage conditions.

## Engines

| Name | What | Notes |
| --- | --- | --- |
| `truth` | Perfect OCR | Floor: what the redactor leaks on its own |
| `tesseract_nld` | Tesseract 5.3.4, Dutch traineddata 4.1.0 | Default settings, `--psm 4` |
| `tesseract_eng` | Same, English traineddata | Does the language pack matter? |
| `tesseract_enh` | `tesseract_nld` after enlarging to about 300 dpi and dividing out the background | About fifteen lines of OpenCV |
| `rapidocr` | `rapidocr_onnxruntime` 1.4.4, PP-OCRv4 mobile ONNX bundled in the Apache-2.0 wheel | Reports lines, so word boxes come from gaps in the ink |

## Metrics

- **Pixel leak** (primary): share of values with any word whose true box is under 90% covered.
  Masks are padded 6 px at 300 dpi. Audited on a quarter-scale raster.
- **Text-audit leak:** share of values with a word of two or more characters, not a name particle,
  found verbatim outside the masks in the OCR text. This is what you get without pixel truth.
- **Ordinary words masked:** share of words outside any value and any distractor at least half
  covered. **Distractors masked:** the same for amounts, dates, times and case numbers.
- **CER:** edit distance over whitespace-normalised text, also with spaces removed.
- Intervals: 95% cluster t over templates, as in `pii_nl`. Differences are paired by template.

## Defences, all after reading

- `repair`: second pass of the redactor with look-alike characters read as digits in number tokens.
- `digits`: mask tokens with at least 5 digits that are at least 60% digit-like.
- `lowconf`: mask words under confidence 0.5.
- `unread`: fail closed. Ink that no OCR word explains is blacked out as well.
- Page review rule: flag a page if over 5% of its ink is unread.

## What dev changed

Everything here happened on dev, before the blind templates were scored.

- The first pass showed `tesseract_nld` losing half of photocopied pages. Global thresholding splits
  the shadowed paper, and the confidence of the words it did read stays high. `unread` and the
  review rule were designed after seeing this. `tesseract_enh` was planned before.
- The text audit counted name particles as leaks, so `van` in ordinary text scored as a leak. Fixed.
- RapidOCR word boxes were first cut by character count, which cost it about 20 points of pixel leak
  on the adapter alone. They now come from ink gaps.
- On clean pages the bundled detector drops whole lines, and resizing or blurring gave no stable
  gain, so RapidOCR runs as shipped. This is one mobile model in one package, not a verdict on PaddleOCR.

## Hypotheses, registered 2026-11-06 before any blind score

Pixel leak on `blind`, all 120 documents, `rules_lg_tc`. "Hard" pools `dpi_100`, `fax`, `photocopy`
and `phone`.

1. **Floor.** `truth` leaks at most 8%.
2. **Blind spot.** `tesseract_nld` leaks at least 40% on `photocopy` and on `phone`, while the
   text audit of the same pages reports at most 10%.
3. **Mild damage.** With `tesseract_enh`, each of `dpi_200`, `dpi_150`, `jpeg`, `noise`, `blur` and
   `skew_1` stays within 3 points of `clean_300`.
4. **Enhancement.** On hard, `tesseract_enh` cuts the leak of `tesseract_nld` by at least 70%.
5. **Language pack.** On `clean_300`, `tesseract_eng` is within 0.5 CER points and 2 leak points of
   `tesseract_nld`.
6. **Line reader.** Over all conditions, `rapidocr` leaks at least 10 points more than
   `tesseract_enh` and masks at least twice as many ordinary words.
7. **Fail closed.** Over all conditions, `unread` cuts the leak of `tesseract_nld` by at least 60%,
   with ordinary words masked at most 30%.
8. **Wrong alarm.** For `tesseract_nld`, the review rule catches at least twice as many leaked
   values as flagging the same number of lowest-confidence pages.
9. **Number tricks.** With `tesseract_enh`, `repair` moves the leak by under 1 point. `digits` cuts it
   by under 2 points and adds at least 20 points of distractors masked.
10. **Names.** With `tesseract_nld` on hard, OCR adds at least 2 points more person leak (engine minus
    `truth`) to the Turkish, Polish and Hindustani lists than to the Dutch list, because of the Dutch
    word model.

The checks were run once on dev after writing this list, to test the code. Two already looked wrong
there: 8 came out at 1.8 times and 10 went the other way. Both stay as written.

## Results

Commit ffe2dae, 2026-11-06, 120 documents, 12 conditions. Full tables: [`results/scan_nl/blind.md`](../results/scan_nl/blind.md).
Checks: [`hypotheses.json`](../results/scan_nl/hypotheses.json). Dev figures, with thresholds tuned, are in
[`dev.md`](../results/scan_nl/dev.md).

| # | Verdict | Evidence |
| --- | --- | --- |
| 1 | Supported | `truth` 0.4% (0.0 to 0.9) |
| 2 | Supported | Pixels 61.9% (53.1 to 70.7) on `photocopy`, 56.1% (48.1 to 64.1) on `phone`. Text audit 1.2% and 3.0% |
| 3 | **Wrong in part** | Five of six stay within 3 points. `noise` adds 3.5 (1.9 to 5.0) |
| 4 | Supported | 32.6% to 2.9% on hard, a 91% cut |
| 5 | Supported | CER 0.21% against 0.13%. English leaks 1.0 point less (0.2 to 1.9), which nobody expected |
| 6 | Supported, narrowly on the second part | 23.5 points more leak (19.6 to 27.4). Ordinary words masked 16.5% against 8.2%, a ratio of 2.02 |
| 7 | Supported | 14.1% to 4.1%, a 71% cut, with 18.5% of ordinary words masked |
| 8 | **Wrong** | The rule catches 1176 of 1501 leaked values, confidence 658: 1.79 times, not 2. It was under 2 on dev too |
| 9 | Supported | `repair` -0.05 points, `digits` -0.9, at +29.6 points of distractors masked |
| 10 | **Wrong** | Beyond the Dutch list: Polish +6.2, Moroccan +1.2, Hindustani -0.3, Turkish -2.1. Only Polish fits, and that difference has no interval |

**What it means.** On these pages the redactor is not the weak link. With perfect reading it leaks
0.4%. Most of what escapes is text the reader never saw, and a check of the output text can't see
that either: it reports about 2% where the page shows about 60%. The reader was sure of itself, too,
because confidence averages only over the words it found.

**Surprises and things found after the fact (not registered).**
- `skew_4` was not in the registered sets and came out as the worst condition left: 21.9% for both
  Tesseract variants, CER 36%. `tesseract_enh` does no deskewing, so this was a gap in the plan.
- Best combination: `tesseract_enh` with `unread`, 3.2% (2.5 to 3.9) over all conditions with 9.6%
  of ordinary words masked. Without `unread`: 4.1% and 8.2%. Picked after seeing the blind data, so
  treat it as a lead.
- With `tesseract_nld`, pages without a flag leak 3.8%, and the rule sends 20% of pages to a person.
- Fail closed works by destroying the page: on `photocopy` it blacks out 66% of ordinary words.
  That is the correct failure for this tool, but a redacted page without text is not a useful page.
- `rapidocr` handles `skew_4` better than Tesseract (18.4%) but is worse everywhere else. Most of its
  gap is whole lines missed by the detector and glued words. Part of it may still be the word-box
  adapter. No confidence or `unread` signal was useful for it.
- Tesseract `eng` reads Dutch about as well as `nld`. Together with hypothesis 10, this suggests the
  language pack matters little on these pages. That is a reading of two results, not a test.

## Known limits

- **The sizes are about this damage model.** The large shadow failure comes from a smooth 25 to 35%
  brightness ramp, which global thresholding handles badly. How often real scans look like that is
  unknown. The mechanism is shown; its rate on real paper is not.
- Simple one-column pages. Tables, stamps, logos, letterheads and handwriting would all add failures.
- One template author, 24 templates, four registers. The 7.8% of ordinary words masked comes from
  the redactor on text it wasn't tuned for.
- Fonts rotate by hash and are not balanced across conditions in a designed way. Leak by font runs
  from 2.7% to 5.4% for `tesseract_enh`, and is not tested.
- A covered box proves nothing about information in layout, line length or document metadata.
- Thresholds of 90% coverage and 5% unread ink are choices. A different one moves the numbers.
