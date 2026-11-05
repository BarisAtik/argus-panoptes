"""Three views of a passage, ordered by how much they rely on topic rather than on style."""
from __future__ import annotations

import re

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

WORD = re.compile(r"[A-Za-z']+")
STOP = frozenset(ENGLISH_STOP_WORDS)
_SENT = re.compile(r"[.!?;]+\s")

STYLE_NAMES = (
    "n_chars", "n_words", "n_sents", "words_per_sent", "sent_len_sd", "word_len_mean",
    "type_token", "stop_rate", "comma", "semicolon", "colon", "em_dash", "paren", "quote",
    "question", "exclaim", "digit", "upper_word", "contraction", "newline", "bullet", "bold",
    "starts_with_filler",
)
_FILLERS = ("certainly", "sure", "absolutely", "great", "of course", "here is", "here's")


def mask_content_words(text: str) -> str:
    """Replace non-stopwords by their first letter class, keeping punctuation and layout.

    Removes most topic while keeping rhythm. Prompts are unseen at test time, so features that
    survive this masking are the ones expected to transfer.
    """
    def repl(m: re.Match) -> str:
        w = m.group(0)
        if w.lower() in STOP:
            return w.lower()
        return "X" if w[0].isupper() else "x"
    return WORD.sub(repl, text)


def style_vector(text: str) -> list[float]:
    words = WORD.findall(text)
    n_words = max(len(words), 1)
    sent_lens = [len(WORD.findall(s)) for s in _SENT.split(text)]
    sent_lens = [s for s in sent_lens if s] or [n_words]
    per_100 = 100.0 / n_words
    lower = [w.lower() for w in words]
    return [
        len(text), len(words), len(sent_lens), float(np.mean(sent_lens)), float(np.std(sent_lens)),
        float(np.mean([len(w) for w in words])) if words else 0.0,
        len(set(lower)) / n_words,
        sum(w in STOP for w in lower) / n_words,
        text.count(",") * per_100, text.count(";") * per_100, text.count(":") * per_100,
        text.count("—") * per_100, text.count("(") * per_100,
        (text.count('"') + text.count("“")) * per_100,
        text.count("?") * per_100, text.count("!") * per_100,
        sum(c.isdigit() for c in text) * per_100,
        sum(w.isupper() and len(w) > 1 for w in words) * per_100,
        sum("'" in w for w in words) * per_100,
        text.count("\n") * per_100,
        len(re.findall(r"(?m)^\s*(?:[-*•]|\d+\.)\s|\s[-*•]\s", text)) * per_100,
        text.count("**") * per_100,
        float(text.lower().lstrip().startswith(_FILLERS)),
    ]


class StyleFeatures(BaseEstimator, TransformerMixin):
    """Hand-built stylometry; every column has a name you can defend in a write-up."""

    def fit(self, X, y=None):  # noqa: N803
        return self

    def transform(self, X):  # noqa: N803
        return np.asarray([style_vector(t) for t in X], dtype=np.float64)

    def get_feature_names_out(self, input_features=None):
        return np.array(STYLE_NAMES, dtype=object)


def word_tfidf(**kw) -> TfidfVectorizer:
    params = dict(ngram_range=(1, 2), min_df=2, max_features=200_000, sublinear_tf=True)
    return TfidfVectorizer(**(params | kw))


def char_tfidf(**kw) -> TfidfVectorizer:
    params = dict(analyzer="char_wb", ngram_range=(2, 5), min_df=2, max_features=300_000,
                  sublinear_tf=True)
    return TfidfVectorizer(**(params | kw))
