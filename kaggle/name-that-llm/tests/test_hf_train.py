"""Runs the transformer loop on a tiny random model, so it needs no download and no GPU."""
import argparse

import numpy as np
import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from tokenizers import Tokenizer, models, pre_tokenizers  # noqa: E402
from transformers import BertConfig, BertForSequenceClassification, PreTrainedTokenizerFast  # noqa: E402

from ntl.hf_train import run, write_oof  # noqa: E402


def tiny_tokenizer(texts):
    vocab = {"[PAD]": 0, "[UNK]": 1}
    for t in texts:
        for w in t.lower().split():
            vocab.setdefault(w, len(vocab))
    tok = Tokenizer(models.WordLevel(vocab, unk_token="[UNK]"))
    tok.pre_tokenizer = pre_tokenizers.Whitespace()
    return PreTrainedTokenizerFast(tokenizer_object=tok, pad_token="[PAD]", unk_token="[UNK]"), len(vocab)


def test_transformer_cv_produces_aligned_oof(small, tmp_path):
    train, _, _ = small
    train = train[train["prompt_id"].isin(train["prompt_id"].unique()[:6])].reset_index(drop=True)
    tokenizer, vocab = tiny_tokenizer(train["text"].str.lower().tolist())

    def build(n):
        return BertForSequenceClassification(BertConfig(
            vocab_size=vocab + 8, hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
            intermediate_size=16, num_labels=n))

    args = argparse.Namespace(folds=2, seed=0, epochs=1, batch_size=8, max_length=32, lr=1e-3,
                              label_smoothing=0.0, save_models=False, out=str(tmp_path))
    proba, folds = run(train, args, build, tokenizer, "cpu")
    assert proba.shape == (len(train), 18)
    assert np.allclose(proba.sum(axis=1), 1, atol=1e-5)
    write_oof(train, proba, folds, tmp_path)
    assert (tmp_path / "oof_transformer.parquet").exists()
