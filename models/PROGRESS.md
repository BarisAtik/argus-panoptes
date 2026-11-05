# Forge progress log

Newest run first. Each session: read this, continue from the TODO, add an entry.

## 2026-11-05: first run

### Done

- Built the `argus-forge` package with three projects (`asr_nl`, `text_nl`, `clip_search`) and the
  shared `forge` library. Includes 93 tests that need no network or GPU, `ruff` clean.
  The tests drive real Whisper, BERT and CLIP code paths on tiny random models, including the
  fine-tuning loop and the multilingual Whisper `language=nl` path.
- Wrote pre-registered hypotheses in each evaluation card, before any run.
- Wrote 86 original Dutch behavioural test sentences for the classifier.
- Finished one real analysis: the [coverage and power simulation](docs/ci_coverage_simulation.md).
  Synthetic speakers, assumed variances. Clip-level bootstrap covers 53-56% at 15 clips per
  speaker and 74% at 5; speaker-level covers 92-95%. 500 clips from 100 speakers give about 47%
  power for a 1-point WER gap.

### Not done, and why

**No real model or dataset has been run.** This cloud session could reach PyPI but not
huggingface.co or download.pytorch.org (the egress proxy refused them), so no checkpoints and no
DBRD. I did not look for mirrors. Every performance section says "pending" on purpose.

Not verified against reality yet, so expect small fixes on first contact:

- `from_common_voice_tsv` and `build_manifest` assume the classic Common Voice layout (`test.tsv`
  with `client_id`, `path`, `sentence`, plus `clips/`). The Data Collective archive may differ; I
  couldn't read the dataset page's licence or field list either (it renders client-side).
- `datacollective.download_dataset(..., download_directory=...)`: the keyword is unverified
  (the SDK README shows only the positional id). Check it first. SDK is pre-1.0 and warns of breaking changes.
- Real checkpoints: `pdelobelle/robbert-v2-dutch-base`, Whisper and open_clip loading untested.
- `clip_search/Dockerfile` was never built (no Docker daemon here). `docker compose config` passes.
- The CI template in `ci/` has never run.
- Timing guesses in the READMEs are estimates.

### TODO, in priority order

1. `python -m text_nl.cli --out runs/baseline --baseline-only`: the fastest first real result, and
   it runs the data audit. Then the fine-tune.
2. `asr_nl` laptop run on 1000 clips. Fix any Common Voice parsing issues; map free-text accents to
   groups; replace the simulation's assumed variances with measured ones and rerun it.
3. `asr_nl` full run on Kaggle (hypothesis 1: `large-v2` vs `large-v3`).
4. `clip_search` full run, then a demo index.
5. Copy curated reports to `results/`, fill in the cards, keep the wrong hypotheses visible.
6. Put a chart in each README: WER by condition, reliability diagram, mAP by language.
7. Extensions, best first: fine-tune Whisper small on Common Voice train and test on held-out
   speakers; run the behavioural set against a second base model; add Wav2Vec2 or Parakeet as a
   non-Whisper ASR comparison; try a small R notebook on `report.json` (mixed-effects model of WER
   with speaker as random effect) to cross-check the bootstrap; test video by sampling frames.

### Needs Baris

- [ ] **Allow `huggingface.co` and its CDN domains** (claude.ai → Settings → Capabilities), plus
      `download.pytorch.org` and `images.cocodataset.org` if overnight runs should do real work.
      Without this, a cloud session can only write and test code. GPU is absent here too, so
      CPU-feasible jobs only (baseline, small Whisper samples, small CLIP index).
- [ ] Create a Mozilla Data Collective account, accept the Common Voice Dutch terms, make an API
      key, export it as `MDC_API_KEY`. Check the licence on the dataset page. Don't commit it.
- [ ] Optional: copy `models/ci/forge-ci.yml` to `.github/workflows/`. This run stayed inside `models/`.
- [ ] Hugging Face account (for Spaces later). Note ZeroGPU needs an account older than 30 days.
- [ ] Run the free-GPU notebook, on a Kaggle account with phone verification for GPU/internet.

### Earning money: honest notes

None of this is income tonight, and nothing here has been tested with a paying customer. Prices
and demand below are unverified guesses, and I found no current prize competition that fits.

| Idea | Realistic? | Notes |
| --- | --- | --- |
| Paid "Dutch speech-to-text audit": run `asr_nl` on a client's own audio, report where it fails | Best fit, still modest | Niche but real for vendors of minutes, transcription and subtitles. The harness takes any manifest. Needs real results as proof, then outreach. Client audio is personal data: needs a processing agreement, local processing, and care. Weeks of sales for each small job. |
| Freelance NLP evaluation / fine-tuning | Plausible with a track record | The repo is a portfolio piece. Income depends on networking, not on this code. |
| Self-hosted Dutch transcription service | Possible, weak margins | Privacy is the pitch, but Whisper wrappers are commodity and support is real work. |
| Hugging Face Space demo | Not income by itself | Free accounts get 2 ZeroGPU Spaces, 5 min/day per signed-in visitor; PRO gets more. It is a shop window. |
| Selling a model trained on DBRD | **No** | CC BY-NC-SA: non-commercial. Retrain on commercially usable data first. |
| Public COCO demo as a product | **No** | Images keep Flickr licences. Switch to a CC0 collection first. |
| Kaggle or bounties | Low odds, separate from here | Expected earnings are near zero for most entrants. Belongs to `kaggle/`. Not researched in this run. |

### Useful references found

- Common Voice left Hugging Face for [Mozilla Data Collective](https://mozilladatacollective.com/)
  in October 2025 ([notice](https://huggingface.co/datasets/mozilla-foundation/common_voice_17_0)).
- [CLIN 34 abstract](https://clin34.leidenuniv.nl/abstracts/evaluating-the-state-of-the-art-automatic-speech-recognition-systems-for-dutch/):
  Whisper large-v2 + VAD beat large-v3 + VAD on Dutch.
- [Lathouwers et al., arXiv:2605.28833](https://arxiv.org/pdf/2605.28833): fine-tuning cut Whisper WER
  on Dutch child speech from about 17% to about 5.5% on low-noise data.
- [ZeroGPU docs](https://huggingface.co/docs/hub/spaces-zerogpu) for quotas and limits.
