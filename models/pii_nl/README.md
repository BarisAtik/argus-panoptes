# 🕵️ pii_nl: how much personal data survives Dutch redaction?

Taggers get measured on news. Personal data lives in letters, app chats, call transcripts and terse
notes. This project is a fully synthetic benchmark across those registers, plus a local redactor
that was built against it and then scored on templates its author never read.

## Result

On blind template set `test2` (36 templates, 5720 fictional values, commit `965281a`, 6 Nov 2026).
Share of values with any word left readable, 95% cluster t intervals over templates:

| System | All personal data | Persons | Ordinary words masked |
| --- | --- | --- | --- |
| spaCy `nl_core_news_lg` + patterns | 30.9% (22.5 to 39.4) | 27.1% (20.3 to 33.8) | 1.0% |
| DEDUCE | 23.5% (13.4 to 33.6) | 24.6% (12.9 to 36.3) | 0.8% |
| rules + `lg` | 6.0% (2.6 to 9.5) | 8.5% (2.4 to 14.6) | 1.8% |
| rules + `lg` + truecasing | **4.8%** (1.9 to 7.6) | **5.6%** (2.0 to 9.1) | 2.4% |

The news model's name gaps are the sharpest finding: in round one, swapping in common Hindustani
Surinamese names raised person leak by 31 points against the Dutch list (23 to 39). Rules shrink
that gap, and the interval no longer excludes zero, which isn't proof it is gone.

**This does not measure a real archive.** Templates are synthetic and written by language models.
The rate says where a tool breaks, not what it would miss on your documents. It leaks about 16% of
names in chat and transcripts, so a person still has to review the output.

## Why these numbers can be believed a bit

- Hypotheses were committed before any scoring. Three of eleven turned out partly or fully wrong,
  and stay in [the card](EVALUATION_CARD.md).
- Test templates came from a separate agent with no access to the rules. The first blind round
  confirmed that tuning flatters: leak on test was 2.3 times dev.
- Fifty fills of one template aren't fifty observations. Template-level intervals are 4.3 times
  wider than naive document-level ones, and these are what's reported.
- Rules may not use the benchmark's name, street or town lists.

## How it works

Patterns with checksums (IBAN, BSN), contextual rules (titles, greetings, signatures, "geboren"),
spoken numbers and dictated mail addresses, a spaCy pipeline on a truecased copy of lowercase lines,
and propagation: a name found once gets masked everywhere in the document, including names read off
a mail address.

## Use

```bash
pip install -e ".[pii]"
python -m spacy download nl_core_news_lg
echo "bel sanne bakker op 06-12345678" | python -m pii_nl.cli -
python -m pii_nl.cli notes.txt --json        # adds every hit, for a reviewer
pip install gradio && python -m pii_nl.app   # local demo
```

Docker: see the top of [`Dockerfile`](Dockerfile). It works with `--network none`, so the container
provably can't send anything. (Neither the image nor the Gradio app has been built or run yet.)

## Reproduce

```bash
python -m pii_nl.run score --split test2 --seed 1 --systems spacy_lg deduce rules_lg rules_lg_tc
python -m pii_nl.run report --split test2
```

## Licences

Code: this repo. spaCy Dutch models: CC BY-SA 4.0. `wordfreq`: Apache-2.0 code, with word-frequency
data under its own CC BY-SA terms. DEDUCE: LGPL, used only as a comparator. Check these before
shipping anything commercial.
