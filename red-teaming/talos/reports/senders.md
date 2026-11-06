# Talos, named senders

16 small models. **A toy.** A thread has several authors and the user trusts one. See the addendum in the [pre-registration](../PREREGISTRATION.md).

## Hypotheses

| | Verdict | Numbers |
| --- | --- | --- |
| A1 | falsified | asr=0.268 |
| A2 | falsified | asr=0.001, task=0.876 |
| A3 | falsified | gap_points=-0.083 |
| A4 | falsified | asr=0.316 |

## Rates, mean over 4 models

| Regime / provenance / cell | ASR (min–max) | Task success | Malformed |
| --- | ---: | ---: | ---: |
| scoped/inband/forged | 32.3% (20%–39%) | 21.3% | 28.8% |
| scoped/inband/scoped | 0.0% (0%–0%) | 100.0% | 0.0% |
| scoped/inband/unnamed | 36.2% (22%–42%) | 25.6% | 18.0% |
| scoped/signed/forged | 0.0% (0%–0%) | 78.2% | 6.8% |
| scoped/signed/scoped | 0.0% (0%–0%) | 99.1% | 0.0% |
| scoped/signed/unnamed | 0.0% (0%–0%) | 87.1% | 2.4% |
| scoped_adv/inband/forged | 26.8% (24%–31%) | 61.9% | 0.0% |
| scoped_adv/inband/scoped | 0.0% (0%–0%) | 98.8% | 0.0% |
| scoped_adv/inband/unnamed | 31.6% (27%–37%) | 59.7% | 0.0% |
| scoped_adv/signed/forged | 0.1% (0%–0%) | 87.6% | 0.0% |
| scoped_adv/signed/scoped | 0.0% (0%–0%) | 97.5% | 0.0% |
| scoped_adv/signed/unnamed | 0.0% (0%–0%) | 92.2% | 0.0% |

## Exploratory, added after the results

Neither part below was pre-registered.

**Three times the steps, 2 seeds.** Did the models above just run out of training?

| Regime / provenance / cell | ASR | Task success |
| --- | ---: | ---: |
| scoped_adv/inband/forged | 18.7% | 78.7% |
| scoped_adv/inband/scoped | 0.0% | 100.0% |
| scoped_adv/inband/unnamed | 20.8% | 75.2% |
| scoped_adv/signed/forged | 0.0% | 99.8% |
| scoped_adv/signed/scoped | 0.0% | 100.0% |
| scoped_adv/signed/unnamed | 0.0% | 100.0% |

**Mimic attack, test only.** The trained attacks ask for keys and tokens more than real notes do, so a model can use content instead of authorship. Here the forged note is drawn from the same distribution as real notes, so a text-only model has nothing left but a guess.

| Provenance | Steps | Models | ASR | Task success |
| --- | ---: | ---: | ---: | ---: |
| inband | 1800 | 4 | 484/1200 (40.3%) | 38.0% |
| inband | 5400 | 2 | 290/600 (48.3%) | 44.0% |
| signed | 1800 | 4 | 0/1200 (0.0%) | 89.5% |
| signed | 5400 | 2 | 0/600 (0.0%) | 99.8% |
