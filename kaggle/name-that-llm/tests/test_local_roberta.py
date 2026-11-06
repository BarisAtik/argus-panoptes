"""Key mapping on tiny fake tensors. No wheel needed."""
import pytest

torch = pytest.importorskip("torch")
from ntl.local_roberta import convert_state_dict, rename_key  # noqa: E402


def test_renames_match_hugging_face_names():
    assert rename_key("curated_encoder.embeddings.inner.word_embeddings.weight") == \
        "embeddings.word_embeddings.weight"
    assert rename_key("curated_encoder.embeddings.inner.layer_norm.bias") == "embeddings.LayerNorm.bias"
    assert rename_key("curated_encoder.layers.3.ffn_output_layernorm.weight") == \
        "encoder.layer.3.output.LayerNorm.weight"
    assert rename_key("curated_encoder.layers.3.mha.output.bias") == \
        "encoder.layer.3.attention.output.dense.bias"
    assert rename_key("scalar_weight.layer_weights") is None


def test_packed_attention_splits_in_query_key_value_order():
    packed = torch.arange(24.0).reshape(6, 4)
    out = convert_state_dict({"curated_encoder.layers.0.mha.input.weight": packed})
    assert torch.equal(out["encoder.layer.0.attention.self.query.weight"], packed[:2])
    assert torch.equal(out["encoder.layer.0.attention.self.key.weight"], packed[2:4])
    assert torch.equal(out["encoder.layer.0.attention.self.value.weight"], packed[4:6])
