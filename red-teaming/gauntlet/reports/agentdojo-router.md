# Task router on AgentDojo

Benchmark `v1.2.2`. Same worst-case replay as [agentdojo-worst-case.md](agentdojo-worst-case.md), so **no language model was involved** and the agent obeys every injection it sees. Only the allowed tool list changes.

Thresholds were chosen on the other three suites for each scored suite, using tool recall only, aiming for 90% of tasks fully covered: `{"docs": {"banking": 0.05, "slack": 0.05, "travel": 0.05, "workspace": 0.05}, "history": {"banking": 0.1, "slack": 0.05, "travel": 0.05, "workspace": 0.05}, "blend": {"banking": 0.6, "slack": 0.6, "travel": 0.6, "workspace": 0.6}}`. Pairs share tasks, so Wilson intervals in the JSON are too narrow.

| Allowed tools | ASR | Benign utility | Tasks fully covered | Mean tools exposed |
| --- | ---: | ---: | ---: | ---: |
| gold | 16.3% (92/566) | 100.0% (97/97) | 100.0% (97/97) | 3.1 of 18.5 |
| gold+contacts | 4.4% (25/566) | 96.9% (94/97) | 100.0% (97/97) | 3.1 of 18.5 |
| no-router | 100.0% (566/566) | 100.0% (97/97) | 100.0% (97/97) | 18.5 of 18.5 |
| reads-only | 3.7% (21/566) | 41.2% (40/97) | 34.0% (33/97) | 11.5 of 18.5 |
| docs | 16.1% (91/566) | 73.2% (71/97) | 72.2% (70/97) | 12.7 of 18.5 |
| docs+contacts | 7.2% (41/566) | 72.2% (70/97) | 72.2% (70/97) | 12.7 of 18.5 |
| history | 51.4% (291/566) | 91.8% (89/97) | 90.7% (88/97) | 14.6 of 18.5 |
| history+contacts | 14.0% (79/566) | 90.7% (88/97) | 90.7% (88/97) | 14.6 of 18.5 |
| blend | 43.6% (247/566) | 95.9% (93/97) | 94.8% (92/97) | 14.1 of 18.5 |
| blend+contacts | 11.3% (64/566) | 93.8% (91/97) | 94.8% (92/97) | 14.1 of 18.5 |

## Frontier with the contact-book check

All suites at one threshold. A sweep, so it describes the method and does not select an operating point.

| Method | Threshold | ASR | Benign utility |
| --- | ---: | ---: | ---: |
| docs | 0.05 | 7.2% | 72.2% |
| docs | 0.1 | 4.4% | 52.6% |
| docs | 0.15 | 4.4% | 47.4% |
| docs | 0.2 | 4.2% | 44.3% |
| docs | 0.3 | 3.9% | 41.2% |
| docs | 0.4 | 3.7% | 41.2% |
| docs | 0.5 | 3.7% | 41.2% |
| docs | 0.6 | 3.7% | 41.2% |
| docs | 0.8 | 3.7% | 41.2% |
| history | 0.05 | 14.1% | 90.7% |
| history | 0.1 | 12.5% | 88.7% |
| history | 0.15 | 10.4% | 87.6% |
| history | 0.2 | 8.8% | 84.5% |
| history | 0.3 | 7.8% | 77.3% |
| history | 0.4 | 5.7% | 69.1% |
| history | 0.5 | 4.6% | 60.8% |
| history | 0.6 | 4.1% | 55.7% |
| history | 0.8 | 3.7% | 42.3% |
| blend | 0.05 | 18.6% | 94.8% |
| blend | 0.1 | 17.7% | 94.8% |
| blend | 0.15 | 16.8% | 94.8% |
| blend | 0.2 | 15.7% | 93.8% |
| blend | 0.3 | 14.5% | 93.8% |
| blend | 0.4 | 12.9% | 93.8% |
| blend | 0.5 | 12.4% | 93.8% |
| blend | 0.6 | 11.3% | 93.8% |
| blend | 0.8 | 9.5% | 85.6% |
