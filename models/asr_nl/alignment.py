"""Word alignment and error counting, including an error class that matters for Dutch.

Dutch writes compounds as one word ("voetbalveld"). ASR models often split them, or join words
that should stay apart. Standard WER scores one spacing slip as two or more errors. Counting
these separately shows how much of the error is spelling convention and how much is misheard
speech.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class ErrorCounts:
    hits: int = 0
    substitutions: int = 0
    deletions: int = 0
    insertions: int = 0
    compound_splits: int = 0  # ref "voetbalveld" -> hyp "voetbal veld"
    compound_joins: int = 0  # ref "te koop" -> hyp "tekoop"
    pairs: Counter = field(default_factory=Counter)

    @property
    def reference_words(self) -> int:
        return self.hits + self.substitutions + self.deletions

    @property
    def errors(self) -> int:
        return self.substitutions + self.deletions + self.insertions

    @property
    def compound_cost(self) -> int:
        """Word errors in standard WER that are only due to compound spacing."""
        return 2 * self.compound_splits + 2 * self.compound_joins


def levenshtein_ops(ref: list, hyp: list) -> list[tuple[str, object, object]]:
    """Return (op, ref_item, hyp_item) with op in {hit, sub, del, ins}. Minimal edit path."""
    n, m = len(ref), len(hyp)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = i
    for j in range(1, m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        previous, row, item = cost[i - 1], cost[i], ref[i - 1]
        for j in range(1, m + 1):
            sub = previous[j - 1] + (item != hyp[j - 1])
            row[j] = min(sub, previous[j] + 1, row[j - 1] + 1)
    ops: list[tuple[str, object, object]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i and j and cost[i][j] == cost[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            ops.append(("hit" if ref[i - 1] == hyp[j - 1] else "sub", ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif j and cost[i][j] == cost[i][j - 1] + 1:
            ops.append(("ins", None, hyp[j - 1]))
            j -= 1
        else:
            ops.append(("del", ref[i - 1], None))
            i -= 1
    return ops[::-1]


def _count_compounds(ops: list[tuple[str, object, object]], counts: ErrorCounts) -> None:
    """A slip shows up as an adjacent sub+ins or sub+del with the same letters overall."""
    for (op_a, ref_a, hyp_a), (op_b, ref_b, hyp_b) in zip(ops, ops[1:]):
        if {op_a, op_b} == {"sub", "ins"}:
            hyp_joined = f"{hyp_a}{hyp_b}"
            ref_word = ref_a if op_a == "sub" else ref_b
            if hyp_joined == ref_word:
                counts.compound_splits += 1
        elif {op_a, op_b} == {"sub", "del"}:
            ref_joined = f"{ref_a}{ref_b}"
            hyp_word = hyp_a if op_a == "sub" else hyp_b
            if ref_joined == hyp_word:
                counts.compound_joins += 1


def score(reference: str, hypothesis: str) -> ErrorCounts:
    ops = levenshtein_ops(reference.split(), hypothesis.split())
    counts = ErrorCounts()
    for op, ref_word, hyp_word in ops:
        if op == "hit":
            counts.hits += 1
        elif op == "sub":
            counts.substitutions += 1
            counts.pairs[(ref_word, hyp_word)] += 1
        elif op == "del":
            counts.deletions += 1
            counts.pairs[(ref_word, "∅")] += 1
        else:
            counts.insertions += 1
            counts.pairs[("∅", hyp_word)] += 1
    _count_compounds(ops, counts)
    return counts


def char_errors(reference: str, hypothesis: str) -> tuple[int, int]:
    """(character edits, reference characters) for CER, with spaces counted as characters."""
    ops = levenshtein_ops(list(reference), list(hypothesis))
    return sum(op != "hit" for op, _, _ in ops), len(reference)
