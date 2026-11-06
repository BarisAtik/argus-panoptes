"""Convert Sigma rules to engine queries.

The same processing pipeline feeds both backends, so a difference in results comes from the
engine or the mapping, not from a different reading of the rule.
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass

from sigma.backends.elasticsearch import LuceneBackend
from sigma.backends.sqlite.sqlite import sqliteBackend
from sigma.collection import SigmaCollection
from sigma.exceptions import SigmaError
from sigma.pipelines.sysmon import sysmon_pipeline
from sigma.pipelines.windows import windows_logsource_pipeline
from sigma.rule import SigmaRule
from sigma.types import SigmaCIDRExpression, SigmaRegularExpression, SigmaString

LOOKAROUND = re.compile(r"\(\?[=!<]")
INLINE_FLAGS = re.compile(r"^\(\?[a-zA-Z]+\)")


def lucene_regex(pattern: str) -> str | None:
    """Rewrite a Python-style Sigma regex so that it means the same thing to Lucene.

    Lucene matches the whole term and a lower-casing normalizer does not touch the pattern, so an
    untouched regex rule can quietly never fire. This unanchors the pattern, drops inline flags,
    turns `(?:` into `(`, lowercases literals and escapes Lucene's extra operators. Returns None
    for lookaround, which Lucene cannot express.
    """
    if LOOKAROUND.search(pattern):
        return None
    body = INLINE_FLAGS.sub("", pattern).replace("(?:", "(")
    start = not body.startswith("^")
    body = body.removeprefix("^")
    end = not (body.endswith("$") and not body.endswith(r"\$"))
    if not end:
        body = body[:-1]
    out: list[str] = []
    position = 0
    while position < len(body):
        char = body[position]
        if char == "\\" and position + 1 < len(body):
            out.append(body[position : position + 2])
            position += 2
            continue
        out.append("\\" + char if char in '<>"#@&~' else char.lower())
        position += 1
    return (".*" if start else "") + "".join(out) + (".*" if end else "")


def adapt_values(node) -> None:
    """Rewrite values that a keyword field cannot evaluate as written.

    A CIDR needs an `ip` field. On a keyword it is a literal string that matches nothing, and when
    it sits under NOT, as in "not from a private range", the filter silently stops filtering.
    """
    for item in node.detection_items:
        if hasattr(item, "detection_items"):
            adapt_values(item)
            continue
        values = []
        for value in item.value:
            if isinstance(value, SigmaRegularExpression):
                source = value.regexp
                adapted = lucene_regex(source if isinstance(source, str) else source.original)
                values.append(value if adapted is None else SigmaRegularExpression(adapted))
            elif isinstance(value, SigmaCIDRExpression):
                values += [SigmaString(prefix) for prefix in value.expand("*")]
            else:
                values.append(value)
        item.value = values


def pipeline():
    return sysmon_pipeline() + windows_logsource_pipeline()


@dataclass
class Converted:
    rule_id: str
    lucene: str | None = None
    lucene_tuned: str | None = None  # with values rewritten by `adapt_values`
    sql_where: str | None = None
    unbound: bool = False  # keyword rule with no field: not comparable across engines
    error: str = ""


def _has_keywords(rule: SigmaRule) -> bool:
    def walk(detection) -> bool:
        for item in detection.detection_items:
            if hasattr(item, "detection_items"):
                if walk(item):
                    return True
            elif item.field is None:
                return True
        return False

    return any(walk(detection) for detection in rule.detection.detections.values())


def convert(rule: SigmaRule) -> Converted:
    result = Converted(rule_id=str(rule.id), unbound=_has_keywords(rule))
    # A backend applies its pipeline to the rule in place, so each one gets its own copy.
    try:
        lucene = LuceneBackend(pipeline()).convert(SigmaCollection([deepcopy(rule)]))
        result.lucene = lucene[0] if len(lucene) == 1 else None
    except (SigmaError, NotImplementedError, ValueError, TypeError) as error:
        result.error = f"lucene: {type(error).__name__}: {str(error)[:120]}"
    try:
        tuned = deepcopy(rule)
        for detection in tuned.detection.detections.values():
            adapt_values(detection)
        lucene = LuceneBackend(pipeline()).convert(SigmaCollection([tuned]))
        result.lucene_tuned = lucene[0] if len(lucene) == 1 else None
    except (SigmaError, NotImplementedError, ValueError, TypeError, re.error) as error:
        result.error += f" tuned: {type(error).__name__}: {str(error)[:120]}"
    try:
        sql = sqliteBackend(pipeline()).convert(SigmaCollection([deepcopy(rule)]))
        statement = sql[0] if len(sql) == 1 else ""
        marker = " WHERE "
        if marker in statement:
            result.sql_where = statement.split(marker, 1)[1]
    except (SigmaError, NotImplementedError, ValueError, TypeError) as error:
        result.error += f" sql: {type(error).__name__}: {str(error)[:120]}"
    return result
