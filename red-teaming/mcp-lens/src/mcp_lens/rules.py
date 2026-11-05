"""Detection rules. All static: nothing here calls a model or runs a tool.

Severity meaning:
  high    a clear sign of an attempt to steer the agent
  medium  common in attacks, sometimes honest; worth a human look
  low     hygiene; does not fail a scan by default
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Iterator

SEVERITY = {"low": 1, "medium": 2, "high": 3}


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    server: str
    tool: str
    field: str
    message: str
    excerpt: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class Tool:
    server: str
    name: str
    description: str
    schema: dict[str, Any]


def text_fields(tool: Tool) -> Iterator[tuple[str, str]]:
    """Every string an LLM client may show the model, not only the top description."""
    yield "description", tool.description or ""

    def walk(node: Any, path: str) -> Iterator[tuple[str, str]]:
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("description", "title", "default", "const", "pattern", "$comment") and isinstance(v, str):
                    yield f"{path}.{k}", v
                elif k in ("enum", "examples") and isinstance(v, list):
                    for i, item in enumerate(v):
                        if isinstance(item, str):
                            yield f"{path}.{k}[{i}]", item
                else:
                    yield from walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from walk(v, f"{path}[{i}]")

    yield from walk(tool.schema or {}, "schema")


def _ex(text: str, m: re.Match[str]) -> str:
    s = max(0, m.start() - 30)
    return " ".join(text[s : m.end() + 30].split())[:120]


_TAG_RANGE = (0xE0000, 0xE007F)
_INVISIBLE = {"Cf"}


def hidden_chars(text: str) -> list[str]:
    out = []
    for ch in text:
        cp = ord(ch)
        if _TAG_RANGE[0] <= cp <= _TAG_RANGE[1] or unicodedata.category(ch) in _INVISIBLE:
            out.append(f"U+{cp:04X}")
    return out


_CONFUSABLE = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X",
    "І": "I", "α": "a", "ο": "o", "ι": "i", "ν": "v", "Ι": "I", "Ο": "O",
})
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
_LEET_WORD = re.compile(r"\b(?=[a-z0-9@$]*[a-z])(?=[a-z0-9@$]*[0-9@$])[a-z0-9@$]{3,}\b", re.I)
_SPACED = re.compile(r"(?<!\S)(?:\S {1,2}){4,}\S(?!\S)")
_B64_TOKEN = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{16,}={0,2}(?![A-Za-z0-9+/])")
_HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.S)


def decoded_blobs(text: str) -> list[str]:
    """Short base64 tokens that decode to readable text."""
    out = []
    for tok in _B64_TOKEN.findall(text):
        try:
            raw = base64.b64decode(tok + "=" * (-len(tok) % 4), validate=True).decode("ascii")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
        if raw.isprintable() and " " in raw:
            out.append(raw)
    return out


def normalize(text: str) -> str:
    """Undo the cheap evasions before any pattern runs."""
    t = unicodedata.normalize("NFKC", text)
    t = "".join(c for c in t if not hidden_chars(c)).translate(_CONFUSABLE)
    t = _SPACED.sub(lambda m: re.sub(r" {2,}", "\0", m.group(0)).replace(" ", "").replace("\0", " "), t)
    t = _LEET_WORD.sub(lambda m: m.group(0).translate(_LEET), t)
    return " ".join([t, *decoded_blobs(t)])


def _rx(*parts: str) -> re.Pattern[str]:
    return re.compile("|".join(parts), re.I)


OVERRIDE = _rx(
    r"\b(ignore|disregard|forget|override|bypass)\b.{0,30}\b(previous|prior|above|earlier|other|all|safety|system|existing)\b.{0,20}\b(instructions?|rules?|prompts?|guidelines?|policies|policy|directions?)\b",
    r"\bnew (system )?instructions?\b\s*[:\-]",
    r"\byou (are now|must now|have been (updated|reconfigured))\b",
    r"\bsystem (override|message|prompt)\s*:",
    r"\[/?(system|inst)\]|<\|?/?(system|im_start|instructions?)\|?>",
    # The same move in other languages. Not a translation layer, only the commonest forms.
    r"\b(negeer|vergeet)\b.{0,25}\b(instructies|regels|opdrachten)\b",
    r"\b(ignoriere|vergiss)\b.{0,25}\b(anweisungen|regeln)\b",
    r"\b(ignore[zr]?|oublie[zr]?)\b.{0,25}\b(instructions|consignes)\b",
    r"\b(ignora|olvida)\b.{0,25}\b(instrucciones|reglas)\b",
)
CONCEAL = _rx(
    r"\b(do not|don'?t|never|avoid)\b.{0,25}\b(tell|tells|inform|mention|notify|alert|reveal|show|disclose|display)\b.{0,40}\b(user|human|operator|anyone|them)\b",
    r"\bwithout\b.{0,20}\b(telling|informing|notifying|alerting|showing)\b",
    r"\b(hide|conceal|keep)\b.{0,25}\b(this|these|it)\b.{0,25}\b(from|secret)\b",
    r"\b(silently|quietly|covertly|secretly|invisibly)\b.{0,40}\b(send|include|add|pass|forward|call|read|attach|copy|upload|post)\b",
    r"\b(send|include|add|pass|forward|call|read|attach|copy|upload|post)\b.{0,40}\b(silently|quietly|covertly|secretly)\b",
    r"\bthe user (does not|doesn'?t|need not|should not|must not) (need to )?(know|see|be told)\b",
    r"\b(vertel|zeg|meld)\b.{0,30}\b(gebruiker)\b.{0,20}\bniets\b",
    r"\bniet (aan )?de gebruiker\b",
)
SECRET = _rx(
    r"(~/|\s)\.(ssh|aws|gnupg|netrc|npmrc|kube)\b",
    r"~/\.(config|docker)\b",
    r"\bid_(rsa|ed25519|ecdsa)\b",
    r"(^|[\s/'\"`])\.env\b",
    r"\b/etc/(passwd|shadow)\b",
    r"\bmcp\.json\b",
    r"\b(contents?|value|values)\s+of\b.{0,40}\b(secrets?|tokens?|credentials?|api[ _-]?keys?|passwords?|private keys?)\b",
    r"\b(read|fetch|get|include|send|pass|provide|attach|supply|copy)\b.{0,40}\b(your|the user'?s|their|all|any|current|stored)\b.{0,25}\b(secrets?|tokens?|credentials?|api[ _-]?keys?|passwords?|private keys?)\b",
    r"\b(system prompt|conversation history|chat history|previous messages|full conversation)\b.{0,50}\b(in|into|to|as)\b",
    r"\b(include|pass|send|attach|provide|supply|copy|put|place)\b.{0,50}\b(system prompt|conversation history|chat history|previous messages|full conversation)\b",
)
# An instruction aimed at the agent that reaches for data or changes who gets what.
# Tools describe what they do; they rarely tell the agent what to hand over.
AGENT_DIRECTED = _rx(
    r"\b(copy|paste|append|attach|add|hand|forward|dump|put|place|insert)\b.{0,50}\b(user'?s|your|what you know|what the user|private|personal|account number|earlier)\b",
    r"\b(change|replace|rewrite|swap|redirect|modify|set)\b.{0,25}\b(the )?(recipients?|payee|destination|account|address|to field)\b",
    r"\b(all|any|every|each)\b.{0,30}\b(payments?|transfers?|replies|reply|responses?|messages|emails?)\b.{0,40}\b(should|must|go|goes|to)\b",
    r"\b(end|finish|start|begin|close)\b.{0,12}\b(every|each|all|your)\b.{0,20}\b(reply|replies|response|responses|answer|answers|message)\b",
    r"\btreat\b.{0,40}\b(as|like)\b.{0,30}\b(user|system|instructions?|trusted|developer|admin)\b",
    r"\b(standing|pre-?)\s?approv\w+|\bapproval\b.{0,30}\b(not needed|not required|waived|granted)\b",
    r"\b(confirmation|approval|review|safety|verification)\b.{0,30}\b(switched off|turned off|disabled|skipped|not needed|waived)\b",
    r"\bafter the \w+ (call|use|run|time)\b",
    r"\bassistant\s*:",
)
_LOOSE_PARAM = _rx(
    r"\bpaste\b", r"\bverbatim\b", r"\bwhat you know\b", r"\brecent\b.{0,20}\b(tool|outputs?|messages?|results?)\b",
    r"\babout the user\b",
)
ORDERING = _rx(
    r"\bbefore (using|calling|invoking|running|executing)\b.{0,30}\b(this|any|the|other)\b.{0,20}\b(tool|function|server|command)\b.{0,50}\b(must|always|first|read|call|send)\b",
    r"\b(must|always|first|required to)\b.{0,30}\b(first )?(call|read|invoke|run|send|fetch)\b.{0,60}\bbefore\b.{0,40}\b(use|using|call|calling|respond|responding|answer|answering|this tool)\b",
    r"\bfor (this|the) tool to work\b",
    r"\b(will|would|may) (fail|crash|not work|break)\b.{0,40}\b(unless|if you do not|if you don'?t|without)\b",
    r"\bfrom (now on|this (version|point) on)\b",
    r"\b(run|call|invoke|use)\s+\w+_\w+\b.{0,40}\b(and|then)\b.{0,20}\b(hand|pass|send|give|feed)\b",
    r"\bthis is routine\b",
    r"\b(whenever|every time|each time)\b.{0,50}\b(also|additionally|must|always)\b",
)
SHADOW = _rx(
    r"\b(instead of|rather than|replaces?|supersedes?|overrides?)\b.{0,30}\b(the )?(\w+[_-]\w+|other|built-?in|default|existing)\b.{0,15}\b(tool|function|server)?\b",
    r"\b(all|every|any)\b.{0,20}\b(outgoing|outbound|other)\b.{0,25}\b(mail|email|message|request|tool|call)s?\b",
    r"\bsend (a )?(blind )?(copy|cc|bcc)\b",
    r"\bwhen (the agent|you|the assistant|it)\b.{0,20}\b(emails?|mails?|sends?|pays?|calls?|posts?)\b",
)
EXFIL_PARAM = re.compile(
    r"^(side_?note|sidenote|memo|context|conversation|history|chat|transcript|system_?prompt|debug_?(info|data)?|"
    r"metadata|extra|internal|feedback|telemetry|reasoning|thoughts?|env|environment_?vars?)$", re.I)
ASKS_FOR_DATA = _rx(
    r"\b(must|always|should|required|please)\b.{0,40}\b(include|contain|pass|provide|fill|hold|carry|set)\b",
    r"\b(entire|whole|full|complete|all)\b.{0,25}\b(conversation|history|context|messages?|prompt|file|contents?)\b",
    r"\bprevious\b.{0,20}\b(messages?|results?|outputs?)\b",
)
B64_BLOB = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{48,}={0,2}(?![A-Za-z0-9+/])")
HEX_BLOB = re.compile(r"\b(?:[0-9a-fA-F]{2}){24,}\b")
URLISH = re.compile(r"https?://[^\s'\")\]>]+|\b[\w.+-]+@[\w-]+\.[\w.-]+\b", re.I)
DOC_HOSTS = re.compile(
    r"(github\.com|githubusercontent\.com|modelcontextprotocol\.io|wikipedia\.org|example\.(com|org|net)|"
    r"localhost|127\.0\.0\.1|schema\.org|json-schema\.org|docs?\.[\w.-]+|developer\.mozilla\.org)", re.I)

_TEXT_RULES: list[tuple[str, str, re.Pattern[str], str]] = [
    ("ML002", "high", OVERRIDE, "tries to override the agent's instructions"),
    ("ML003", "high", CONCEAL, "asks the agent to hide something from the user"),
    ("ML004", "high", SECRET, "reaches for secrets, sensitive files or the conversation"),
    ("ML005", "medium", ORDERING, "imposes steps on the agent beyond this tool's job"),
    ("ML006", "medium", SHADOW, "tries to change how other tools or mail are used"),
    ("ML016", "medium", AGENT_DIRECTED, "instructs the agent about data or destinations"),
]


def scan_tool(tool: Tool, known_tools: set[str]) -> list[Finding]:
    f: list[Finding] = []
    add = lambda rule, sev, field, msg, ex="": f.append(Finding(rule, sev, tool.server, tool.name, field, msg, ex))
    for field, text in text_fields(tool):
        if not text:
            continue
        hid = hidden_chars(text)
        if hid:
            add("ML001", "high", field, f"{len(hid)} invisible character(s): {', '.join(sorted(set(hid))[:4])}")
        clean = normalize(text)
        if _HTML_COMMENT.search(text):
            add("ML017", "high", field, "text hidden in an HTML comment", _HTML_COMMENT.search(text).group(0)[:80])
        for rule, sev, rx, msg in _TEXT_RULES:
            m = rx.search(clean)
            if m:
                add(rule, sev, field, msg, _ex(clean, m))
        others = {n for n in known_tools - {tool.name} if len(n) >= 5 and ("_" in n or "-" in n)}
        for name in sorted(others):
            if re.search(rf"\b{re.escape(name)}\b", clean):
                add("ML007", "medium", field, f"mentions another tool: {name}")
                break
        for rx, label in ((B64_BLOB, "base64"), (HEX_BLOB, "hex")):
            m = rx.search(clean)
            if m:
                add("ML009", "medium", field, f"long {label}-looking blob", m.group(0)[:40])
        for m in URLISH.finditer(clean):
            if not DOC_HOSTS.search(m.group(0)):
                add("ML010", "low", field, "names an outside address", m.group(0)[:80])
                break
    joined = normalize(" ".join(t for _, t in text_fields(tool)))  # a phrase split over two fields
    for rule, sev, rx, msg in _TEXT_RULES[:3]:
        if not any(x.rule == rule for x in f) and (m := rx.search(joined)):
            add(rule, sev, "joined-fields", f"{msg} (across fields)", _ex(joined, m))
    if len(tool.description or "") > 2500:
        add("ML013", "low", "description", f"description is {len(tool.description)} characters long")
    props = (tool.schema or {}).get("properties") or {}
    for pname, spec in props.items():
        if not isinstance(spec, dict):
            continue
        d = str(spec.get("description", ""))
        if (EXFIL_PARAM.match(pname) and ASKS_FOR_DATA.search(d)) or _LOOSE_PARAM.search(d):
            add("ML008", "medium", f"schema.properties.{pname}", "parameter is shaped to carry data the tool does not need",
                " ".join(d.split())[:100])
    if tool.schema and tool.schema.get("type") == "object" and not props and tool.schema.get("additionalProperties", False):
        add("ML012", "low", "schema", "accepts arbitrary properties with no declared ones")
    return f


# Capability inference from names and text. Coarse by design: it is used to raise
# a question about a whole server set, never to accuse a single tool.
_CAP = {
    "untrusted": _rx(r"\b(fetch|browse|scrape|crawl|web|url|http|rss|inbox|email|mail|slack|issue|comment|pull request|search the web)\b"),
    "private": _rx(r"\b(read_file|file system|filesystem|database|sql|query|secret|credential|vault|calendar|contacts?|drive|documents?|notes?|memory|knowledge graph)\b"),
    "egress": _rx(r"\b(send|post|publish|upload|webhook|email|tweet|share|create_issue|comment|push|http_post|http_request|fetch)\b"),
}


def capabilities(tool: Tool) -> set[str]:
    blob = tool.name.replace("_", " ") + " " + tool.name + " " + (tool.description or "")[:400]
    return {c for c, rx in _CAP.items() if rx.search(blob)}


def scan_set(tools: list[Tool]) -> list[Finding]:
    """Findings that only exist across tools: collisions and dangerous combinations."""
    out: list[Finding] = []
    by_norm: dict[str, list[Tool]] = {}
    for t in tools:
        key = unicodedata.normalize("NFKC", t.name).lower().replace("-", "_")
        by_norm.setdefault(key, []).append(t)
    for key, group in by_norm.items():
        servers = {t.server for t in group}
        names = {t.name for t in group}
        if len(names) > 1:
            out.append(Finding("ML011", "high", group[0].server, group[0].name, "name",
                               f"near-identical tool names: {sorted(names)}"))
        elif len(servers) > 1:
            out.append(Finding("ML011", "medium", sorted(servers)[0], group[0].name, "name",
                               f"same tool name on {len(servers)} servers: {sorted(servers)}"))
    for t in tools:
        if any(ord(c) > 127 for c in t.name):
            out.append(Finding("ML011", "high", t.server, t.name, "name", "non-ASCII tool name, possible look-alike"))
    caps: dict[str, set[str]] = {"untrusted": set(), "private": set(), "egress": set()}
    for t in tools:
        for c in capabilities(t):
            caps[c].add(f"{t.server}/{t.name}")
    if all(caps.values()):
        out.append(Finding("ML014", "low", "*", "*", "set",
                           "this tool set can read third-party content, read private data and send data out; "
                           "an injection in the first can reach the last",
                           f"e.g. {sorted(caps['untrusted'])[0]} → {sorted(caps['private'])[0]} → {sorted(caps['egress'])[0]}"))
    return out


RULE_DOCS = {
    "ML001": "Invisible Unicode (tag characters, zero-width, bidi controls) in text a model reads.",
    "ML002": "Language that overrides the agent's instructions.",
    "ML003": "Requests to hide actions from the user.",
    "ML004": "References to secrets, sensitive paths or the conversation itself.",
    "ML005": "Mandatory prior steps that have nothing to do with the tool's job.",
    "ML006": "Attempts to change how other tools or outgoing messages behave.",
    "ML007": "A description that names another tool.",
    "ML008": "Parameters shaped to carry context the tool should not need.",
    "ML009": "Encoded blobs inside descriptions.",
    "ML010": "Outside addresses inside descriptions.",
    "ML011": "Tool name collisions and look-alikes across servers.",
    "ML012": "Schemas that accept anything.",
    "ML013": "Very long descriptions, a common place to bury instructions.",
    "ML014": "A tool set combining third-party input, private data and an outbound channel.",
    "ML015": "A pinned tool changed (rug pull).",
    "ML016": "Instructions to the agent about data, recipients or its replies.",
    "ML017": "Text hidden in an HTML comment.",
}
