"""Fill hand-written templates with fictional values. Generated documents are never committed.

The design is crossed and paired: every template appears with every naming tradition, and the
random draw depends only on seed, template and repeat, so traditions can be compared on otherwise
identical documents. Reserved `example.*` mail domains are used. Numbers are drawn at run time and
pass the format checks, which means a generated BSN or IBAN can coincide with a real one by chance,
and that is why no generated value is ever written to the repository.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from ner_nl.names import NAMES

STREETS = (
    "Kerkstraat Dorpsstraat Molenweg Schoolstraat Julianastraat Beatrixlaan Nieuwstraat "
    "Stationsweg Wilhelminastraat Sportlaan Parallelweg Rozenstraat Veldweg Lindelaan "
    "Oranjeplein Vijverhof Bergkade Havenkade"
).split()
TOWNS = (
    "Amersfoort Zwolle Tilburg Leeuwarden Almere Breda Arnhem Enschede Haarlem Maastricht "
    "Roermond Assen Hoorn Deventer"
).split()
MONTHS = (
    "januari februari maart april mei juni juli augustus september oktober november december"
).split()
BANKS = "ABNA RABO INGB SNSB TRIO ASNB".split()
DIGIT_WORDS = "nul een twee drie vier vijf zes zeven acht negen".split()
PREFIXES = ("van", "de", "van de", "van der", "van den", "ter")

# What each placeholder means for scoring. None: neutral, neither a leak nor over-redaction.
GOLD_KINDS = {
    "NAAM": "PERSOON",
    "VOORNAAM": "PERSOON",
    "ACHTERNAAM": "PERSOON",
    "INITIAAL": "PERSOON",
    "NAAM2": "PERSOON",
    "VOORNAAM2": "PERSOON",
    "ACHTERNAAM2": "PERSOON",
    "STRAAT": "ADRES",
    "POSTCODE": "POSTCODE",
    "PLAATS": None,
    "TELEFOON": "TELEFOON",
    "EMAIL": "E-MAIL",
    "IBAN": "IBAN",
    "BSN": "BSN",
    "GEBDATUM": "GEBOORTEDATUM",
    "KENTEKEN": "KENTEKEN",
    "BEDRAG": "AFLEIDER",
    "DOSSIER": "AFLEIDER",
    "DATUM": "AFLEIDER",
    "TIJD": "AFLEIDER",
}
SLOT = re.compile(r"\{([A-Z0-9]+)\}")


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    kind: str | None
    slot: str


@dataclass(frozen=True)
class Document:
    template: str
    register: str
    group: str
    repeat: int
    text: str
    spans: tuple[Span, ...]


def load_templates(split: str, folder: str | Path | None = None) -> list[dict]:
    if folder is None:
        raw = resources.files("pii_nl").joinpath("templates", f"{split}.jsonl").read_text("utf-8")
    else:
        raw = (Path(folder) / f"{split}.jsonl").read_text("utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _iban(rng: random.Random) -> str:
    bank = rng.choice(BANKS)
    account = f"{rng.randrange(10**10):010d}"
    moved = f"{bank}{account}NL00"
    digits = "".join(str(int(c, 36)) for c in moved)
    return f"NL{98 - int(digits) % 97:02d}{bank}{account}"


def _bsn(rng: random.Random) -> str:
    while True:
        head = [rng.randrange(10) for _ in range(8)]
        last = sum(d * w for d, w in zip(head, (9, 8, 7, 6, 5, 4, 3, 2))) % 11
        if last < 10 and sum(head) > 0:
            return "".join(map(str, head + [last]))


def _phone(rng: random.Random) -> str:
    digits = f"{rng.randrange(10**8):08d}"
    style = rng.randrange(4)
    if style == 0:
        return f"06-{digits}"
    if style == 1:
        return f"06 {digits[:2]} {digits[2:4]} {digits[4:6]} {digits[6:]}"
    if style == 2:
        return f"+31 6 {digits}"
    return f"0{rng.choice((20, 30, 40, 50, 70))}-{digits[:7]}"


def _plate(rng: random.Random) -> str:
    letters = "BDFGHJKLNPRSTVXZ"
    def pick(n):
        return "".join(rng.choice(letters) for _ in range(n))
    style = rng.randrange(3)
    a, b = rng.randrange(10), rng.randrange(100, 1000)
    if style == 0:
        return f"{pick(2)}-{b}-{pick(1)}"
    if style == 1:
        return f"{a}-{pick(3)}-{rng.randrange(10, 100)}"
    return f"{pick(3)}-{rng.randrange(10, 100)}-{pick(1)}"


def _birth(rng: random.Random) -> str:
    day, month, year = rng.randrange(1, 29), rng.randrange(1, 13), rng.randrange(1940, 2006)
    style = rng.randrange(3)
    if style == 0:
        return f"{day:02d}-{month:02d}-{year}"
    if style == 1:
        return f"{day} {MONTHS[month - 1]} {year}"
    return f"{day}/{month}/{year}"


def _spell(value: str) -> str:
    """Digits become words and symbols words, as speech-to-text writes out a dictated value."""
    out = []
    for char in value.lower():
        if char.isdigit():
            out.append(DIGIT_WORDS[int(char)])
        elif char.isalpha():
            out.append(char)
        elif char == "@":
            out.append("apenstaartje")
        elif char == ".":
            out.append("punt")
    joined, previous_alpha = [], False
    for part in out:
        if len(part) == 1 and previous_alpha:
            joined[-1] += part
        else:
            joined.append(part)
        previous_alpha = len(part) == 1
    return " ".join(joined)


def _spoken_date(value: str) -> str:
    """Speech-to-text writes months out, whatever format the value was drawn in."""
    match = re.fullmatch(r"(\d+)[-/](\d+)[-/](\d+)", value)
    if not match:
        return value
    day, month, year = match.groups()
    return f"{int(day)} {MONTHS[int(month) - 1]} {year}"


def _person(rng: random.Random, group: str) -> dict:
    pool = NAMES[group]
    first = pool["first"][rng.randrange(len(pool["first"]))]
    last = pool["last"][rng.randrange(len(pool["last"]))]
    # The draw happens for every group, so designs stay paired; only Dutch names use it.
    prefix = PREFIXES[rng.randrange(len(PREFIXES))] if rng.random() < 0.3 else ""
    if group == "dutch" and prefix:
        last = f"{prefix} {last}"
    return {"first": first, "last": last}


def _values(rng: random.Random, group: str) -> dict:
    one, two = _person(rng, group), _person(rng, group)
    town = rng.choice(TOWNS)
    mail_name = f"{one['first']}.{one['last']}".lower().replace(" ", "")
    return {
        "NAAM": f"{one['first']} {one['last']}",
        "VOORNAAM": one["first"],
        "ACHTERNAAM": one["last"],
        "INITIAAL": f"{one['first'][0]}. {one['last']}",
        "NAAM2": f"{two['first']} {two['last']}",
        "VOORNAAM2": two["first"],
        "ACHTERNAAM2": two["last"],
        "STRAAT": f"{rng.choice(STREETS)} {rng.randrange(1, 180)}",
        "POSTCODE": f"{rng.randrange(1000, 9999)} {rng.choice('BCDGHJKLMNPRTVWXZ')}"
        f"{rng.choice('BCDGHJKLMNPRTVWXZ')}",
        "PLAATS": town,
        "TELEFOON": _phone(rng),
        "EMAIL": f"{mail_name}@{rng.choice(('example.nl', 'example.com', 'example.org'))}",
        "IBAN": _iban(rng),
        "BSN": _bsn(rng),
        "GEBDATUM": _birth(rng),
        "KENTEKEN": _plate(rng),
        "BEDRAG": f"€ {rng.randrange(20, 4000)},{rng.randrange(100):02d}",
        "DOSSIER": f"Z{rng.randrange(2021, 2027)}-{rng.randrange(1000, 99999)}",
        "DATUM": f"{rng.randrange(1, 29)} {MONTHS[rng.randrange(12)]} {rng.randrange(2024, 2027)}",
        "TIJD": f"{rng.randrange(8, 18)}:{rng.choice(('00', '15', '30', '45'))}",
    }


def _render_value(slot: str, value: str, register: str, rng: random.Random) -> str:
    lower = rng.random() < 0.5  # drawn for every slot, to keep streams aligned across groups
    if register == "transcript":
        if slot in ("TELEFOON", "BSN", "IBAN", "POSTCODE", "KENTEKEN", "EMAIL"):
            digits = value.replace("+31", "0031") if slot == "TELEFOON" else value
            return _spell(digits)
        if slot == "GEBDATUM":
            return _spoken_date(value)
        return value.lower()
    if register == "chat" and lower and slot not in ("IBAN", "KENTEKEN"):
        return value.lower()
    return value


def render(template: dict, group: str, repeat: int, seed: int = 0) -> Document:
    stream = f"{seed}/{template['id']}/{repeat}"
    rng = random.Random(stream)
    values = _values(rng, group)
    parts, spans, cursor, at = [], [], 0, 0
    text = template["text"]
    for match in SLOT.finditer(text):
        slot = match.group(1)
        if slot not in GOLD_KINDS:
            raise ValueError(f"{template['id']}: unknown slot {slot}")
        literal = text[cursor : match.start()]
        parts.append(literal)
        at += len(literal)
        value = _render_value(slot, values[slot], template["register"], rng)
        parts.append(value)
        spans.append(Span(at, at + len(value), GOLD_KINDS[slot], slot))
        at += len(value)
        cursor = match.end()
    parts.append(text[cursor:])
    return Document(
        template["id"], template["register"], group, repeat, "".join(parts), tuple(spans)
    )


def generate(split: str, repeats: int = 8, seed: int = 0, folder=None) -> list[Document]:
    return [
        render(t, group, r, seed)
        for t in load_templates(split, folder)
        for group in NAMES
        for r in range(repeats)
    ]
