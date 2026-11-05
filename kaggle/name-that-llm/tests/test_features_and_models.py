import numpy as np
import pytest
from sklearn.metrics import balanced_accuracy_score

from ntl.data import LABEL, TEXT
from ntl.features import STYLE_NAMES, StyleFeatures, mask_content_words, style_vector
from ntl.models import REGISTRY


def test_masking_removes_topic_keeps_rhythm():
    masked = mask_content_words("The Quantum reactor — however — failed, and it melted.")
    assert "quantum" not in masked.lower() and "reactor" not in masked
    assert "the X x — however — x, and it x." == masked


def test_style_vector_aligned_with_names():
    assert len(style_vector("One sentence here. And another; a third!")) == len(STYLE_NAMES)
    assert StyleFeatures().get_feature_names_out().tolist() == list(STYLE_NAMES)


def test_style_vector_survives_empty_text():
    assert all(np.isfinite(style_vector("")))


def test_style_counts_are_per_100_words():
    v = dict(zip(STYLE_NAMES, style_vector("a b c d e f g h i j, k")))
    assert v["comma"] == pytest.approx(100 / 11)


@pytest.mark.parametrize("name", ["tfidf_lr", "style_lr"])
def test_candidates_beat_chance_on_unseen_prompts(small, name):
    train, test, truth = small
    model = REGISTRY[name]().fit(train[TEXT].tolist(), train[LABEL])
    score = balanced_accuracy_score(truth[LABEL], model.predict(test[TEXT].tolist()))
    assert score > 3 / 18
