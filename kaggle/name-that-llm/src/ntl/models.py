"""Sklearn candidates. All expose predict_proba, so the CV loop treats them the same."""
from __future__ import annotations

from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import make_pipeline, make_union
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from .features import StyleFeatures, char_tfidf, mask_content_words, word_tfidf


class NBEvidence(BaseEstimator, TransformerMixin):
    """Replace sparse text features with ComplementNB log-probabilities per class."""

    def fit(self, x, y):
        self.nb_ = ComplementNB(alpha=0.1).fit(x, y)
        return self

    def transform(self, x):
        return self.nb_.predict_joint_log_proba(x)


def _mask_all(texts):
    return [mask_content_words(t) for t in texts]


def _lr(c: float = 10.0) -> LogisticRegression:
    return LogisticRegression(C=c, max_iter=2000, class_weight="balanced")


def tfidf_lr():
    """Raw word + char n-grams. Strongest on seen topics, most at risk on unseen ones."""
    return make_pipeline(make_union(word_tfidf(), char_tfidf()), _lr())


def masked_lr():
    """Same model on content-masked text: the "does style alone carry this?" check."""
    return make_pipeline(
        FunctionTransformer(_mask_all),
        make_union(word_tfidf(token_pattern=r"\S+", ngram_range=(1, 3)),
                   char_tfidf(analyzer="char", ngram_range=(1, 4))),
        _lr(),
    )


def style_lr():
    """23 interpretable numbers. If this beats chance by much, the signal is not just vocabulary."""
    return make_pipeline(StyleFeatures(), StandardScaler(), _lr(1.0))


def style_gbm():
    return make_pipeline(
        StyleFeatures(),
        HistGradientBoostingClassifier(max_iter=150, learning_rate=0.08, class_weight="balanced"),
    )


def word_lr():
    return make_pipeline(word_tfidf(), _lr())


def char_lr():
    return make_pipeline(char_tfidf(), _lr())


def tfidf_lr_c100():
    """Weaker regularisation: tf-idf rows are unit length, so C=10 can underfit."""
    return make_pipeline(make_union(word_tfidf(), char_tfidf()), _lr(100.0))


def nb_lr():
    """Logistic regression on one-vs-rest naive Bayes evidence, a sturdy small-data text baseline."""
    return make_pipeline(make_union(word_tfidf(), char_tfidf()), NBEvidence(), _lr(1.0))


REGISTRY = {"tfidf_lr": tfidf_lr, "masked_lr": masked_lr, "style_lr": style_lr,
            "style_gbm": style_gbm, "word_lr": word_lr, "char_lr": char_lr,
            "tfidf_lr_c100": tfidf_lr_c100, "nb_lr": nb_lr}
