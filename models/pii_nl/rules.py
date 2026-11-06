"""Rules on top of `ner_nl.redact`, tuned on the dev templates only.

No name, street or town lists from the benchmark are used. Every rule looks at form or context:
street-name endings, a title before a name, a greeting, a signature, spoken digits. Whatever gets
recognised as a person is then masked everywhere else in the same document.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache

from ner_nl.redact import Hit, merge, model_hits, pattern_hits

try:
    from wordfreq import zipf_frequency
except ImportError:  # optional: rules still run, without the frequency checks
    zipf_frequency = None

COMMON_ZIPF = 4.6
RARE_ZIPF = 3.3
WORD = r"[^\W\d_][^\W\d_'’-]*(?:[-'’][^\W\d_]+)*"
PARTICLES = r"(?:van|de|der|den|ter|ten|te|het|el|al|ben|bin)"
DIGITS = "nul een één twee drie vier vijf zes zeven acht negen tien".split()
DIGIT = r"(?:" + "|".join(DIGITS) + r")"

# Words that can follow a cue in lowercase text and are clearly not part of a name.
STOP = frozenset(
    """aan af al alle als altijd ander anders bent ben bij bijna daar dan dat de deze die dit doe
    doen door dus een eens eh en er ergens even ff geen gaat ga had heb hebben heeft hem hen het
    hier hij hoe hoi hun ik in is ja je jij jullie kan kijk kijken klopt komt kun kunnen kunt laat
    maar me meer met mij mijn moet mogen mooi morgen na naar nee net niet nog nou nu of ofzo oke ok
    om onder ons ook op over per regelt sinds te terug tot toch twee u uit uw van vanaf vandaag
    veel via voor vraag waar want was wat we weer wel werd wie wil wilde wij wordt zal ze zei zij
    zijn zo zoals zou zoon dochter buurman buurvrouw thuis gisteren hallo goedemiddag goedemorgen
    goedenavond dag beste geachte hee hey hi ok thanks allemaal collega collegas team heer meneer
    mevrouw mevr mevr. dhr mnr mw groetjes groeten groet bedankt melder aanvrager geboortedatum
    bsn bezwaarmaker geb geboren mail adres telefoon tel""".split()
)
TITLES = (
    r"(?:mevrouw|mevr\.?|mw\.?|meneer|mnr\.?|de\s+heer|dhr\.?|dr\.?|mr\.?|ir\.?|drs\.?|prof\.?)"
)
INTROS = (
    r"(?:ik\s+ben|u\s+spreekt\s+met|je\s+spreekt\s+met|spreekt\s+met|mijn\s+naam\s+is|ik\s+heet"
    r"|heette|heet|hallo\s+met|hoi\s+met|ja\s+met|met\s+wie\s+spreek\s+ik|naam:|aanvrager:"
    r"|melder:|verzoek\s+van|inschrijving|namens|medewerker|collega|contactpersoon|bezwaarmaker"
    r"|bijgestaan\s+door|aan\s+de\s+lijn\s+gehad)"
)
GREETINGS = r"(?:beste|geachte|hoi|hi|hey|hee|hallo|dag|lieve)"
SIGN_OFF = r"(?:groet(?:en|jes)?|gr\.?|hoogachtend|thanks|bedankt|liefs|mvg|namens[^\n]*)"
STREET = (
    r"(?:straat|laan|weg|plein|kade|hof|singel|gracht|dreef|pad|steeg|dijk|plantsoen|boulevard"
    r"|markt|park|erf|haven|wal|veld|hoek)"
)
LETTERS = "BDFGHJKLMNPRSTVWXZ"

EXTRA_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    (
        "ADRES",
        re.compile(rf"\b[^\W\d_]*{STREET}\s+\d{{1,4}}(?:\s?[a-zA-Z](?![^\W\d_]))?", re.I),
    ),
    # Sidecodes in use on Dutch plates, hyphens required: without them too much looks like one.
    (
        "KENTEKEN",
        re.compile(
            rf"(?<![\w-])(?:[{LETTERS}]{{2}}-\d{{3}}-[{LETTERS}]|\d-[{LETTERS}]{{3}}-\d{{2}}"
            rf"|[{LETTERS}]{{3}}-\d{{2}}-[{LETTERS}]|\d{{2}}-[{LETTERS}]{{3}}-\d"
            rf"|[{LETTERS}]-\d{{3}}-[{LETTERS}]{{2}}|\d{{3}}-[{LETTERS}]{{2}}-\d"
            rf"|[{LETTERS}]{{2}}-[{LETTERS}]{{2}}-\d{{2}}|\d{{2}}-\d{{2}}-[{LETTERS}]{{2}}"
            rf"|\d{{2}}-[{LETTERS}]{{2}}-[{LETTERS}]{{2}}|[{LETTERS}]{{2}}-\d{{2}}-[{LETTERS}]{{2}})"
            r"(?![\w-])",
            re.I,
        ),
    ),
)
_MONTH = (
    r"(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)"
)
_DATE = rf"(?:\d{{1,2}}[-/.]\d{{1,2}}[-/.]\d{{2,4}}|\d{{1,2}}\s+{_MONTH}\s+\d{{4}})"
BIRTH = re.compile(rf"\b(?:geboren|geboortedatum|geb)\b\.?[\s:a-z]{{0,20}}?({_DATE})", re.I)
# Dictated values. A run of digit words, or digit words mixed with short letter groups.
SPOKEN_RUN = re.compile(rf"\b{DIGIT}(?:\s+{DIGIT}){{5,}}\b", re.I)
SPOKEN_MIXED = re.compile(rf"\b(?:[a-z]{{1,4}}\s+)?{DIGIT}(?:\s+(?:{DIGIT}|[a-z]{{1,4}})){{5,}}\b")
_DIGIT_END = re.compile(rf".*\b{DIGIT}\b", re.S)
SPOKEN_PLATE = re.compile(
    rf"\b(?:[a-z]{{1,3}}\s+{DIGIT}(?:\s+{DIGIT}){{1,3}}\s+[a-z]{{1,3}}"
    rf"|{DIGIT}\s+[a-z]{{2,3}}\s+{DIGIT}\s+{DIGIT}"
    rf"|{DIGIT}\s+{DIGIT}\s+[a-z]{{2,3}}\s+{DIGIT})\b"
)
SPOKEN_CUE = re.compile(
    rf"\b(postcode|kenteken)\s+(?:is\s+|van\s+)?((?:(?:{DIGIT}|[a-z]{{1,3}})(?:\s+|$)){{2,8}})",
    re.I,
)
SPOKEN_MAIL = re.compile(
    rf"\b{WORD}(?:\s+punt\s+{WORD})*\s+apenstaartje\s+{WORD}(?:\s+punt\s+{WORD})+", re.I
)
CAPITAL = r"[A-Z][^\W\d_]*(?:[-'’][^\W\d_]+)*"
INITIALS = re.compile(rf"\b(?:[A-Z]\.\s?)+(?:{PARTICLES}\s+)*{CAPITAL}")
LOWER_INITIAL = re.compile(r"(?<![\w.])[a-z]\.\s(?=[a-z])")


@lru_cache(maxsize=50000)
def zipf(word: str) -> float:
    """General Dutch word frequency on the Zipf scale, or 8 without `wordfreq` (nothing is rare)."""
    if zipf_frequency is None:
        return 8.0
    return zipf_frequency(word.lower(), "nl")


def _common(word: str) -> bool:
    """Too frequent to be taken for a name when nothing else speaks for it."""
    return zipf_frequency is not None and zipf(word) >= COMMON_ZIPF


def truecase(text: str, rare: float = RARE_ZIPF) -> str:
    """Capitalise rare words on lowercase lines, so a news model has its usual cue. Same length."""
    lines = []
    for line in text.split("\n"):
        words = re.findall(WORD, line)
        capitals = sum(w[0].isupper() for w in words)
        if words and capitals / len(words) < 0.25:
            line = re.sub(
                WORD,
                lambda m: m.group().capitalize()
                if len(m.group()) >= 3
                and m.group().lower() not in STOP
                and m.group().lower() not in DIGITS
                and zipf(m.group()) < rare
                else m.group(),
                line,
            )
        lines.append(line)
    return "\n".join(lines)


def _spoken_mixed(text: str) -> list[Hit]:
    """Digit words with letter groups, as in a dictated IBAN. Ends at the last digit word and only
    counts when ordinary words don't dominate the run."""
    hits = []
    for match in SPOKEN_MIXED.finditer(text):
        last = _DIGIT_END.match(match.group())
        words = last.group().split()
        plain = sum(w in STOP and w not in DIGITS for w in words)
        if plain <= 1:
            hits.append(Hit(match.start(), match.start() + last.end(), "NUMMER", "pattern"))
    return hits


def _spoken_plates(text: str) -> list[Hit]:
    hits = []
    for match in SPOKEN_PLATE.finditer(text):
        letters = [w for w in match.group().split() if w not in DIGITS]
        if not any(w in STOP or _common(w) for w in letters):
            hits.append(Hit(match.start(), match.end(), "KENTEKEN", "pattern"))
    return hits


def _name_tokens(text: str, start: int) -> int:
    """End offset of up to four name-like words from `start`. Returns `start` if there are none."""
    end, words, seen, cased = start, 0, 0, False
    for match in re.finditer(rf"\s*({WORD}|[A-Z]\.)", text[start:start + 80]):
        if match.start() != end - start:
            break
        word = match.group(1)
        if "\n" in match.group(0):
            break
        low = word.lower()
        if re.fullmatch(PARTICLES, low):
            if words == 0 and word.islower() and low in ("de", "het", "te"):
                break
            seen += 1
            end = start + match.end()
            continue
        if low in STOP or low in DIGITS or (word.islower() and _common(low)):
            break
        if words and cased and word[0].islower():
            break  # in cased text a name stops at the first lowercase word
        cased = cased or word[0].isupper()
        end = start + match.end()
        words += 1
        seen += 1
        if words == 3 or seen == 5:
            break
    return end if words else start


def _cued_names(text: str) -> list[Hit]:
    hits = []
    for cue in (TITLES, INTROS, GREETINGS):
        for match in re.finditer(rf"(?<![\w-]){cue}(?![\w-])\s*", text, re.I):
            end = _name_tokens(text, match.end())
            if end > match.end():
                hits.append(Hit(match.end(), end, "PERSOON", "rule"))
    for match in LOWER_INITIAL.finditer(text):
        end = _name_tokens(text, match.end() - 1)
        if end > match.end():
            hits.append(Hit(match.start(), end, "PERSOON", "rule"))
    return hits


def _signature(text: str) -> list[Hit]:
    hits = []
    for match in re.finditer(rf"(?m)\b{SIGN_OFF}\s*[,:]?[ \t]*\n?\s*", text, re.I):
        line_end = text.find("\n", match.end())
        line_end = len(text) if line_end < 0 else line_end
        line = text[match.end() : line_end]
        words = line.split()
        if 1 <= len(words) <= 4 and all(w[:1].isupper() for w in words if len(w) > 3):
            hits.append(Hit(match.end(), match.end() + len(line.rstrip()), "PERSOON", "rule"))
    return hits


def _midsentence_capitals(text: str) -> list[Hit]:
    """A capitalised word that doesn't start a sentence or line. Crude, and only a backstop."""
    hits = []
    for match in re.finditer(rf"(?<=[a-zà-ÿ,] ){CAPITAL}(?:\s+{CAPITAL})*", text):
        if match.group().lower() not in STOP:
            hits.append(Hit(match.start(), match.end(), "PERSOON", "rule"))
    return hits


def _mail_names(hits: Iterable[Hit], text: str) -> set[str]:
    """`sanne.bakker@...` tells us two name parts, and the same holds for a dictated address."""
    found = set()
    for hit in hits:
        if hit.kind != "E-MAIL":
            continue
        value = text[hit.start : hit.end].lower()
        local = re.split(r"@|\s+apenstaartje\s+", value)[0]
        found |= {w for w in re.split(r"[._+\-\s]|punt", local) if len(w) >= 3}
    return found


def propagate(text: str, hits: list[Hit]) -> list[Hit]:
    """Mask every other occurrence, in any case, of a word already identified as a name."""
    names = {
        w.lower()
        for h in hits
        if h.kind == "PERSOON"
        for w in re.findall(WORD, text[h.start : h.end])
    }
    names |= _mail_names(hits, text)
    names = {
        n
        for n in names
        if len(n) >= 3
        and n not in STOP
        and n not in DIGITS
        and zipf(n) < 5.0
        and not re.fullmatch(PARTICLES, n)
    }
    if not names:
        return hits
    extra = [
        Hit(m.start(), m.end(), "PERSOON", "rule")
        for m in re.finditer(WORD, text)
        if m.group().lower() in names
    ]
    return hits + extra


def rule_hits(text: str, nlp=None, cased=None) -> list[Hit]:
    """`cased`, if given, replaces `text` for the model only. It must keep the same offsets."""
    hits = pattern_hits(text)
    for kind, pattern in EXTRA_PATTERNS:
        hits += [Hit(m.start(), m.end(), kind, "pattern") for m in pattern.finditer(text)]
    hits += [Hit(m.start(1), m.end(1), "GEBOORTEDATUM", "pattern") for m in BIRTH.finditer(text)]
    hits += [Hit(m.start(), m.end(), "NUMMER", "pattern") for m in SPOKEN_RUN.finditer(text)]
    hits += _spoken_mixed(text) + _spoken_plates(text)
    hits += [Hit(m.start(2), m.end(2), "NUMMER", "pattern") for m in SPOKEN_CUE.finditer(text)]
    hits += [Hit(m.start(), m.end(), "E-MAIL", "pattern") for m in SPOKEN_MAIL.finditer(text)]
    hits += [Hit(m.start(), m.end(), "PERSOON", "rule") for m in INITIALS.finditer(text)]
    hits += _cued_names(text) + _signature(text) + _midsentence_capitals(text)
    if nlp is not None:
        hits += model_hits(text if cased is None else cased, nlp)
    return propagate(text, hits)


def redact(text: str, nlp=None, use_truecase: bool = True) -> tuple[str, list[Hit]]:
    """Replace each masked stretch by a `[KIND]` label. Adjacent model hits collapse via `merge`."""
    kept = merge(rule_hits(text, nlp, truecase(text) if use_truecase else None))
    parts, cursor = [], 0
    for hit in kept:
        parts += [text[cursor : hit.start], f"[{hit.kind}]"]
        cursor = hit.end
    parts.append(text[cursor:])
    return "".join(parts), kept
