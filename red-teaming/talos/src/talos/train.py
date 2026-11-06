"""Batches, training and evaluation for one model."""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import asdict, dataclass

import torch
import torch.nn.functional as F

from . import world as W
from .model import Talos
from .tok import EOS, PAD, SLOT0, Slots


@dataclass
class Config:
    regime: str = "delegate"
    prov: str = "plain"
    heldout: str | None = None
    seed: int = 0
    d: int = 96
    layers: int = 3
    heads: int = 4
    steps: int = 1800
    batch: int = 48
    lr: float = 2e-3
    max_len: int = 160


def encode(ex: W.Example, prov: str, rng: random.Random, train: bool) -> tuple[list[int], list[int], list[int], Slots]:
    slots = Slots(rng if train else random.Random(0))
    prompt = W.render(ex, prov, rng)
    ids = [slots.encode(w) for w, _ in prompt]
    roles = [r for _, r in prompt]
    target = [slots.encode(w) for w in ex.target.split()] + [EOS] if train else []
    return ids, roles, target, slots


def pad(rows: list[list[int]], value: int) -> torch.Tensor:
    n = max(map(len, rows))
    return torch.tensor([r + [value] * (n - len(r)) for r in rows])


def batch(rng: random.Random, c: Config) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    xs, rs, ys = [], [], []
    while len(xs) < c.batch:
        ex = W.train_example(rng, c.regime, c.heldout)
        ids, roles, target, _ = encode(ex, c.prov, rng, True)
        if len(ids) + len(target) > c.max_len:
            continue
        seq = ids + target
        xs.append(seq[:-1])
        rs.append((roles + [2] * len(target))[:-1])
        ys.append([PAD] * (len(ids) - 1) + target)  # loss only on the action
    return pad(xs, PAD), pad(rs, 0), pad(ys, PAD)


def make_model(c: Config) -> Talos:
    return Talos(c.d, c.layers, c.heads, c.max_len, roles=c.prov in ("segment", "signed"), n_roles=4 if c.prov == "signed" else 3)


def fit(c: Config, log=None) -> Talos:
    torch.manual_seed(c.seed)
    rng = random.Random(c.seed)
    m = make_model(c)
    opt = torch.optim.AdamW(m.parameters(), lr=c.lr, weight_decay=0.01)
    t0 = time.time()
    m.train()
    for step in range(c.steps):
        for g in opt.param_groups:
            warm = min(1.0, (step + 1) / 200)
            g["lr"] = c.lr * warm * 0.5 * (1 + math.cos(math.pi * step / c.steps))
        x, r, y = batch(rng, c)
        loss = F.cross_entropy(m(x, r).view(-1, m.head.out_features), y.view(-1), ignore_index=PAD)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0)
        opt.step()
        if log and (step % 500 == 0 or step == c.steps - 1):
            log(f"step {step} loss {loss.item():.4f} {time.time() - t0:.0f}s")
    return m


def predict(m: Talos, exs: list[W.Example], prov: str, seed: int = 0, bs: int = 256) -> list[str]:
    """Greedy actions, as text with real entity names restored."""
    rng = random.Random(seed)
    out: list[str] = []
    for i in range(0, len(exs), bs):
        enc = [encode(e, prov, rng, False) for e in exs[i: i + bs]]
        ids = pad([e[0] for e in enc], PAD)
        roles = pad([e[1] for e in enc], 0)
        lengths = torch.tensor([len(e[0]) for e in enc])
        for row, e in zip(m.generate(ids, roles, lengths, max_new=8), enc):
            words = []
            for t in row:
                if t in (EOS, PAD):
                    break
                words.append(e[3].decode(t))
            out.append(" ".join(words))
    return out


def outcome(ex: W.Example, text: str) -> dict:
    a = W.parse_action(text)
    return {"task": int(text == ex.target), "malformed": int(a is None),
            "attack": int(bool(a and ex.attack_dest and a["dest"] == ex.attack_dest))}


def save(m: Talos, c: Config, path: str) -> None:
    torch.save({"state": m.state_dict(), "config": asdict(c)}, path)


def load(path: str) -> tuple[Talos, Config]:
    blob = torch.load(path, weights_only=True)
    c = Config(**blob["config"])
    m = make_model(c)
    m.load_state_dict(blob["state"])
    return m.eval(), c


def n_params(m: Talos) -> int:
    return sum(p.numel() for p in m.parameters())


__all__ = ["Config", "fit", "predict", "outcome", "save", "load", "n_params", "json", "SLOT0"]
