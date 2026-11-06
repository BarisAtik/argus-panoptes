# ⚕️ Hermes: trust across agent boundaries

Hermes is the messenger who talked Argus to sleep and then killed him. This lab asks the same question of agent
meshes: what happens to a watcher when the danger arrives as a message from a colleague?

Controls built for one agent assume one agent sees everything. On A2A, the untrusted input, the private data and the
outbound tool can sit in three different agents, and each of them looks fine alone. Hermes measures what survives that
split, using the real A2A SDK, mock tools and fake canaries. Nothing here touches a real system.

**No language model has been run.** A scripted worst-case agent drove every trial, so results measure controls.
They say nothing about how often a model obeys a relayed instruction.

## Results

782 factorial attack cells, 64 benign cells, 17 protocol-surface attacks and 6 surface controls.
[Full report](reports/experiment.md), [inference and typed forwards](reports/inference.md),
[frontier](reports/frontier.md), [holdout](reports/holdout.md),
[hypotheses, written first](PREREGISTRATION.md).

| Stack | Factorial ASR | Surface attacks | Benign tasks, dev | Benign tasks, blind |
| --- | ---: | ---: | ---: | ---: |
| `none` | 100% | 17/17 | 100% | 16/16 |
| `agent_trifecta` | 98.1% | 17/17 | 100% | not scored |
| `perimeter` (egress, DLP, trifecta) | 28.9% | 12/17 | 100% | 10/16 |
| `caps` | 35.3% | 10/17 | 87.5% | 13/16 |
| `identity` (ACL, caps, cards, push, human gate) | 22.5% | 6/17 | 87.5% | 12/16 |
| `taint_lineage` + types | 80.4% | 12/17 | 75.0% | 14/16 |
| `taint_hwm` + types | 10.2% | 12/17 | 50.0% | 13/16 |
| `full` | 2.3% | 5/17 | 50.0% | 7/16 |
| `full_lineage` | 9.2% | 5/17 | 75.0% | 7/16 |
| `taint_inferred` + types | 55.1% | 12/17 | 75.0% | not scored yet |
| `full_inferred` | 7.5% | 5/17 | 75.0% | not scored yet |
| `hwm_typed_fwd` | 10.2% | 12/17 | 62.5%* | not scored yet |
| `full_fwd` | 2.3% | 5/17 | 62.5%* | not scored yet |
| `full_inferred_fwd` | 7.5% | 5/17 | 87.5%* | not scored yet |

\* The same 64 tasks with `input` types declared, so these rows are not on quite the same cells as the rest. The 782
cells do not include the 102 deferred cells, which flatters the inferred rows. See finding 9 and
[the inference report](reports/inference.md).

Dev rates are exact counts over a space I designed, not estimates of anything in the wild. The factorial's ASR is
weighted by that design, so compare stacks and do not quote it. The blind set has wide intervals: 7/16 is 23 to 67%.

## What it found

1. **The trifecta rule fails on the first hop.** It stops all 15 unlaundered hop-0 exfiltration cells and nothing at 1+ hops (0 of 748),
   because no single agent holds all three legs.
2. **Hop count barely matters after that.** Most stacks are flat from 2 to 4 hops. That is partly the method: a
   scripted agent always obeys, so any real attenuation by a model cannot show up here.
3. **Who holds the labels decides everything.** Against a rogue relay, in-band metadata and gateway lineage both fail
   102 of 102 cells. I predicted lineage would do better (H5, falsified): it trusts the rogue to report the link. Per-agent
   high-water marks held all 102.
4. **Stronger labels are paid for in ordinary work.** `taint_hwm` keeps 37.5% of dev tasks. Typed outputs win back
   only 8 of the 40 lost (H8, falsified), since they only work on replies, not on chained forwards or sticky sessions.
5. **Labels need something to label.** The factorial's rogue source lost 160 of 240 cells to `taint_hwm`, which
   falsified H7, but only because labelled traffic woke it. A patient rogue acting from a clean context beat `full`
   outright (`rogue-source-clean-context`).
6. **A signature proves authorship, not honesty.** `card_sig` catches unsigned and tampered cards and passes a signed
   liar. `card_pin` stops that, and also blocks honest updates and new agents, since a hash cannot see intent.
7. **Types cap the rate of a leak, they do not stop it.** A validated enum leaked exactly
   `min(64, calls × log2|T|)` bits in all 20 settings. A call budget caps it exactly.
8. **Dev utility did not survive contact with a new author.** The cheap frontier pick (egress, DLP, peer map) fell
   from 98.6% to 9/16, and the heavier pick rose from 52.9% to 12/16. Five of its seven breaks are named contacts missing
   from the org allowlist, which my dev tasks had quietly kept in step. So this measures allowlist upkeep as much as
   the control, and it is the cost a real team would pay if the two drift. The 25-point edge of lineage over high-water marks in `full` vanished too: both 7/16.

9. **Inferring links beats a rogue relay until it learns to wait.** A gateway that links any send made while a request
   is open stopped all 102 immediate rogue-relay cells that beat lineage. A relay that answers first and sends after the
   request closes won all 102 back. High-water marks stopped both. In a full stack that is 0 of 102 immediate and 9 of 102
   deferred, the same 9 as `full_lineage`. Inference also keeps the sticky tasks that high-water marks lose (40 of 64
   against 24), and its own cost is a false link when requests overlap: it kept 1 of 3 parallel tasks to lineage's 3. It
   does not reach the store.
10. **Typed forwards pay for chains, and bring the type's weakness along.** With `input` types, `hwm_typed_fwd` wins back
   16 of the 40 tasks `taint_hwm` loses, up from 8, which clears the bar H8 missed. But a value chosen inside the type
   now beats `full_fwd` where `full` stopped it (`typed-forward-tamper`), a forward leaks exactly
   `min(64, calls × log2|T|)` bits in all 20 settings, and a declared 64-bit `int` carries the whole canary in one call.
   The gateway checks a value against a type. It does not judge the type.

All nine predictions for these two findings (H10 to H18) held exactly. I made them by reading my own deterministic mesh,
so that shows the code does what I reasoned, not that the design holds up.

11. **A second blind set was harder still.** On 20 ordinary mesh tasks from a new author ([report](reports/holdout2.md)), `full`
   kept 4/20 (8 to 42%), and `caps` and `identity` 11/20. All nine `caps` breaks are `caps:dest`: the destination was
   not named in the user's words or the contact book. `taint_inferred` kept 9/20. Inference cost no more than the
   other label schemes here: `full`, `full_lineage` and `full_inferred` all kept 4/20.

## Nothing here stops

`full` loses to five surface attacks, pinned by `_gap` tests: injection that leaks into a granted internal mailbox,
memory worms (labels only mark them), leaks through the final reply, a value chosen inside a declared type, and the
clean-context rogue above. Replies need rendering controls and types need range checks against the task. The rest
needs a human or a different architecture.

## A real model, when there is one

[`hops.py`](src/hermes/hops.py) puts the open question to a local OpenAI-style model: does it obey a relayed instruction
less at each hop? It also asks whether the model still follows a delegated instruction at that hop, since a model that
simply loses the thread is not defended. Its path has run once end to end, against one small [Talos](../talos/) model
through its loopback server. That proves the plumbing and nothing about a language model.

## Limits

- **The second blind set cannot test the new ideas.** It has no `input` types and no `parallel` steps, so `_fwd` stacks equal
  their base stacks there, and it says nothing about typed forwards or false links. It does show ordinary cost.
- **No blind attack set.** The separate author session was stopped by an automated safety check while writing the
  attacks, and I did not retry that content. Attack numbers are dev only. I wrote both the attacks and the controls.
- Only the benign half was tested blind, by the same kind of system as me, which also chose its own grants.
- `rogue` assumes all traffic crosses the gateway. An agent with a side channel is out of scope.
- `grants` come from the task text and a contact book. A rephrased task can change them.
- Push callbacks travel in message metadata rather than through the SDK's push config API.
- Direct and A2A transports agreed on all 448 checked scenario and stack pairs, a sample and not the whole matrix.
  The frontier and factorial run on the direct transport.

## Run it

```bash
pip install -e ".[dev]" && pytest      # 155 tests
make experiment                        # seconds
make inference                         # seconds, H10 to H18
make frontier                          # 4,096 stacks, about 8 minutes on two cores
make wire                              # surface scenarios over real A2A on loopback
make holdout2                          # spent: refuses to overwrite its report
make hops MODEL=name                   # hop attenuation on a real local model
hermes lint card.json --sarif out.sarif
hermes run --scenarios my.yaml --stacks none,full
```

Scenario format: [`docs/DSL.md`](docs/DSL.md). `hermes lint` is structural on purpose: a tidy, lying card passes.

## Background

[Agent Card poisoning](https://keysight.com/blogs/en/tech/nwvs/2026/03/12/agent-card-poisoning) (Keysight) and
[what signing does not prove](https://dev.to/indra_gustiprasetya_a80a/a2a-agent-card-poisoning-signed-but-lying-1lod)
informed the card scenarios. [A survey of A2A gaps](https://grith.ai/blog/a2a-protocol-zero-defenses-prompt-injection)
names session smuggling and the missing consent state, and reports no measurements. Label ideas come from
[CaMeL](https://arxiv.org/abs/2503.18813) and [FIDES](https://arxiv.org/abs/2505.23643).
