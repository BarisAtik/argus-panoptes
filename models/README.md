# 🔥 The Forge — models

Tinkering with open models from the Hugging Face ecosystem using PyTorch, across speech, text
and images. The rule here: **a number only counts if it comes with how it could be wrong.**

| Project | Modality | Question | Status |
| --- | --- | --- | --- |
| [`asr_nl/`](asr_nl/) | 🎙️ audio | Where does Whisper break on Dutch: accents, noise, compounds, silence? | Pipeline tested; first real run pending |
| [`text_nl/`](text_nl/) | 📝 text | Can a small Dutch classifier be trusted beyond its accuracy score? | Pipeline tested; first real run pending |
| [`clip_search/`](clip_search/) | 🖼️ image | How much worse is image search when you ask in Dutch? | Pipeline tested; first real run pending |
| [`ner_nl/`](ner_nl/) | 🏷️ text | How far does a Dutch tagger travel beyond its home corpus? | Real run in progress on CoNLL-2002 |
| [`pii_nl/`](pii_nl/) | 🕵️ text | How much personal data survives Dutch redaction in chat, calls and notes? | **First real results**: 4.8% of values leak on blind synthetic templates, against 30.9% for spaCy lg |
| [`forge/`](forge/) | 🧰 shared | Cluster bootstrap and t intervals, calibration, ranking metrics, stamped reports | Done |

**Status means what it says.** `pii_nl` and `ner_nl` run real models; their numbers live in
[`results/`](results/). Speech, classifier and image projects are tested against tiny random
models only, and so have no performance results yet. The design behind them comes from a
[simulation](docs/ci_coverage_simulation.md) behind the
evaluation design: resampling clips instead of speakers can make a "95%" interval cover the
truth only about 55% of the time. A [second simulation](docs/small_group_coverage.md) shows that
even a speaker bootstrap covers only about 88% on a 10-speaker group, so small slices now use a
cluster t interval.

## Quick start

```bash
cd models
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,asr,text,vision]"
pytest                                     # no downloads, under a minute on CPU
bash scripts/first_results.sh text         # first real result: CPU, minutes
```

Each project README has the commands for the full experiment.
[`notebooks/run_on_free_gpu.ipynb`](notebooks/run_on_free_gpu.ipynb) runs any of them on a free
Kaggle or Colab GPU.

## House rules for experiments

- Hypotheses go in the project's evaluation card *before* the run, so Git history shows they came first.
- Uncertainty is computed at the level the data was collected (speakers, not clips).
- A baseline runs next to every model. Small groups are reported as too small, not as a number.
- Reports are stamped `real` or `smoke`; smoke output carries a banner and is never quoted.
- Only curated `results/*.md` get committed. Data, weights and `runs/` stay out of Git.

See [`PROGRESS.md`](PROGRESS.md) for what's next and [`CLAUDE.md`](CLAUDE.md) for how to continue.
