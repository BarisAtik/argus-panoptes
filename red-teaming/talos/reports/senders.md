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
