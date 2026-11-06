"""Check each claim in an answer against the passage it cites.

The citation check in rag.py only proves that a number points at a passage. This goes a step
further, with no LLM and no network: split the answer into claims, then look for evidence that
the cited passage does not say this. It is a cheap filter, and it cannot understand meaning, so
`supported` means "no problem found". See reports/ak-groundedness.md for what it misses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from .citations import extract_refs
from .text import sentences, tokens

_CITATION = re.compile(r"\[(\d+)\]")
_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)*\b")
_NEGATION = frozenset("niet geen nooit zonder niets noch verboden".split())
_STRONG = frozenset("moet moeten verplicht altijd uitsluitend alleen nooit".split())
_WEAK = frozenset("kan kunnen mag mogen eventueel desgewenst aanbevolen".split())


@dataclass(frozen=True)
class Thresholds:
    # Defaults are the values frozen on dev claims, see evals/frozen-grounded.json. Similarity
    # needs an embedder and is skipped without one. Modality checks are kept for those who want
    # them, but they did not earn their false alarms.
    min_terms: float = 0.4
    min_similarity: float = 0.9
    check_modality: bool = False
    check_negation: bool = True


@dataclass
class ClaimCheck:
    claim: str
    citations: list[int]
    supported: bool
    reasons: list[str] = field(default_factory=list)
    best_sentence: str = ""
    term_support: float = 0.0
    similarity: float = 0.0


def split_claims(answer: str) -> list[tuple[str, list[int]]]:
    """Sentences with the citations they carry. A trailing citation joins its sentence."""
    claims: list[tuple[str, list[int]]] = []
    for sentence in sentences(answer.replace("\n", " ")):
        cited = [int(n) for n in _CITATION.findall(sentence)]
        text = _CITATION.sub("", sentence).strip(" .")
        if text:
            claims.append((text, cited))
        elif claims and cited:
            claims[-1][1].extend(cited)
    return claims


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in _NUMBER.findall(text)}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[^\W\d_]+", text.lower()))


def best_sentence(claim: str, passage: str) -> tuple[str, float]:
    """The passage sentence sharing most stems with the claim, and the share of claim stems."""
    terms = set(tokens(claim))
    if not terms:
        return "", 0.0
    pieces = sentences(passage) or [passage]
    scored = [(len(terms & set(tokens(piece))) / len(terms), piece) for piece in pieces]
    score, piece = max(scored, key=lambda item: item[0])
    return piece, score


def check_claim(
    claim: str,
    passages: list[str],
    thresholds: Thresholds = Thresholds(),  # noqa: B008
    embed=None,
) -> ClaimCheck:
    """Judge one claim against the text of the passages it cites."""
    result = ClaimCheck(claim, [], True)
    if not passages:
        result.supported = False
        result.reasons.append("no citation")
        return result
    text = " ".join(passages)
    all_terms = set(tokens(text))
    terms = set(tokens(claim))
    result.term_support = len(terms & all_terms) / len(terms) if terms else 0.0
    result.best_sentence, sentence_support = best_sentence(claim, text)

    missing_numbers = _numbers(claim) - _numbers(text)
    if missing_numbers:
        result.reasons.append(f"number not in source: {', '.join(sorted(missing_numbers))}")
    missing_refs = set(extract_refs(claim)) - set(extract_refs(text))
    if missing_refs:
        result.reasons.append(f"citation not in source: {', '.join(sorted(missing_refs))}")
    if result.term_support < thresholds.min_terms:
        result.reasons.append(f"few source terms: {result.term_support:.2f}")

    claim_words, sentence_words = _words(claim), _words(result.best_sentence)
    if thresholds.check_negation and sentence_support >= 0.4:
        if bool(claim_words & _NEGATION) != bool(sentence_words & _NEGATION):
            result.reasons.append("negation differs from the closest sentence")
    if thresholds.check_modality and sentence_support >= 0.4:
        if claim_words & _STRONG and sentence_words & _WEAK and not sentence_words & _STRONG:
            result.reasons.append("source is weaker: claim says must, source says can")
        if claim_words & _WEAK and sentence_words & _STRONG and not sentence_words & _WEAK:
            result.reasons.append("source is stronger: claim says can, source says must")
    if embed is not None and thresholds.min_similarity > 0:
        vectors = embed([claim, *(sentences(text) or [text])])
        result.similarity = float(np.max(vectors[1:] @ vectors[0]))
        if result.similarity < thresholds.min_similarity:
            result.reasons.append(f"low similarity: {result.similarity:.2f}")
    result.supported = not result.reasons
    return result


def check_answer(
    answer: str,
    contexts: list[str],
    thresholds: Thresholds = Thresholds(),  # noqa: B008
    embed=None,
) -> list[ClaimCheck]:
    """Check every claim of an answer against the passages it cites, 1-based."""
    checks = []
    for claim, cited in split_claims(answer):
        passages = [contexts[n - 1] for n in cited if 1 <= n <= len(contexts)]
        check = check_claim(claim, passages, thresholds, embed)
        check.citations = cited
        checks.append(check)
    return checks
