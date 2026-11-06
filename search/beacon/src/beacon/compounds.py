"""Split Dutch compounds, so that `register` can find `algoritmeregister`.

Dutch writes compounds as one word, and BM25 sees them as unrelated terms. A word is split only
when every part is a known word. Known words come from the corpus and, if `wordfreq` is
installed, a list of common Dutch words. A small corpus alone is not enough: `register` hardly
occurs by itself in the test corpus, so `algoritmeregister` stayed whole. Neither source reads
queries or labels, so they cannot leak them.

Two implementations exist on purpose. `Decompounder` is used by the local backend. For
Elasticsearch, `analysis_settings` in `backends/elastic.py` passes the same word list to Lucene's
`dictionary_decompounder`, which looks for known words inside a token instead of cutting it
into exact pieces. The two will not give identical results, so measure each one.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from functools import lru_cache

from .text import STOPWORDS

MIN_PART = 4
MIN_WORD = 9
LINKERS = ("", "s", "e", "en", "n")
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def build_vocabulary(
    texts: Iterable[str], min_document_frequency: int = 2, max_words: int = 20_000
) -> dict[str, int]:
    """Words of at least MIN_PART letters that occur in at least two texts."""
    frequency: Counter[str] = Counter()
    for text in texts:
        frequency.update(set(_WORD.findall(text.lower())))
    known = {
        word: count
        for word, count in frequency.items()
        if count >= min_document_frequency and len(word) >= MIN_PART and word not in STOPWORDS
    }
    return dict(sorted(known.items(), key=lambda item: (-item[1], item[0]))[:max_words])


def dutch_lexicon(top_n: int = 30_000) -> dict[str, int]:
    """Common Dutch words from `wordfreq`, for parts that a small corpus never has on their own.

    Needs `pip install wordfreq`. Its word lists are CC-BY-SA 4.0, and nothing from them is
    stored in this repository.
    """
    from wordfreq import top_n_list

    words = top_n_list("nl", top_n)
    # Rank stands in for frequency, so that common words win ties when splitting.
    return {
        word: top_n - rank
        for rank, word in enumerate(words)
        if len(word) >= MIN_PART and word.isalpha() and word not in STOPWORDS
    }


def compound_vocabulary(texts: Iterable[str]) -> dict[str, int]:
    """Corpus words plus the common-word lexicon when `wordfreq` is installed."""
    vocabulary = build_vocabulary(texts)
    try:
        return {**dutch_lexicon(), **vocabulary}
    except ImportError:
        return vocabulary


class Decompounder:
    def __init__(self, vocabulary: Mapping[str, int]):
        self.vocabulary = dict(vocabulary)
        self._split = lru_cache(maxsize=200_000)(self._search)

    def split(self, word: str) -> list[str]:
        """The parts of a compound, or an empty list when it should stay whole."""
        return self._split(word.lower()) if len(word) >= MIN_WORD else []

    def _search(self, word: str) -> list[str]:
        best: list[list[str] | None] = [None] * (len(word) + 1)
        best[len(word)] = []
        for start in range(len(word) - MIN_PART, -1, -1):
            for end in range(start + MIN_PART, len(word) + 1):
                part = word[start:end]
                if part not in self.vocabulary or part == word:
                    continue
                for linker in LINKERS:
                    stop = end + len(linker)
                    if stop > len(word) or word[end:stop] != linker:
                        continue
                    rest = best[stop]
                    if rest is None:
                        continue
                    candidate = [part, *rest]
                    if best[start] is None or self._better(candidate, best[start]):
                        best[start] = candidate
        parts = best[0] or []
        return parts if len(parts) >= 2 else []  # one part with a linker is just an inflection

    def _better(self, candidate: list[str], current: list[str]) -> bool:
        """Fewer parts first, then the parts that are more common in the corpus."""

        def rank(parts: list[str]) -> tuple[int, int]:
            return (-len(parts), min(self.vocabulary[p] for p in parts))

        return rank(candidate) > rank(current)

    def expand(self, words: Iterable[str]) -> list[str]:
        """The original words, each followed by its parts."""
        output: list[str] = []
        for word in words:
            output.append(word)
            output.extend(self.split(word))
        return output
