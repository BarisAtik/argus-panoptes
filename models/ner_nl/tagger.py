"""A compact BiLSTM-CRF in plain PyTorch, sized to train on a laptop CPU.

Word vectors stay frozen, characters and word shape go through small learned layers, and a
linear-chain CRF enforces valid BIO sequences. The CRF also gives token marginals, which is where
the entity confidence for the calibration study comes from.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import asdict, dataclass

import numpy as np
import torch
from torch import nn

from .data import Sentence
from .spans import bio_spans

TAGS = ("O", "B-PER", "I-PER", "B-LOC", "I-LOC", "B-ORG", "I-ORG", "B-MISC", "I-MISC")
TAG_INDEX = {t: i for i, t in enumerate(TAGS)}
NO_PATH = -1e4


def word_shape(token: str) -> int:
    if any(c.isdigit() for c in token):
        return 1
    if token.isupper() and len(token) > 1:
        return 2
    if token[:1].isupper():
        return 3
    if token.islower():
        return 4
    return 0


def allowed_transitions() -> torch.Tensor:
    """1 where tag j may follow tag i. I-X only after B-X or I-X."""
    n = len(TAGS)
    mask = torch.ones(n, n)
    for j, tag in enumerate(TAGS):
        if tag.startswith("I-"):
            kind = tag[2:]
            for i, prev in enumerate(TAGS):
                mask[i, j] = float(prev in (f"B-{kind}", f"I-{kind}"))
    return mask


@dataclass
class Config:
    char_dim: int = 30
    char_filters: int = 50
    shape_dim: int = 8
    hidden: int = 200
    dropout: float = 0.5


class BiLSTMCRF(nn.Module):
    def __init__(self, vectors: torch.Tensor, n_chars: int, config: Config):
        super().__init__()
        self.config = config
        self.words = nn.Embedding.from_pretrained(vectors, freeze=True, padding_idx=0)
        self.chars = nn.Embedding(n_chars, config.char_dim, padding_idx=0)
        self.char_cnn = nn.Conv1d(config.char_dim, config.char_filters, 3, padding=1)
        self.shapes = nn.Embedding(5, config.shape_dim)
        size = vectors.shape[1] + config.char_filters + config.shape_dim
        self.drop = nn.Dropout(config.dropout)
        self.lstm = nn.LSTM(size, config.hidden, batch_first=True, bidirectional=True)
        self.emit = nn.Linear(2 * config.hidden, len(TAGS))
        n = len(TAGS)
        self.trans = nn.Parameter(torch.zeros(n, n))
        self.start = nn.Parameter(torch.zeros(n))
        self.end = nn.Parameter(torch.zeros(n))
        self.register_buffer("allowed", allowed_transitions())
        start_ok = torch.tensor([0.0 if t.startswith("I-") else 1.0 for t in TAGS])
        self.register_buffer("start_ok", start_ok)

    def _trans(self) -> torch.Tensor:
        return self.trans.masked_fill(self.allowed == 0, NO_PATH)

    def _start(self) -> torch.Tensor:
        return self.start.masked_fill(self.start_ok == 0, NO_PATH)

    def emissions(self, batch: dict) -> torch.Tensor:
        b, t, c = batch["chars"].shape
        chars = self.chars(batch["chars"].view(b * t, c)).transpose(1, 2)
        pooled = torch.relu(self.char_cnn(self.drop(chars))).max(dim=2).values.view(b, t, -1)
        x = torch.cat([self.words(batch["words"]), pooled, self.shapes(batch["shapes"])], dim=2)
        lengths = batch["mask"].sum(1).cpu()
        packed = nn.utils.rnn.pack_padded_sequence(
            self.drop(x), lengths, batch_first=True, enforce_sorted=False
        )
        out, _ = self.lstm(packed)
        out, _ = nn.utils.rnn.pad_packed_sequence(out, batch_first=True, total_length=t)
        return self.emit(self.drop(out))

    def _forward_scores(self, emissions, mask) -> torch.Tensor:
        """alpha[b, t, j]: log sum over all paths ending in j at step t."""
        trans = self._trans()
        alpha = [self._start() + emissions[:, 0]]
        for t in range(1, emissions.shape[1]):
            step = torch.logsumexp(alpha[-1].unsqueeze(2) + trans, dim=1) + emissions[:, t]
            alpha.append(torch.where(mask[:, t, None], step, alpha[-1]))
        return torch.stack(alpha, dim=1)

    def loss(self, batch: dict) -> torch.Tensor:
        emissions, mask, tags = self.emissions(batch), batch["mask"], batch["tags"]
        log_z = torch.logsumexp(self._forward_scores(emissions, mask)[:, -1] + self.end, dim=1)
        rows = torch.arange(len(tags))
        trans = self._trans()
        score = self._start()[tags[:, 0]] + emissions[rows, 0, tags[:, 0]]
        for t in range(1, tags.shape[1]):
            gain = trans[tags[:, t - 1], tags[:, t]] + emissions[rows, t, tags[:, t]]
            score = score + gain * mask[:, t]
        last = mask.sum(1) - 1
        score = score + self.end[tags[rows, last]]
        return (log_z - score).mean()

    @torch.no_grad()
    def decode(self, emissions, mask) -> list[list[int]]:
        trans = self._trans()
        score = self._start() + emissions[:, 0]
        pointers = []
        for t in range(1, emissions.shape[1]):
            best, back = (score.unsqueeze(2) + trans).max(dim=1)
            step = best + emissions[:, t]
            on = mask[:, t, None]
            score = torch.where(on, step, score)
            pointers.append(back)
        paths = []
        for b in range(len(emissions)):
            n = int(mask[b].sum())
            tag = int((score[b] + self.end).argmax())
            path = [tag]
            for t in range(n - 2, -1, -1):
                tag = int(pointers[t][b, tag])
                path.append(tag)
            paths.append(path[::-1])
        return paths

    @torch.no_grad()
    def marginals(self, emissions, mask, temperature: float = 1.0) -> torch.Tensor:
        """p(tag at t | sentence), with potentials divided by a fitted temperature."""
        trans = self._trans() / temperature
        em = emissions / temperature
        start, end = self._start() / temperature, self.end / temperature
        steps = em.shape[1]
        alpha = [start + em[:, 0]]
        for t in range(1, steps):
            step = torch.logsumexp(alpha[-1].unsqueeze(2) + trans, dim=1) + em[:, t]
            alpha.append(torch.where(mask[:, t, None], step, alpha[-1]))
        last = mask.sum(1) - 1
        beta = [torch.zeros_like(em[:, 0]) for _ in range(steps)]
        ends = last == steps - 1
        beta[-1] = torch.where(ends[:, None], end.expand_as(em[:, 0]), beta[-1])
        for t in range(steps - 2, -1, -1):
            step = torch.logsumexp(trans + em[:, t + 1].unsqueeze(1) + beta[t + 1].unsqueeze(1), 2)
            value = torch.where(mask[:, t + 1, None], step, torch.zeros_like(step))
            beta[t] = torch.where((last == t)[:, None], end.expand_as(value), value)
        log_p = torch.stack(alpha, 1) + torch.stack(beta, 1)
        return torch.softmax(log_p, dim=2)


class Encoder:
    """Text to tensors. Vocabulary comes from the vector table, not from the training labels."""

    def __init__(self, word_index: dict[str, int], chars: dict[str, int]):
        self.word_index, self.chars = word_index, chars

    @classmethod
    def build(cls, sentences: Sequence[Sentence], word_index: dict[str, int]) -> Encoder:
        chars = sorted({c for s in sentences for t in s.tokens for c in t})
        return cls(word_index, {c: i + 2 for i, c in enumerate(chars)})

    def batch(self, sentences: Sequence[Sentence], device="cpu") -> dict:
        b = len(sentences)
        t = max(max(len(s.tokens) for s in sentences), 1)
        c = max((len(tok) for s in sentences for tok in s.tokens), default=1)
        c = max(min(c, 24), 3)
        words = torch.zeros(b, t, dtype=torch.long)
        shapes = torch.zeros(b, t, dtype=torch.long)
        tags = torch.zeros(b, t, dtype=torch.long)
        mask = torch.zeros(b, t, dtype=torch.bool)
        chars = torch.zeros(b, t, c, dtype=torch.long)
        mask[:, 0] = True  # empty sentences keep one pad step so that decoding stays simple
        for i, s in enumerate(sentences):
            for j, tok in enumerate(s.tokens):
                words[i, j] = self.word_index.get(tok, self.word_index.get(tok.lower(), 0))
                shapes[i, j] = word_shape(tok)
                mask[i, j] = True
                tags[i, j] = TAG_INDEX[s.tags[j]]
                for k, ch in enumerate(tok[:c]):
                    chars[i, j, k] = self.chars.get(ch, 1)
        batch = {"words": words, "shapes": shapes, "chars": chars, "tags": tags, "mask": mask}
        return {k: v.to(device) for k, v in batch.items()}


def predict(
    model: BiLSTMCRF, encoder: Encoder, sentences: Sequence[Sentence], batch_size: int = 128
) -> list[list[str]]:
    return predict_with_confidence(model, encoder, sentences, batch_size, want_conf=False)[0]


def predict_with_confidence(
    model: BiLSTMCRF,
    encoder: Encoder,
    sentences: Sequence[Sentence],
    batch_size: int = 128,
    temperature: float = 1.0,
    want_conf: bool = True,
):
    """Viterbi tags, plus per sentence the (start, end, label, confidence) of each predicted span.

    Span confidence is the lowest marginal of its tags, a cheap stand-in for the span's true
    posterior.
    """
    model.eval()
    order = sorted(range(len(sentences)), key=lambda i: len(sentences[i].tokens))
    tags: list = [None] * len(sentences)
    confidence: list = [[] for _ in sentences]
    with torch.no_grad():
        for at in range(0, len(order), batch_size):
            ids = order[at : at + batch_size]
            batch = encoder.batch([sentences[i] for i in ids])
            emissions = model.emissions(batch)
            paths = model.decode(emissions, batch["mask"])
            margins = model.marginals(emissions, batch["mask"], temperature) if want_conf else None
            for row, (i, path) in enumerate(zip(ids, paths)):
                n = len(sentences[i].tokens)
                named = [TAGS[p] for p in path[:n]]
                tags[i] = named
                if want_conf:
                    for start, end, label in bio_spans(named):
                        low = min(float(margins[row, k, path[k]]) for k in range(start, end))
                        confidence[i].append((start, end, label, low))
    return tags, confidence


def token_nll(
    model: BiLSTMCRF,
    encoder: Encoder,
    sentences: Sequence[Sentence],
    temperature: float,
    batch_size: int = 128,
) -> float:
    """Mean negative log marginal of the gold tag. Used to fit temperature on dev data."""
    model.eval()
    total, count = 0.0, 0
    order = sorted(range(len(sentences)), key=lambda i: len(sentences[i].tokens))
    with torch.no_grad():
        for at in range(0, len(order), batch_size):
            batch = encoder.batch([sentences[i] for i in order[at : at + batch_size]])
            margins = model.marginals(model.emissions(batch), batch["mask"], temperature)
            gold = margins.gather(2, batch["tags"].unsqueeze(2)).squeeze(2)
            picked = gold[batch["mask"]].clamp_min(1e-12)
            total += float(-picked.log().sum())
            count += int(batch["mask"].sum())
    return total / count


def lowercase_some(sentences: Sequence[Sentence], share: float, rng: random.Random):
    """Training augmentation: a random share of sentences loses case and punctuation."""
    from .perturb import transcript_style

    return [
        transcript_style([s])[0] if rng.random() < share else s
        for s in sentences
    ]


def train(
    train_set: Sequence[Sentence],
    dev_set: Sequence[Sentence],
    vectors: np.ndarray,
    word_index: dict[str, int],
    seed: int = 0,
    epochs: int = 30,
    patience: int = 6,
    batch_size: int = 32,
    lr: float = 1e-3,
    augment: float = 0.0,
    config: Config | None = None,
    log=print,
) -> tuple[BiLSTMCRF, Encoder, dict]:
    """Train with early stopping on dev F1, entity level, all four labels."""
    from .spans import count_by_doc, prf

    random.seed(seed)
    torch.manual_seed(seed)
    rng = random.Random(seed)
    encoder = Encoder.build(train_set, word_index)
    model = BiLSTMCRF(
        torch.tensor(vectors, dtype=torch.float32), len(encoder.chars) + 2, config or Config()
    )
    learnable = [p for p in model.parameters() if p.requires_grad]
    optimiser = torch.optim.Adam(learnable, lr=lr)
    best, best_state, bad, history = -1.0, None, 0, []
    usable = [s for s in train_set if s.tokens]
    for epoch in range(epochs):
        model.train()
        data = lowercase_some(usable, augment, rng) if augment else list(usable)
        data = [s for s in data if s.tokens]
        rng.shuffle(data)
        chunks = [
            sorted(data[i : i + batch_size * 50], key=lambda s: len(s.tokens))
            for i in range(0, len(data), batch_size * 50)
        ]
        batches = [c[i : i + batch_size] for c in chunks for i in range(0, len(c), batch_size)]
        rng.shuffle(batches)
        running = 0.0
        for chunk in batches:
            optimiser.zero_grad()
            loss = model.loss(encoder.batch(chunk))
            loss.backward()
            nn.utils.clip_grad_norm_(learnable, 5.0)
            optimiser.step()
            running += float(loss)
        rows, _ = count_by_doc(dev_set, predict(model, encoder, dev_set))
        f1 = prf(rows)["f1"]
        history.append({"epoch": epoch, "loss": running / len(batches), "dev_f1": f1})
        log(f"seed {seed} epoch {epoch} loss {running / len(batches):.3f} dev F1 {f1:.4f}")
        if f1 > best:
            best, bad = f1, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    model.load_state_dict(best_state)
    return model, encoder, {"history": history, "best_dev_f1": best, "config": asdict(model.config)}
