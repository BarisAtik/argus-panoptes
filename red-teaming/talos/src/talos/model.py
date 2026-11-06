"""A small GPT-style transformer with an optional out-of-band role embedding."""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from .tok import EOS, PAD, VOCAB


class Block(nn.Module):
    def __init__(self, d: int, heads: int, dropout: float):
        super().__init__()
        self.n1, self.n2 = nn.LayerNorm(d), nn.LayerNorm(d)
        self.q, self.heads, self.drop = nn.Linear(d, 3 * d), heads, dropout
        self.out = nn.Linear(d, d)
        self.mlp = nn.Sequential(nn.Linear(d, 4 * d), nn.GELU(), nn.Linear(4 * d, d))

    def forward(self, x, mask):
        b, t, d = x.shape
        q, k, v = self.q(self.n1(x)).chunk(3, -1)
        split = lambda z: z.view(b, t, self.heads, d // self.heads).transpose(1, 2)
        a = F.scaled_dot_product_attention(split(q), split(k), split(v), attn_mask=mask,
                                           dropout_p=self.drop if self.training else 0.0)
        x = x + self.out(a.transpose(1, 2).reshape(b, t, d))
        return x + self.mlp(self.n2(x))


class Talos(nn.Module):
    def __init__(self, d=128, layers=4, heads=4, max_len=160, roles=False, dropout=0.0):
        super().__init__()
        self.tok, self.pos = nn.Embedding(VOCAB, d), nn.Embedding(max_len, d)
        self.role = nn.Embedding(3, d) if roles else None
        self.blocks = nn.ModuleList(Block(d, heads, dropout) for _ in range(layers))
        self.norm = nn.LayerNorm(d)
        self.head = nn.Linear(d, VOCAB, bias=False)
        self.head.weight = self.tok.weight
        self.max_len = max_len

    def forward(self, ids, roles=None):
        t = ids.shape[1]
        x = self.tok(ids) + self.pos(torch.arange(t, device=ids.device))
        if self.role is not None:
            x = x + self.role(roles)
        keep = torch.tril(torch.ones(t, t, dtype=torch.bool, device=ids.device))
        for b in self.blocks:  # prompts are right-padded, so the causal mask already hides padding
            x = b(x, keep)
        return self.head(self.norm(x))

    @torch.no_grad()
    def generate(self, ids, roles, lengths, max_new=8):
        """Greedy decoding. Prompts are right-padded; each row writes after its own prompt."""
        self.eval()
        n = ids.shape[0]
        room = lengths.max().item() + max_new
        grow = room - ids.shape[1]
        if grow > 0:
            ids = F.pad(ids, (0, grow), value=PAD)
            roles = F.pad(roles, (0, grow), value=0)
        pos = lengths.clone()
        done = torch.zeros(n, dtype=torch.bool)
        rows = torch.arange(n)
        for _ in range(max_new):
            logits = self(ids[:, : pos.max()], roles[:, : pos.max()])
            nxt = logits[rows, pos - 1].argmax(-1)
            nxt[done] = PAD
            ids[rows, pos] = nxt
            roles[rows, pos] = 2
            done |= nxt == EOS
            pos = (pos + (~done).long()).clamp(max=room - 1)
            if done.all():
                break
        return [ids[i, lengths[i]:].tolist() for i in range(n)]
