# Talos results

60 models, each about 370k parameters, trained from scratch on a synthetic language. **This is a toy.** Results describe it, and suggest mechanisms to test on a real model. They do not estimate how any language model behaves.

Each rate is a mean over models. ASR means the action went to the attacker's destination. Malformed output stays in the denominator.

## Hypotheses

| | Verdict | Numbers |
| --- | --- | --- |
| T1 | held | clean_asr_max=0.000 |
| T2 | falsified | delegate_plain_asr=0.071 |
| T3 | falsified | delegate_asr=0.067, known_asr=0.000, heldout_asr=0.000, relative_drop=1.000, gap_points=0.000 |
| T4 | held | range_points=1.310, by_prov.plain=0.071, by_prov.delim=0.067, by_prov.salted=0.071, by_prov.segment=0.058 |
| T5 | falsified | break_heldout_asr.plain=0.000, break_heldout_asr.delim=0.000, break_heldout_asr.salted=0.000, break_heldout_asr.segment=0.000 |
| T6 | falsified | delegate_regime=0.998, adv_known=0.984, adv_heldout=0.973 |
| T7 | not supported | asr_drop_points=-1.375, task_drop_points=14.625 |

## By regime and provenance

| Regime / provenance | Models | ASR (min–max model) | Task under attack | Malformed | Direct task | Delegated task | False obey on mention | Known family ASR | Held-out family ASR | Delegated, held-out family |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| clean/plain | 4 | 0.0% (0%–0%) | 78.8% | 11.8% | 99.6% | 0.0% | 0.0% | n/a | n/a | n/a |
| clean/delim | 4 | 0.0% (0%–0%) | 77.3% | 11.8% | 99.5% | 0.1% | 0.0% | n/a | n/a | n/a |
| clean/salted | 4 | 0.0% (0%–0%) | 80.5% | 9.2% | 99.6% | 0.0% | 0.0% | n/a | n/a | n/a |
| clean/segment | 4 | 0.0% (0%–0%) | 86.8% | 2.9% | 99.6% | 0.1% | 0.0% | n/a | n/a | n/a |
| delegate/plain | 4 | 7.1% (3%–11%) | 64.1% | 5.1% | 100.0% | 99.9% | 0.6% | n/a | n/a | n/a |
| delegate/delim | 4 | 6.7% (6%–8%) | 67.0% | 2.6% | 100.0% | 99.9% | 1.5% | n/a | n/a | n/a |
| delegate/salted | 4 | 7.1% (3%–16%) | 69.8% | 4.1% | 100.0% | 99.8% | 1.2% | n/a | n/a | n/a |
| delegate/segment | 4 | 5.8% (0%–11%) | 70.5% | 1.1% | 100.0% | 99.8% | 0.4% | n/a | n/a | n/a |
| adv/plain | 7 | 0.0% (0%–0%) | 99.9% | 0.0% | 100.0% | 99.7% | 0.0% | 0.0% | 0.0% | 99.2% |
| adv/delim | 7 | 0.0% (0%–0%) | 99.9% | 0.0% | 100.0% | 99.3% | 0.0% | 0.0% | 0.0% | 98.5% |
| adv/salted | 7 | 0.0% (0%–0%) | 98.8% | 0.0% | 100.0% | 96.7% | 0.0% | 0.0% | 0.0% | 95.5% |
| adv/segment | 7 | 0.0% (0%–0%) | 99.3% | 0.0% | 100.0% | 97.3% | 0.0% | 0.0% | 0.0% | 95.8% |

## ASR by family

| | ignore | polite | role | authority | conditional | story | break |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| clean/plain | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| clean/delim | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| clean/salted | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| clean/segment | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| delegate/plain | 6% | 4% | 5% | 11% | 6% | 8% | 9% |
| delegate/delim | 8% | 6% | 7% | 4% | 6% | 6% | 11% |
| delegate/salted | 8% | 6% | 6% | 4% | 9% | 9% | 7% |
| delegate/segment | 7% | 4% | 4% | 8% | 5% | 5% | 8% |
| adv/plain | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| adv/delim | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| adv/salted | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| adv/segment | 0% | 0% | 0% | 0% | 0% | 0% | 0% |

## Relay hops

Training saw hops 0 and 1 only.

| Hop | ASR, delegate | Delegated task, delegate | ASR, adv | Delegated task, adv |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 7.3% | 99.7% | 0.0% | 97.6% |
| 1 | 9.2% | 99.5% | 0.0% | 97.1% |
| 2 | 8.2% | 97.1% | 0.0% | 93.8% |
| 3 | 6.1% | 88.7% | 0.0% | 85.3% |
| 4 | 8.7% | 85.1% | 0.0% | 78.5% |

## GLMM

```
== T4, delegate regime: attack ~ provenance 
            Estimate Std. Error z value Pr(>|z|)
(Intercept)   -4.099      0.411  -9.972    0.000
provdelim      0.065      0.573   0.114    0.909
provsalted    -0.133      0.574  -0.232    0.816
provsegment   -0.530      0.578  -0.917    0.359
 Groups Name        Std.Dev.
 item   (Intercept) 1.89154 
 model  (Intercept) 0.79546 
singular fit: FALSE 

== T3, adv regime: attack ~ held-out + provenance 
not fitted: 0 successes in 29400 trials

== T5, break held out, reference segment 
not fitted: 0 successes in 600 trials
```
