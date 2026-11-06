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


def tiny_model(n, vocab):
    return BertForSequenceClassification(BertConfig(
        vocab_size=vocab + 8, hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
        intermediate_size=16, num_labels=n, pad_token_id=0))


def test_padding_is_per_batch_and_predictions_keep_row_order(tmp_path):
    from ntl.hf_train import batches, predict

    texts = ["a b c d e f g h i j k l", "a", "a b", "b"]
    tokenizer, vocab = tiny_tokenizer(texts)
    widths = [b["input_ids"].shape[1] for b, _ in batches(tokenizer, texts[1:], None, 2, 32, False)]
    assert max(widths) <= 2
    args = argparse.Namespace(batch_size=2, max_length=32)
    model = tiny_model(3, vocab)
    together = predict(model, tokenizer, texts, args, "cpu")
    alone = predict(model, tokenizer, texts[:1], args, "cpu")
    assert np.allclose(together[0], alone[0], atol=1e-5)


def test_saved_folds_predict_like_the_trained_model(tmp_path):
    from ntl.hf_train import predict, predict_folds, save_classes

    texts = ["alpha beta", "gamma delta"]
    tokenizer, vocab = tiny_tokenizer(texts)
    model = tiny_model(2, vocab)
    save_classes(tmp_path, ["a", "b"])
    model.save_pretrained(tmp_path / "fold0")
    args = argparse.Namespace(batch_size=2, max_length=8)
    proba, classes = predict_folds(tmp_path, "unused", texts, args, "cpu", tokenizer)
    assert classes == ["a", "b"]
    assert np.allclose(proba, predict(model, tokenizer, texts, args, "cpu"), atol=1e-5)


def test_lora_trains_adapter_only_and_reloads(tmp_path):
    pytest.importorskip("peft")
    from ntl.hf_train import predict, predict_folds, save_classes, train_one, with_lora

    texts = ["alpha beta gamma", "delta epsilon zeta", "alpha gamma", "zeta delta"]
    tokenizer, vocab = tiny_tokenizer(texts)
    base_dir = tmp_path / "base"
    tiny_model(2, vocab).save_pretrained(base_dir)
    tokenizer.save_pretrained(base_dir)
    model = with_lora(BertForSequenceClassification.from_pretrained(base_dir), r=2)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    assert 0 < trainable < sum(p.numel() for p in model.parameters()) / 2
    frozen = next(p for n, p in model.named_parameters() if "word_embeddings" in n).clone()
    args = argparse.Namespace(epochs=2, batch_size=2, max_length=8, lr=1e-2, label_smoothing=0.0,
                              grad_accum=2)
    train_one(model, tokenizer, texts, np.array([0, 1, 0, 1]), texts, args, "cpu")
    assert torch.equal(frozen, next(p for n, p in model.named_parameters()
                                    if "word_embeddings" in n))
    save_classes(tmp_path / "folds", ["a", "b"])
    model.save_pretrained(tmp_path / "folds" / "fold0")
    proba, _ = predict_folds(tmp_path / "folds", str(base_dir), texts, args, "cpu", tokenizer)
    assert np.allclose(proba, predict(model, tokenizer, texts, args, "cpu"), atol=1e-4)
