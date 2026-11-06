# 100% on dev, 5% on holdout

*Notes from a hobby lab on testing AI agent defenses. Everything ran locally against mocks and fake
canary tokens.*

I built a scanner for poisoned MCP tool descriptions and it scored 100% on my test set. On a fresh
set, written after the rules were frozen, it caught 2 of 25. I then improved it, the failed set went
to 88%, and I felt good for about an hour. On another fresh set it caught 1 of 20.

Nothing was broken. Pattern matching had done what it does: it memorised the last examples it saw.
This post is about the habit that exposed that, and three more places where the same habit changed
the answer.

## The habit

Freeze the system. Write the test afterwards, ideally through someone who cannot see the system. Score
once. If you look at the failures and tune, the set is now dev data, so write a new one.

That sounds fussy until you see the size of the gap:

| Version | Dev recall | Fresh holdout recall |
| --- | ---: | ---: |
| mcp-lens 0.1 | 100% (21/21) | 8% (2/25) |
| mcp-lens 0.2 | 100% (21/21), 88% (22/25) on the old holdout | 5% (1/20) |

The holdouts are small, one author wrote them, and they lean adversarial, so 5% is not a rate for
attacks in the wild. Blunt poisoning, invisible Unicode and rug pulls are still caught well. The honest
description of the tool is "cheap hygiene check". Without the second holdout I would have called it
a defense.

## Same habit, bigger system

The Gauntlet is a harness for agents with mock tools. Its layered policy stack stopped 25 of 28
attacks on dev, and 22 of 24 on a blind holdout written by a separate session with no view of the
defense code. That is a rare case of a score surviving. A rule on what an action may do does not
care how an injection is worded.

The same table had a number I had been stepping around: **control utility of 23%**. Controls are
harmless tasks placed near each rule, so they are harsher than normal work, but a stack that breaks
three of four is not a stack anyone keeps.

Leave-one-out analysis did not help. Remove one defense from twelve and little moves, because
neighbours cover for each other. So I ran all 8,192 subsets of 13 defenses and computed exact Shapley
values, which share credit among overlapping controls instead of giving each one zero.

| Stack | Defenses | Dev attack success | Dev control utility | Holdout attack success | Holdout control utility |
| --- | ---: | ---: | ---: | ---: | ---: |
| none | 0 | 100% | 100% | 100% | 100% |
| layered | 12 | 10.7% | 23.1% | 8.3% | 25.0% |
| picked: utility at least 90% | 2 | 28.6% | 92.3% | 41.7% | 87.5% |
| picked: utility at least 75% | 3 | 21.4% | 76.9% | 29.2% | 62.5% |

Two things stand out. A two-defense stack gets most of the way there: requiring that outgoing destinations come from the user, plus
secrets scoped to what the user named. And selection did what selection always does. Picking the best
stack on dev cost 13 points of attack success and 5 of utility when it met the holdout. The first row
of a sorted table is always flattered.

The Shapley table also found defenses that cost as much as they buy. `exec_guard` buys 7 points of
attack success for 15 points of control failure, the most expensive line in the table, with intervals
so wide the honest reading is "depends on your workload". Several others, such as `memory_guard` and
`manifest_scan`, buy under a point on this set. That may mean the set lacks scenarios for them,
which is a statement about my scenarios as much as about the defense.

## Evaluators have bugs too

The worst mistakes were not in the defenses. A plain substring check for the canary missed 6 of 84
successful attacks, because the agent had encoded the secret first. A naive evaluator calls those
stopped. In the AgentDojo bridge, blocked tool calls were still counted as successful attacks by
trace-based checks, which ran the other way. Two oracles in my own scenarios could never fire, which
would have shown up as a perfect defense.

Each attack now has to fire against an agent that obeys everything, and each task has to be solvable,
before any defense is scored. A dead test and a perfect defense look the same from the outside.

## What about a trained detector?

Phrase lists fail, so train one. Tripwire is a small PyTorch byte-level CNN, with TF-IDF and a regex as
baselines, on injection text from AgentDojo, garak, PyRIT and PromptInject. The threshold is set on
validation data for 1% false positives.

| Test | Recall | False positives |
| --- | ---: | ---: |
| Held-out templates | 93% | 1.1% |
| Held-out publisher, averaged | 58% | 10.6% |
| Gauntlet scenarios stopped, dev | 2 of 28 | |
| Gauntlet scenarios stopped, holdout | 1 of 24 | |

The usual warning about leakage turned out to be the smaller effect here: 94% of test payloads in a
naive split also appear in training, yet naive and grouped scores nearly matched. Meeting a new author
was the problem. The false-positive rate I asked for missed by a factor of ten, because a threshold is a
statement about the data it was set on. On the Gauntlet's lines the AUROC was 0.58 and 0.70, so there was
little signal for a better threshold to find. The plain TF-IDF baseline did about as well as the CNN.

Then I tested spelling changes, and a bad metric nearly fooled me. Training on obfuscated payloads pushed
recall on those rewrites to 100%. It also flagged over 99% of benign text with the same rewrites. The
model had learned "odd characters mean attack". The plain CNN "caught" 74% of base64 payloads while
flagging 87% of base64 benign documents, which is worse than a coin. A four-line normaliser (NFKC, drop
format characters, fold look-alikes, close up s p a c e d text) restored 93% with no retraining and no
false-positive cost. That one needs a small caveat: my base64 rewrite adds a sentence asking the reader to
act on the note, even to benign text, so some of those flags are arguably fair.


## What I would tell someone starting out

- Put the control on the action, not on the text. Assume some injection lands.
- Report the cost next to the benefit, in the same table.
- Keep a holdout, and retire it when you have learned from it.
- Test the evaluator first. Then split by template or source, not by row.
- Say what the number does not cover. Every result here is a scripted worst-case agent or a detector
  on public benchmark text. No language model has been through this harness yet, so none of this says
  how often a real model falls for anything. That run is next.

Code, reports and all failed scores are in [`red-teaming/`](../). Figures trace to
[`gauntlet/reports/`](../gauntlet/reports/), [`mcp-lens/reports/`](../mcp-lens/reports/) and
[`tripwire/reports/`](../tripwire/reports/).
