"""Audit the data before trusting any metric computed on it.

Answers: is the test set contaminated by training data? Do duplicates disagree on their label?
Is this all Dutch? Could a one-feature model already score well (a sign of a leak)?
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from zlib import crc32

import numpy as np

from text_nl.data import Split

_TOKEN = re.compile(r"[^\W\d_]+|\d+", re.UNICODE)
_URL = re.compile(r"https?://|www\.|\b[\w.-]+\.(?:nl|com|be)\b", re.IGNORECASE)
_PROMO = re.compile(r"\b(te koop|bestel(?:len)?|gratis verzending|kortingscode|actieprijs|"
                    r"webshop|bezoek onze)\b", re.IGNORECASE)
DUTCH_STOPWORDS = frozenset(
    "de het een en van ik te dat die in je niet zijn is op aan met als voor had er maar om hem "
    "dan zou of wat mijn men dit zo door over ze zich bij ook tot jij uit ben nog naar heb "
    "deze boek was werd veel wel geen".split()
)
ENGLISH_STOPWORDS = frozenset(
    "the of and to in that it is was for on with as his they at be this have from or one had "
    "by not but what all were we when your can said there use an each which she do how".split()
)
MERSENNE = (1 << 61) - 1


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(unicodedata.normalize("NFKC", text).lower())


def canonical(text: str) -> str:
    return " ".join(tokens(text))


def language_guess(text: str) -> str:
    """Stopword vote. Crude but dependency-free; "unclear" means too short or no signal."""
    words = tokens(text)
    if len(words) < 5:
        return "unclear"
    dutch = sum(w in DUTCH_STOPWORDS for w in words)
    english = sum(w in ENGLISH_STOPWORDS for w in words)
    if dutch == english:
        return "unclear"
    return "nl" if dutch > english else "en"


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def _shingles(text: str, size: int) -> set[int]:
    words = tokens(text)
    if len(words) < size:
        return {crc32(" ".join(words).encode())} if words else set()
    return {crc32(" ".join(words[i : i + size]).encode()) for i in range(len(words) - size + 1)}


def near_duplicate_pairs(
    texts: list[str],
    *,
    threshold: float = 0.7,
    shingle: int = 3,
    num_perm: int = 64,
    bands: int = 16,
    seed: int = 0,
) -> list[tuple[int, int]]:
    """MinHash + LSH candidates, verified by true Jaccard similarity. Scales to 100k reviews."""
    rng = np.random.default_rng(seed)
    a = rng.integers(1, MERSENNE, num_perm, dtype=np.uint64)
    b = rng.integers(0, MERSENNE, num_perm, dtype=np.uint64)
    sets = [_shingles(t, shingle) for t in texts]
    buckets: dict[tuple, list[int]] = defaultdict(list)
    rows = num_perm // bands
    for index, items in enumerate(sets):
        if not items:
            continue
        values = np.fromiter(items, dtype=np.uint64)[:, None]
        # uint64 wraparound is fine: this only needs to act as a hash family.
        signature = ((a * values + b) & np.uint64(MERSENNE)).min(axis=0)
        for band in range(bands):
            key = (band, signature[band * rows : (band + 1) * rows].tobytes())
            buckets[key].append(index)
    pairs: set[tuple[int, int]] = set()
    for members in buckets.values():
        if not 1 < len(members) <= 200:
            continue
        for offset, i in enumerate(members):
            for j in members[offset + 1 :]:
                if (i, j) in pairs:
                    continue
                union = len(sets[i] | sets[j])
                if union and len(sets[i] & sets[j]) / union >= threshold:
                    pairs.add((i, j))
    return sorted(pairs)


def duplicate_groups(texts: list[str], **kwargs) -> np.ndarray:
    """Group id per text: exact (after canonicalization) or near duplicates share a group."""
    n = len(texts)
    forest = UnionFind(n)
    first_seen: dict[str, int] = {}
    for index, text in enumerate(texts):
        key = canonical(text)
        if key in first_seen:
            forest.union(index, first_seen[key])
        else:
            first_seen[key] = index
    for i, j in near_duplicate_pairs(texts, **kwargs):
        forest.union(i, j)
    return np.array([forest.find(i) for i in range(n)])


def group_split(
    labels: list[int], groups: np.ndarray, val_fraction: float, seed: int
) -> tuple[list[int], list[int]]:
    """Validation split where no duplicate group straddles the border (stratified by label)."""
    rng = np.random.default_rng(seed)
    unique = np.unique(groups)
    rng.shuffle(unique)
    target = int(val_fraction * len(labels))
    wanted = {label: count * val_fraction for label, count in Counter(labels).items()}
    members = defaultdict(list)
    for index, group in enumerate(groups):
        members[int(group)].append(index)
    val: list[int] = []
    taken: Counter = Counter()
    for group in unique:
        items = members[int(group)]
        group_labels = Counter(labels[i] for i in items)
        if len(val) < target and all(taken[lab] < wanted[lab] for lab in group_labels):
            val += items
            taken.update(group_labels)
    in_val = set(val)
    return [i for i in range(len(labels)) if i not in in_val], sorted(val)


def length_only_accuracy(texts: list[str], labels: list[int]) -> float:
    """Best threshold on length alone, on the same data. Well above majority = suspicious."""
    lengths = np.array([len(tokens(t)) for t in texts])
    y = np.array(labels)
    order = np.argsort(lengths)
    positives_left = np.cumsum(y[order])
    n = len(y)
    left = np.arange(1, n + 1)
    # Predict one class under the threshold, the other class over it.
    correct = (left - positives_left) + (y.sum() - positives_left)
    return float(max(correct.max(), (n - correct).max()) / n)


def audit_splits(train: Split, test: Split, **lsh) -> dict:
    n_train, n_test = len(train), len(test)
    texts = train.texts + test.texts
    labels = np.array(train.labels + test.labels)
    groups = duplicate_groups(texts, **lsh)
    train_groups = set(groups[:n_train].tolist())
    test_leaked = [i for i in range(n_test) if int(groups[n_train + i]) in train_groups]

    by_group = defaultdict(set)
    for group, label in zip(groups.tolist(), labels.tolist()):
        by_group[group].add(label)
    sizes = Counter(groups.tolist())
    conflicts = sum(1 for group, seen in by_group.items() if len(seen) > 1)
    languages = Counter(language_guess(t) for t in texts)
    length_values = np.array([len(tokens(t)) for t in texts])
    report = {
        "train": n_train,
        "test": n_test,
        "label_balance_train": dict(Counter(train.labels)),
        "label_balance_test": dict(Counter(test.labels)),
        "empty_texts": int(sum(1 for t in texts if not tokens(t))),
        "duplicate_groups": sum(1 for size in sizes.values() if size > 1),
        "texts_in_duplicate_groups": sum(size for size in sizes.values() if size > 1),
        "test_texts_also_in_train": len(test_leaked),
        "test_leak_share": len(test_leaked) / max(1, n_test),
        "groups_with_conflicting_labels": conflicts,
        "language": dict(languages),
        "contains_url": sum(bool(_URL.search(t)) for t in texts),
        "promo_phrases": sum(bool(_PROMO.search(t)) for t in texts),
        "length_words_median": float(np.median(length_values)),
        "length_words_p99": float(np.quantile(length_values, 0.99)),
        "length_only_train_accuracy": length_only_accuracy(train.texts, train.labels),
        "majority_train_accuracy":
            max(Counter(train.labels).values()) / max(1, n_train),
    }
    report["_groups"] = groups
    report["_test_leaked"] = test_leaked
    return report
