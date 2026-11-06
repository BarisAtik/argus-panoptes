# The lethal trifecta has a loophole: three agents

*A blog-style post. Numbers trace to [`hermes/reports/`](../hermes/reports/experiment.md).*

The usual rule for agent safety is simple. Don't let one agent read untrusted content, hold private data and talk to
the outside world at once. It's a good rule. I wanted to know what it does in a mesh, so I built a lab where those
three legs sit in three different agents, talking over the real A2A protocol, and ran every path I could enumerate.

The rule stopped every direct single-agent exfiltration. From one hop up it stopped none of 748 attack cells. Nothing was
broken. Each agent really did hold fewer than three legs.

## Who holds the label?

The obvious fix is to carry taint labels across the boundary. I compared three ways of holding them: in message
metadata, at a gateway following context links, and at a gateway per agent for the whole session. I expected the
gateway with links to beat metadata. It didn't. Against one rogue relay, both failed all 102 cells, because links are
something the agent reports. Moving a label somewhere safer doesn't help if the attacker still supplies the input to it.

Per-agent marks held all 102. They also blocked over half of my benign tasks, because the label never comes off. A
web page read on Monday stops a rent payment on Tuesday.

## The numbers I trusted least

On my own benign tasks, a cheap stack of egress allowlist, DLP and a peer map looked close to free at 98.6%. Then a
separate session wrote 16 fresh tasks, without seeing any of this, and it passed 9. A heavier stack I had written off
passed 12. Five of its seven failures were people in the contact book who weren't on the allowlist. My own tasks had quietly kept
those two lists in step. Nobody decided that. It's just what happens when one person writes the test and the defense.

That's the result I'd pass on. Security costs measured on your own tasks are a guess. Have someone else write them.

## What I'd actually do

- Treat every peer as third-party input, including your own.
- Put destinations in a task-bound capability, so a hijacked agent can't widen them.
- Register peers, and treat card text as data. A signature tells you who lied.
- Use narrow types where you can, and budget the calls. A yes/no answer still leaks a secret one bit at a time.
- Decide what happens at the end of a session. That's where sticky labels hurt.

## What this doesn't show

No language model ran. A script obeyed every instruction, so this says what controls do at worst, not how likely any
of it is. Attack cells were written by me, and I have no blind attack set: the session writing one was stopped by
an automated safety check and I left it there. And five attacks beat the strongest stack, including a patient rogue
agent that gives the gateway nothing to label. Labels only track what they can see.
