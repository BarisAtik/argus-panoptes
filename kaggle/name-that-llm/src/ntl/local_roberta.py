"""Rebuild a usable RoBERTa from spaCy's en_core_web_trf wheel, for machines without Hugging Face.

Some cloud sessions can reach GitHub but not huggingface.co. The wheel (MIT licence, Explosion)
holds a real roberta-base encoder, plus its vocabulary and merges, in spaCy's own format. This turns
it into an ordinary folder that `from_pretrained` can read:

    curl -L -o data/trf.whl https://github.com/explosion/spacy-models/releases/download/\
en_core_web_trf-3.8.0/en_core_web_trf-3.8.0-py3-none-any.whl
    python -m ntl.local_roberta --wheel data/trf.whl --out artifacts/roberta-base-spacy

These are not the stock weights: spaCy fine-tuned them for tagging and parsing. That is a mild
handicap at most, but say so next to any score they produce. On Kaggle, attach a normal snapshot.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import zipfile
from pathlib import Path

MODEL_MEMBER = "en_core_web_trf/en_core_web_trf-3.8.0/transformer/model"
CONFIG = {
    "architectures": ["RobertaModel"], "model_type": "roberta", "vocab_size": 50265,
    "hidden_size": 768, "num_hidden_layers": 12, "num_attention_heads": 12,
    "intermediate_size": 3072, "hidden_act": "gelu", "hidden_dropout_prob": 0.1,
    "attention_probs_dropout_prob": 0.1, "max_position_embeddings": 514, "type_vocab_size": 1,
    "layer_norm_eps": 1e-5, "pad_token_id": 1, "bos_token_id": 0, "eos_token_id": 2,
}
RENAMES = (
    (r"^curated_encoder\.embeddings\.inner\.layer_norm\.", "embeddings.LayerNorm."),
    (r"^curated_encoder\.embeddings\.inner\.", "embeddings."),
    (r"^curated_encoder\.layers\.(\d+)\.mha\.output\.", r"encoder.layer.\1.attention.output.dense."),
    (r"^curated_encoder\.layers\.(\d+)\.attn_output_layernorm\.",
     r"encoder.layer.\1.attention.output.LayerNorm."),
    (r"^curated_encoder\.layers\.(\d+)\.ffn\.intermediate\.",
     r"encoder.layer.\1.intermediate.dense."),
    (r"^curated_encoder\.layers\.(\d+)\.ffn\.output\.", r"encoder.layer.\1.output.dense."),
    (r"^curated_encoder\.layers\.(\d+)\.ffn_output_layernorm\.",
     r"encoder.layer.\1.output.LayerNorm."),
)
COMBINED_ATTENTION = re.compile(r"^curated_encoder\.layers\.(\d+)\.mha\.input\.(weight|bias)$")


def rename_key(key: str) -> str | None:
    """HF name for a spaCy parameter, or None for anything that isn't part of the encoder."""
    for pattern, new in RENAMES:
        if re.search(pattern, key):
            return re.sub(pattern, new, key)
    return None


def convert_state_dict(state: dict) -> dict:
    """spaCy packs query, key and value into one linear layer, in that order. HF keeps three."""
    import torch

    out = {}
    for key, value in state.items():
        combined = COMBINED_ATTENTION.match(key)
        if combined:
            layer, kind = combined.groups()
            for name, part in zip(("query", "key", "value"), torch.chunk(value, 3, dim=0)):
                out[f"encoder.layer.{layer}.attention.self.{name}.{kind}"] = part.clone()
        elif (new := rename_key(key)) is not None:
            out[new] = value
    return out


def read_wheel(wheel: Path) -> tuple[dict, list, dict]:
    """State dict, BPE merges and vocabulary. `weights_only` keeps the checkpoint from running code."""
    import msgpack
    import torch

    with zipfile.ZipFile(wheel) as archive:
        blob = archive.read(MODEL_MEMBER)
    outer = msgpack.unpackb(blob, raw=False, strict_map_key=False)
    bpe = msgpack.unpackb(outer["attrs"][3]["byte_bpe_processor"], raw=False)
    shim = msgpack.unpackb(next(s[0] for s in outer["shims"] if s), raw=False,
                           strict_map_key=False)
    checkpoint = next(v for v in shim.values() if isinstance(v, bytes))
    state = torch.load(io.BytesIO(checkpoint), map_location="cpu", weights_only=True)
    return state, bpe["merges"], bpe["vocab"]


def export(wheel: Path, out: Path) -> Path:
    from safetensors.torch import save_file

    state, merges, vocab = read_wheel(wheel)
    out.mkdir(parents=True, exist_ok=True)
    converted = convert_state_dict(state)
    save_file({k: v.contiguous() for k, v in converted.items()}, out / "model.safetensors")
    (out / "config.json").write_text(json.dumps(CONFIG, indent=2))
    (out / "vocab.json").write_text(json.dumps(vocab, ensure_ascii=False))
    (out / "merges.txt").write_text("#version: 0.2\n" + "\n".join(" ".join(m) for m in merges) + "\n")
    (out / "tokenizer_config.json").write_text(json.dumps(
        {"tokenizer_class": "RobertaTokenizer", "model_max_length": 512}))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wheel", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("artifacts/roberta-base-spacy"))
    args = ap.parse_args()
    print(f"wrote {export(args.wheel, args.out)}")


if __name__ == "__main__":
    main()
