"""A byte-level CNN. Small on purpose: it trains on two CPU cores in about a minute,
and it reads any language and encoding without a tokenizer."""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from .dataset import MAX_CHARS


def encode(texts: list[str], max_len: int = MAX_CHARS) -> torch.Tensor:
    out = np.zeros((len(texts), max_len), dtype=np.int64)
    for i, t in enumerate(texts):
        b = t.encode("utf-8", "ignore")[:max_len]
        out[i, : len(b)] = np.frombuffer(b, dtype=np.uint8).astype(np.int64) + 1
    return torch.from_numpy(out)


class ByteCNN(nn.Module):
    def __init__(self, emb: int = 24, filters: int = 64, kernels: tuple[int, ...] = (3, 5, 9), dropout: float = 0.3):
        super().__init__()
        self.embed = nn.Embedding(257, emb, padding_idx=0)
        self.convs = nn.ModuleList(nn.Conv1d(emb, filters, k, padding=k // 2) for k in kernels)
        self.drop = nn.Dropout(dropout)
        self.head = nn.Linear(filters * len(kernels), 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        e = self.embed(x).transpose(1, 2)
        h = torch.cat([torch.relu(c(e)).amax(dim=2) for c in self.convs], dim=1)
        return self.head(self.drop(h)).squeeze(1)


def fit(texts: list[str], labels: list[int], epochs: int = 4, batch: int = 64, lr: float = 1e-3, seed: int = 0) -> ByteCNN:
    torch.manual_seed(seed)
    model = ByteCNN()
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    loss_fn = nn.BCEWithLogitsLoss()
    X, y = encode(texts), torch.tensor(labels, dtype=torch.float32)
    g = torch.Generator().manual_seed(seed)
    model.train()
    for _ in range(epochs):
        for idx in torch.randperm(len(X), generator=g).split(batch):
            opt.zero_grad()
            loss_fn(model(X[idx]), y[idx]).backward()
            opt.step()
    return model.eval()


@torch.no_grad()
def logits(model: ByteCNN, texts: list[str], batch: int = 256) -> np.ndarray:
    model.eval()
    return np.concatenate([model(encode(texts[i : i + batch])).numpy() for i in range(0, len(texts), batch)]) if texts else np.zeros(0)


def fit_temperature(z: np.ndarray, y: np.ndarray) -> float:
    """One-parameter calibration on held-out data (Guo et al., 2017)."""
    t = torch.tensor(0.0, requires_grad=True)
    Z, Y = torch.tensor(z, dtype=torch.float32), torch.tensor(y, dtype=torch.float32)
    opt = torch.optim.LBFGS([t], max_iter=50)

    def closure():
        opt.zero_grad()
        loss = nn.functional.binary_cross_entropy_with_logits(Z / t.exp(), Y)
        loss.backward()
        return loss

    opt.step(closure)
    return float(t.exp())
