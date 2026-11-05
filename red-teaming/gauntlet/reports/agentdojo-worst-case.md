# Policy layer on AgentDojo

Benchmark `v1.2.2`, mode `worst-case`.

> **No language model was involved.** The agent replays AgentDojo's ground-truth calls and obeys every injection it sees. ASR here means "what still gets through once the model is fully hijacked", not how often a model gets hijacked. AgentDojo's own `utility()` and `security()` did the scoring.

Of 949 (user task, injection task) pairs, 609 expose the injection to the agent and 566 of those succeed with no policy. Rates use those 566 pairs, so the `none` row is 100% by construction. Wilson intervals are in the JSON; pairs share tasks, so they are too narrow.

| Policy | ASR | Utility under attack | Benign utility |
| --- | ---: | ---: | ---: |
| none | 100.0% (566/566) | 42.2% (239/566) | 100.0% (97/97) |
| allowlist | 20.0% (113/566) | 94.3% (534/566) | 100.0% (97/97) |
| contacts | 27.7% (157/566) | 81.8% (463/566) | 96.9% (94/97) |
| provenance | 16.8% (95/566) | 68.6% (388/566) | 76.3% (74/97) |
| readonly-after-read | 12.4% (70/566) | 47.3% (268/566) | 50.5% (49/97) |
| allowlist+contacts | 8.1% (46/566) | 94.2% (533/566) | 96.9% (94/97) |

## ASR and benign utility by suite

| Policy | banking | slack | travel | workspace |
| --- | --- | --- | --- | --- |
| none | 100.0% (143/143) / 100.0% (16/16) | 100.0% (105/105) / 100.0% (21/21) | 100.0% (118/118) / 100.0% (20/20) | 100.0% (200/200) / 100.0% (40/40) |
| allowlist | 32.2% (46/143) / 100.0% (16/16) | 40.0% (42/105) / 100.0% (21/21) | 5.9% (7/118) / 100.0% (20/20) | 9.0% (18/200) / 100.0% (40/40) |
| contacts | 10.5% (15/143) / 93.8% (15/16) | 60.0% (63/105) / 95.2% (20/21) | 33.1% (39/118) / 95.0% (19/20) | 20.0% (40/200) / 100.0% (40/40) |
| provenance | 10.5% (15/143) / 87.5% (14/16) | 18.1% (19/105) / 28.6% (6/21) | 17.8% (21/118) / 100.0% (20/20) | 20.0% (40/200) / 85.0% (34/40) |
| readonly-after-read | 10.5% (15/143) / 56.2% (9/16) | 14.3% (15/105) / 4.8% (1/21) | 0.0% (0/118) / 70.0% (14/20) | 20.0% (40/200) / 62.5% (25/40) |
| allowlist+contacts | 0.0% (0/143) / 93.8% (15/16) | 38.1% (40/105) / 95.2% (20/21) | 3.4% (4/118) / 95.0% (19/20) | 1.0% (2/200) / 100.0% (40/40) |
