"""Look at the data before believing any score on it."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence

from .data import Sentence
from .spans import ALL_LABELS, bio_spans


def surfaces(sentences: Sequence[Sentence]) -> list[tuple[str, str]]:
    """(lowercased entity text, label) for every gold mention."""
    return [
        (" ".join(s.tokens[a:b]).lower(), label)
        for s in sentences
        for a, b, label in bio_spans(s.tags)
    ]


def invalid_bio(sentences: Sequence[Sentence]) -> int:
    bad = 0
    for s in sentences:
        previous = "O"
        for tag in s.tags:
            if tag.startswith("I-") and previous[2:] != tag[2:]:
                bad += 1
            previous = tag
    return bad


def describe(sentences: Sequence[Sentence]) -> dict:
    mentions = surfaces(sentences)
    per_doc = Counter(s.doc_id for s in sentences)
    labels = Counter(label for _, label in mentions)
    total = sum(labels.values()) or 1
    return {
        "articles": len(per_doc),
        "sentences": len(sentences),
        "tokens": sum(len(s.tokens) for s in sentences),
        "mentions": len(mentions),
        "invalid_bio_tags": invalid_bio(sentences),
        **{f"share_{k}": labels[k] / total for k in ALL_LABELS},
        "largest_article_share": max(per_doc.values()) / max(len(sentences), 1),
    }


def leakage(train: Sequence[Sentence], test: Sequence[Sentence]) -> dict:
    """How much of `test` was already seen, as a sentence or as an entity string."""
    seen_sentences = {s.tokens for s in train}
    long_test = [s for s in test if len(s.tokens) >= 5]
    repeated = sum(s.tokens in seen_sentences for s in long_test)
    seen_entities = {text for text, _ in surfaces(train)}
    mentions = surfaces(test)
    known = sum(text in seen_entities for text, _ in mentions)
    return {
        "test_sentences_5plus_tokens": len(long_test),
        "exact_repeats_of_train_sentences": repeated,
        "repeat_share": repeated / max(len(long_test), 1),
        "test_mentions": len(mentions),
        "mentions_seen_in_train": known,
        "seen_share": known / max(len(mentions), 1),
    }


def label_conflicts(sentences: Sequence[Sentence], min_count: int = 3) -> dict:
    """Entity strings with more than one label: real ambiguity and annotator drift mixed."""
    by_text: dict[str, Counter] = defaultdict(Counter)
    for text, label in surfaces(sentences):
        by_text[text][label] += 1
    frequent = {t: c for t, c in by_text.items() if sum(c.values()) >= min_count}
    mixed = {t: c for t, c in frequent.items() if len(c) > 1}
    mentions = sum(sum(c.values()) for c in frequent.values())
    minority = sum(sum(c.values()) - c.most_common(1)[0][1] for c in mixed.values())
    return {
        "strings_seen_3plus": len(frequent),
        "strings_with_two_or_more_labels": len(mixed),
        "share_of_strings": len(mixed) / max(len(frequent), 1),
        "minority_label_mentions": minority,
        "minority_share_of_mentions": minority / max(mentions, 1),
    }
