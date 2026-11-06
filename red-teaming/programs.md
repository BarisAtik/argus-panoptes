# 💰 Paid programs and competitions

Checked on 6 November 2026. Rules and dates change, so read the official page before acting.
Nothing here has been entered; see "Needs Baris" in [PROGRESS.md](PROGRESS.md).

## Competitions

| What | Prize | Status | Notes |
| --- | ---: | --- | --- |
| [Gray Swan: Indirect Prompt Injection Black](https://app.grayswan.ai/arena/challenge/ipi-black-2026?panel=rules) | $300,000 total, $100,000 per wave, split evenly between white-box and black-box | **Wave 3 live, 2 to 12 Nov 2026. Ends 12 Nov, 10:00 PT** | The [Arena page](https://app.grayswan.ai/arena) shows 10 scenarios and 42 models, about a week left on 6 Nov. This settles the date conflict noted on 5 Nov. |
| [Gray Swan: The Labyrinth, Challenge Edition](https://app.grayswan.ai/arena) | None shown | Live | 4 scenarios, 4 models. No dates or prize on the Arena page. |
| [Gray Swan: Proving Ground](https://app.grayswan.ai/arena/challenge/proving-ground) | None listed | Free practice | Weekly drops across indirect, agent, chat and image formats. The right on-ramp. |
| [Gray Swan: Lucky Break Agent Direct](https://app.grayswan.ai/arena) | $10,000 | Ended | Useful as a size reference: smaller pools exist between the big events. |
| [Gray Swan × Hack The Box: Machine-in-the-Middle](https://app.grayswan.ai/arena/challenge/machine-in-the-middle/rules) | $100,000 | Closed Dec 2025 | Solving CTF targets through an AI agent. Paid the top 30 per wave plus a quantity pool, so it rewarded volume, not only first place. |
| [CrowdStrike: Agents of Chaos](https://www.crowdstrike.com/en-us/blog/agents-of-chaos-immersive-ai-security-challenge/) | $100,000 | Closed 29 Sep 2026 | The game stays up as training. Covers direct and indirect injection and tool poisoning. |
| [Lambda × Berkeley AgentBeats Security](https://luma.com/lambda-agentbeats) | $5,000 / $3,000 / $1,000 | Phase 2 onboarding was Feb 2026; current status unclear | Build attack and defense agents, head to head. Closest match to this lab's skills, if a new round opens. |

**Nothing else is on the calendar yet.** Two deadline directories ([one](https://agentdeadlines.com/), [two](https://epochal-intelligence.com/Competitions.html)) list no dedicated AI security competition after November 2026. The nearest neighbours are [SANS NetWars](https://www.sans.org/cyber-ranges/upcoming-netwars-tournament) (14 to 19 Dec, general, now with AI challenges) and the [DevFest Münster hackathon](https://devfest-ai-hackathon.devpost.com/) (21 Nov, in person, no cash). Absence from two directories is weak evidence, so check the Arena page again after 12 Nov.

Gray Swan's rules that matter most: [18 or older, one account, manual submissions only, no sandbox
escapes, no trying to identify models, no sharing breaks until 30 days after the end](https://app.grayswan.ai/arena/challenge/ipi-black-2026?panel=rules).
Sponsors are [Anthropic, Meta, Google DeepMind and Reflection AI](https://fortune.com/2026/10/20/exclusive-ai-security-company-gray-swan-red-team-arena-contest-to-jailbreak-ai-agents/).
Top performers [may be invited to paid red-teaming work](https://securitybrief.news/story/gray-swan-relaunches-arena-with-usd-300-000-challenge), which may be worth more than prizes.

## Bounties

| Program | Pays for | Reward | Fit with this lab |
| --- | --- | ---: | --- |
| [OpenAI Safety Bug Bounty](https://openai.com/index/safety-bug-bounty/) | Third-party prompt injection that hijacks an agent into harmful action or a data leak, including via MCP. Must reproduce at least 50% of the time. Jailbreaks out of scope. | [Reported as up to $100,000 for critical findings](https://storyboard18.com/digital/openai-launches-safety-bug-bounty-program-with-payouts-up-to-100000-93422.htm). Press figure, the primary page could not be re-read on 6 Nov | Good. `gauntlet repro` answers the 50% question. |
| [Google AI VRP](https://www.bleepingcomputer.com/news/google/googles-new-ai-bug-bounty-program-pays-up-to-30-000-for-flaws) | Rogue actions and sensitive data exfiltration in Search, Gemini, Workspace | Up to $20,000 base for rogue actions, up to $30,000 with bonuses (2025 figures) | Good. Same weakness classes as the Gauntlet. |
| [Google Chrome agent defenses](https://www.eweek.com/news/google-bounty-chrome-ai-security-breach/) | Breaking the indirect-injection protections for Chrome's agent | Up to $20,000 (Dec 2025 report) | Good, but a hardened target. Check whether it is still open. |
| [0DIN](https://0din.ai/policy) | Model bugs and prompt injection in applications leading to unauthorized actions | $500 to $15,000, discretionary | Medium. An abstract can be submitted first to check scope and likely bounty. |
| [Anthropic Model Safety](https://support.claude.com/en/articles/12119250-model-safety-bug-bounty-program) | Universal jailbreaks of CBRN classifiers | Up to $35,000 | **Out for this lab.** It involves extracting harmful content, by application and under NDA. |
| Microsoft, Meta, HackerOne and Bugcrowd AI programs | Varies | [Estimates only](https://wraith.sh/learn/state-of-llm-bug-bounties-2026): often $500 to $3,000, more for critical | Unverified: that source calls its figures estimates. Check each program. |

All of these mean testing someone's real product under that program's rules, by hand, by Baris. The
Gauntlet refuses non-local endpoints in code and is not a tool for this. Its value is in practice,
reproduction statistics and report quality.

## How realistic is any of this?

My judgement, not data.

| Idea | Could earn | Odds | Note |
| --- | --- | --- | --- |
| Gray Swan prize | Hundreds to thousands | Low at first | Strong, experienced field. Treat year one as training; aim for the leaderboard and certificates. |
| Gray Swan paid network | Real income if invited | Low to medium, after a track record | The best route, since it pays for steady skill rather than for being first. |
| One valid bounty | $500 to $5,000 | Low to medium, after weeks of practice | Duplicates are common. Agent products are newer, so less picked over. |
| Agent security review for small teams | €500 to €2,000 per review | Medium, if someone asks | The Gauntlet report is the sample deliverable. Needs a contract and written scope. |
| Hosted scanner | Little | Low | Free competitors exist and the holdout result shows the limits. Better as a portfolio piece. |
| Paid scenario packs, training | Small | Low to medium | Depends on an audience, which a good blog post could start. |

None of this is financial or legal advice. Prize and bounty income has tax implications that depend
on where you live.
