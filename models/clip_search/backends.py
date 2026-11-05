"""CLIP-style encoders behind one interface. All vectors come back L2-normalized."""

from __future__ import annotations

from typing import Protocol

import numpy as np


class Backend(Protocol):
    name: str

    def encode_images(self, images: list) -> np.ndarray: ...
    def encode_texts(self, texts: list[str]) -> np.ndarray: ...


def normalize(vectors: np.ndarray) -> np.ndarray:
    return vectors / np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9, None)


def _features(output):
    """Newer transformers wrap features in an output object; older ones return a tensor."""
    return getattr(output, "pooler_output", output)


class HFClip:
    """Any Hugging Face CLIP model. English text encoder for the OpenAI checkpoints."""

    def __init__(self, model_id: str, device: str | None = None, model=None, processor=None):
        import torch
        from transformers import CLIPModel, CLIPProcessor

        self.name = model_id
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = (model or CLIPModel.from_pretrained(model_id)).to(self.device).eval()
        self.processor = processor or CLIPProcessor.from_pretrained(model_id)

    def encode_images(self, images: list) -> np.ndarray:
        import torch

        inputs = self.processor(images=images, return_tensors="pt").to(self.device)
        with torch.inference_mode():
            output = _features(self.model.get_image_features(**inputs))
        return normalize(output.float().cpu().numpy())

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        import torch

        inputs = self.processor(text=texts, return_tensors="pt", padding=True,
                                truncation=True).to(self.device)
        with torch.inference_mode():
            output = _features(self.model.get_text_features(**inputs))
        return normalize(output.float().cpu().numpy())


class OpenClip:
    """open_clip models, including the multilingual XLM-Roberta text encoder."""

    def __init__(self, model_name: str, pretrained: str, device: str | None = None):
        import open_clip
        import torch

        self.name = f"{model_name}/{pretrained}"
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained, device=self.device
        )
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(model_name)

    def encode_images(self, images: list) -> np.ndarray:
        import torch

        batch = torch.stack([self.preprocess(image) for image in images]).to(self.device)
        with torch.inference_mode():
            return normalize(self.model.encode_image(batch).float().cpu().numpy())

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        import torch

        tokens = self.tokenizer(texts).to(self.device)
        with torch.inference_mode():
            return normalize(self.model.encode_text(tokens).float().cpu().numpy())


def load_backend(spec: str) -> Backend:
    """`hf:openai/clip-vit-base-patch32` or `openclip:<model>:<pretrained>`."""
    kind, _, rest = spec.partition(":")
    if kind == "hf":
        return HFClip(rest)
    if kind == "openclip":
        model_name, _, pretrained = rest.partition(":")
        return OpenClip(model_name, pretrained)
    raise ValueError(f"unknown backend spec {spec!r}")
