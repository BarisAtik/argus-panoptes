# 🎙️ asr_nl: where does Whisper break on Dutch?

Published Dutch ASR numbers usually come from restricted corpora, and a single WER hides most of
what matters. This project runs Whisper variants on Common Voice Dutch and asks where they fail:
which accents, what noise, how often they invent speech, and whether their confidence can be
trusted.

Status: **pipeline tested, no real results yet.** See the [evaluation card](EVALUATION_CARD.md).

## What makes this more than a WER table

- **Speaker-level uncertainty.** Intervals resample speakers. A [simulation](../docs/ci_coverage_simulation.md)
  shows that resampling clips can give a nominal 95% interval only about 55% coverage.
- **Dutch-aware scoring.** Numbers are spelled out with correct Dutch forms (`22` → `tweeëntwintig`),
  elisions expanded (`'t` → `het`). The report also shows the WER without normalization and
  without diacritics, so you can see how much of the headline is a scoring decision.
- **Compound accounting.** Dutch writes `voetbalveld` as one word. A model that outputs `voetbal
  veld` heard it correctly but pays two word errors. These slips are counted separately.
- **Hallucination test.** Speech-free audio goes in. The correct output is nothing.
- **Controlled degradation.** Noise is seeded per clip, so every model hears exactly the same
  audio: white, pink, multi-speaker babble, telephone band, reverb.
- **Paired comparisons.** Model pairs are compared on identical clips with Holm correction.
- **Selective transcription.** Can the mean token log-probability pick out the bad transcripts,
  or is it decoration? Measured with a risk-coverage curve against random and oracle.

## Run it

```bash
pip install -e ".[asr,dev]"                # plus ".[asr-fast]" for faster-whisper
export MDC_API_KEY=...                     # from mozilladatacollective.com, after accepting terms
python -m asr_nl.fetch_common_voice --n 1000 --out runs/cv_nl
python -m asr_nl.cli audit --manifest runs/cv_nl/manifest_test_1000.jsonl
python -m asr_nl.cli run --config asr_nl/configs/laptop.yaml
```

The report lands in `runs/asr_laptop/report.md`. Transcription resumes where it stopped, so a
disconnected notebook loses at most one batch. Add a model by editing the YAML; prefix
`faster:` uses faster-whisper (`faster:large-v3`).

Any other speech data works too: write a JSONL manifest with `id, path, text, speaker` and
optionally `accent, gender, age`.
