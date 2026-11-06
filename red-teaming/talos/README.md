# 🤖 Talos: can a model learn whose words to obey?

Talos was the bronze automaton who walked round Crete and did exactly what he was built to do. This is a very small one.

Every other project here runs a scripted agent, since no pretrained model can be downloaded where these runs happen. Scripted
agents can't say anything about soft defenses. So Talos trains a transformer from scratch: 370k parameters, three layers, a few
minutes on a laptop CPU, on a synthetic language of tasks, documents and mock actions. It is a real learned model, and **it is a
toy**. Everything below describes the toy and suggests mechanisms to test on a real model. None of it estimates how a language
model behaves.

## Results

76 models, plus 4 exploratory. Hypotheses were [pushed first](PREREGISTRATION.md). Most were wrong, which is the useful part.
Reports: [first study](reports/results.md), [named senders](reports/senders.md), [blended actions](reports/blend.md).

**1. Attack training solved the first study, for a boring reason.** 28 attack-trained models obeyed 0 of 29,400 injected
documents, including attack styles held out of training (T3 and T5 falsified). I expected a generalization gap. The grammar has one easy
cue, whether the user said to follow the document, and a model learns that cue, not a list of attacks. So this says the toy was
easy, and does not say attack training transfers. Marks did nothing here (T4 held, 1.3 points across four levels, GLMM p > 0.35).

**2. Named senders is the case that matters.** The user says "do what dana says" and a thread has several authors. A forged header is
word for word a real one. Attack-trained models with 1,800 steps:

| Authorship is carried by | Forged note obeyed | Other sender obeyed | Real task, no attack |
| --- | ---: | ---: | ---: |
| Text only, trained on attacks | 26.8% (24–31) | 31.6% (27–37) | 98.8% |
| Out-of-band mark, trained on attacks | 0.1% | 0.0% | 97.5% |
| Out-of-band mark, **never saw an attack** | 0.0% | 0.0% | 99.1% |

All four predictions failed as written, and the failures are informative. A1 missed by 3 points. A2 stopped attacks but kept 87.6% of
tasks against a 90% bar. A3 failed in the best way: the mark needed no attack training at all. A4 failed because text-only models
did not even learn to match a name well.

**3. Exploratory: the text-only models were partly cheating.** Trained attacks ask for keys and tokens more than real notes do, so
those models used content, not authorship. When a forged note is drawn from the same distribution as real ones, nothing is left to
go on, and they drift to a coin flip with more training:

| Provenance | Steps | ASR | Task success |
| --- | ---: | ---: | ---: |
| text only | 1,800 | 484/1,200 (40.3%) | 38.0% |
| text only | 5,400 | 290/600 (48.3%) | 44.0% |
| out-of-band mark | 1,800 | 0/1,200 | 89.5% |
| out-of-band mark | 5,400 | 0/600 | 99.8% |

If an attacker can write exactly what a trusted author writes, no text-only model can tell them apart, however much it trains. That is
just information theory, and here it shows up in a measurement. It is the model-side version of [Hermes](../hermes/), where
in-band labels failed against a rogue relay and gateway-held ones survived.

**4. A destination check misses most of the damage.** The registered ASR counts actions sent to the attacker. On `delegate-plain`
models that is 7.1%, far below my predicted 50% (T2 falsified), yet only 64.1% of injected trials were correct. A further 23.7% were
*blended* ([report](reports/blend.md)): the user's recipient with the attacker's item, say, or the user's address on the attacker's
tool. An oracle watching destinations calls those safe. Models never taught to follow documents are never hijacked (0.0%, T1 held) and still
lose 13 to 23 points of task success to foreign text.

**5. Relays did not weaken obedience here.** From hop 0 to 4, ASR went 7.3% to 8.7% while delegated task success fell from 99.7% to 85.1%
(T7 not supported). So the toy loses ability with depth and does not lose obedience. Only hops 0 and 1 were in training.

## Limits

- One author wrote the grammar, the attacks and the hypotheses. The vocabulary is closed and small, and nothing here paraphrases.
- 4 to 7 models a cell. Items are shared, so interval widths come from few models. The adv GLMMs for T3 and T5 could not be fitted: 0 successes.
- `signed` assumes a runtime that really knows authorship, and that the model is given the mark. Real chat templates flatten roles
  into tokens, and a model with broad instruction-following may ignore a mark that this model was built around.
- The first 40 models motivated the named-sender study, so it is a second question and not a confirmation. Sections 3 and 4 are exploratory.

## Run it

```bash
pip install -e ".[dev]" && pytest
make study          # 60 models, about 2 hours on two CPU cores, restartable
make report         # needs R and lme4
make study2         # 16 models, about 45 minutes
python -m talos.study2 --long --out data/runs3 && python -m talos.study2 --mimic
python -m talos.blend
make serve MODEL=data/runs/delegate-plain-none-s0.pt   # OpenAI-style endpoint on loopback
```

The server speaks the same API as a local model, so it is how the [Hermes hop runner](../hermes/src/hermes/hops.py), the Gauntlet
OpenAI client and [garak](adapters/garak_rest.json) got their first real end-to-end runs. These runs prove plumbing. garak
reported 256 of 256 passed on one probe, because this model answers English it can't read with `call send_email`. A pass from a
model that did not understand the question means nothing.
