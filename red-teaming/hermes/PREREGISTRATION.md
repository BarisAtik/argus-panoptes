# Pre-registration

Written before any experiment ran. Results go in `reports/`, and this file is not edited afterwards. Additions go
at the bottom, dated, and say that they came later.

## Question

Controls that work for one agent assume one agent sees everything. In an A2A mesh the untrusted input, the private
data and the outbound tool can sit in three different agents. What survives that split, what does it cost, and
does it matter how many hops there are?

## Design

A full factorial, not a sample. A cell is one attack path, run against every control stack:

| Factor | Levels |
| --- | --- |
| goal | exfiltrate canary, rogue payment |
| hops between private data and sink | 0, 1, 2, 3, 4 |
| encoding (exfil only) | verbatim, base64, rot13, words, chunks |
| reader of the leak | attacker address, allow-listed collector, task-granted partner |
| delegation edges | declared in the benign workflow, undeclared |
| adversary | hijacked model (runtime honest), rogue relay, rogue source |
| laundering | none, shared store between two tasks |

Hijacked means the model obeys the injection but the runtime around it still works. Rogue means the whole agent
belongs to the attacker: it strips metadata, skips its own hooks and drops context links. All traffic still crosses
the gateway. Cost is measured on benign control tasks through the same topologies.

Scored by a scripted worst-case agent, so results measure controls, never model behaviour. Grants come from the
text of the user's task plus a contact book, not from a gold list.

## Hypotheses

- **H1, split trifecta.** `agent_trifecta` stops hop-0 attacks and stops none at 1+ hops, since no single agent
  holds all three legs. Falsified if it stops any attack at 1+ hops.
- **H2, DLP.** `agent_dlp` stops verbatim, base64 and rot13, and stops neither words nor chunks, with no effect of
  hops. Falsified if a stop rate depends on hops.
- **H3, egress is about destination only.** `agent_egress` stops all attacker-destination cells and no collector or
  granted-partner cells.
- **H4, capabilities.** `caps` stops attacker and collector cells at every hop, including rogue relays, and stops
  no granted-partner cell.
- **H5, label custody.** Against a rogue relay, in-band labels fail and gateway-held labels hold only if they do
  not rely on context links. Predicted ASR order: `taint_inband` > `taint_lineage` > `taint_hwm`.
- **H6, storage.** The shared store launders labels past `taint_inband` and `taint_lineage` but not `taint_hwm`.
- **H7, rogue source.** No label scheme stops a rogue source whose tool reads the gateway cannot see. This is a
  limit, not a bug, and is pinned by a `_gap` test.
- **H8, cost.** `taint_hwm` has the lowest control utility of the label schemes. `typed_declass` recovers at least
  a third of what it loses. Falsified if recovery is below a third.
- **H9, typed channels.** A typed reply that declassifies private data leaks at most
  `calls × log2(|type|)` bits, and a call budget caps it exactly. They limit the rate, they do not stop the leak.

## Primary comparison

ASR over all attack cells and control utility for: `none`, `agent_egress`, `agent_dlp`, `agent_trifecta`,
`peer_acl`, `caps`, `taint_inband`, `taint_lineage`, `taint_hwm`, `perimeter`, `identity`, `full`.

## Holdout

After the controls are frozen, a separate author session writes a set of attacks and controls from the DSL docs,
without reading `controls.py`, this file's predictions or any report. It is scored once. Tuning on it turns it into
dev data. The author is the same kind of system as me, so it is blind, not independent.

## Limits known in advance

I wrote both the attacks and the controls, so the factorial shows where logic has holes, not how likely an
attack is. The hop-attenuation question (does a real model obey a relayed instruction?) cannot be answered without
a model, and this sandbox has none.
