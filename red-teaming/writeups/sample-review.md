# Sample agent security review

This shows what a small review could look like. **Pigeon is invented.** There is no client, and no real product was tested. Pigeon
stands for the mock office assistant in [Gauntlet](../gauntlet/), and each number comes from a report in this repo, measured with a
scripted agent that obeys every injection. A real review would swap in the client's own tools, tasks and model, under a written scope.

## Scope

Pigeon reads mail, documents and web pages for a user, and can send mail, pay invoices, read secrets and keep notes. The question: if
someone else writes part of what Pigeon reads, what can they make it do, and which fixes pay for themselves?

## Summary

1. **Pigeon's text filter is not doing much.** It stopped 2 of 28 attack scenarios. Remove it from the risk story.
2. **Two rules give most of the protection.** Checking that destinations and amounts came from the user, and scoping secrets to the task,
   took a fully hijacked agent from 100% to 29% attack success, keeping 26 of 30 ordinary tasks.
3. **The full stack stops more, and is expensive to run.** Twelve defenses reach 11%. They keep 26 of 30 ordinary tasks, but only 23% of
   hard edge cases, such as sending a credential to its rightful owner. Plan who handles those.

## Results

| Stack | Attack success, dev (28 scenarios) | Attack success, blind (24) | Ordinary tasks kept (30) | Hard edge cases kept (13) |
| --- | ---: | ---: | ---: | ---: |
| none | 100% | 100% | 30/30 | 100% |
| text filter | 93% | 100% | 30/30 | 92% |
| provenance + scoped secrets | 29% | 42% | 26/30 | 92% |
| layered (12 defenses) | 11% | 8% | 26/30 | 23% |

The blind column is the one to trust. Stacks chosen on dev scores lost 8 to 13 points there, which is the usual price of picking winners on
your own test set. With this few scenarios, one scenario moves a rate by about 4 points.

## Recommendations, in order

| Priority | Change | Why | Cost seen |
| --- | --- | --- | --- |
| 1 | Check destinations and amounts against the user's own words | Largest single effect, 18 points by Shapley value | 3 amounts and 1 destination blocked in 30 ordinary tasks: offer a confirm step |
| 2 | Scope secrets to the task | 11 points by Shapley value | None seen on ordinary tasks |
| 3 | Add an egress allowlist | 15 points. Holds whatever the wording | 3 in 30 ordinary tasks, all missing entries. Someone must own the list |
| 4 | Keep human approval for what gets past | Three dev scenarios beat `layered`, including one that works on the human | Reviewer time |
| 5 | Do not buy a detector yet | A trained one stopped no more than the regex here | Saves money |

## What this review does not cover

- **No model was in the loop.** These figures say what controls still prevent once the model is fully hijacked. How often a model gets
  hijacked needs a separate test on the real one.
- One author wrote the dev scenarios. The blind sets were written by a separate session of the same kind of system.
- Scenarios are small, and 0 failures in 30 still allows a real rate of up to 11%.
- A real review needs the client's own tools and tasks. Rates do not transfer between products.

## Sources

[Worst case](../gauntlet/reports/worst-case.md), [frontier](../gauntlet/reports/frontier.md), [blind holdout](../gauntlet/reports/holdout.md),
[ordinary tasks](../gauntlet/reports/ordinary.md).
