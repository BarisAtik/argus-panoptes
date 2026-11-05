# Evaluation card: Whisper on Dutch (Common Voice)

> **No results yet.** Everything below "Results" is to be filled from a `real` report.
> Hypotheses are registered here before the first run.

## What is evaluated

Off-the-shelf Whisper checkpoints (MIT licence) for Dutch transcription: `tiny` to `large-v3-turbo`,
via Transformers or faster-whisper. No fine-tuning yet.

## Data

Common Voice Scripted Speech, Dutch ([Mozilla Data Collective](https://mozilladatacollective.com/);
since October 2025 no longer distributed through Hugging Face). Check the licence and terms on the
dataset page before use. Audio is not redistributed from this repo and speaker ids are hashed
again; nothing here tries to identify speakers.

Known limits, before seeing any data:

- Read sentences, recorded by volunteers on their own devices. Not conversation, not meetings.
  Results say little about spontaneous speech or dialect.
- Contributors skew by age, gender and region, and demographic fields are optional and
  self-reported. Group results describe people who filled in the form.
- Common Voice is a *used* fine-tuning source for some public models, so a model may have seen
  similar sentences. Check model cards before calling a clip "unseen".

## Pre-registered hypotheses (written before any run)

1. `large-v2` beats `large-v3` on clean Dutch. Reported for Dutch on N-Best and JASMIN-CGN at
   [CLIN 34](https://clin34.leidenuniv.nl/abstracts/evaluating-the-state-of-the-art-automatic-speech-recognition-systems-for-dutch/);
   Common Voice is a different kind of speech, so it may not replicate.
2. Babble at 10 dB hurts more than pink noise at 10 dB for every model.
3. Compound spacing accounts for a visible share of errors (over 3% of reference words) on clean audio.
4. Smaller models hallucinate more on speech-free audio.
5. Mean log-probability ranks clip quality clearly better than random, but far from oracle.
6. Differences between accent groups exceed the speaker-level interval for at least one group, if
   any group has enough speakers.

7. On clean audio, Parakeet TDT 0.6b v3 (int8) does not beat `whisper-small` on Dutch. Added before
   any Parakeet run. It covers 25 languages, and Dutch is not its focus.

## Planned design

Test split only, at most 5 clips per speaker, 1000 to 2000 clips. Per the simulation, 500 clips
from 100 speakers detect a 2-point WER gap with about 95% power, but only about 47% for a 1-point
gap, so model differences under 1 point should be read as "not resolved" (under its assumptions).

## Results

_Pending._ Copy curated tables from `runs/*/report.md` to `results/asr_nl/` and link them here.

## Failure analysis

_Pending._

## Decisions about scoring

Scoring normalizes case, punctuation, numbers and elisions; hyphens become spaces. It keeps
diacritics. Sensitivity variants are in every report.
