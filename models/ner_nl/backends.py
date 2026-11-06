"""Predictors: anything that turns sentences into BIO tags. Pretokenised, so scores line up."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence

from .data import Sentence
from .label_map import SPACY_TO_CONLL
from .spans import bio_spans, spans_to_bio


class Gazetteer:
    """Baseline: longest match against entity strings seen in training, majority label.

    Case sensitive, because this is how a lookup list usually works in practice.
    """

    def __init__(self, train: Sequence[Sentence]):
        counts: dict[tuple[str, ...], Counter] = defaultdict(Counter)
        for s in train:
            for start, end, label in bio_spans(s.tags):
                counts[s.tokens[start:end]][label] += 1
        self.table = {k: c.most_common(1)[0][0] for k, c in counts.items()}
        self.longest = max((len(k) for k in self.table), default=0)

    def __call__(self, sentences: Sequence[Sentence]) -> list[list[str]]:
        return [self._tag(s.tokens) for s in sentences]

    def _tag(self, tokens: tuple[str, ...]) -> list[str]:
        spans, i = [], 0
        while i < len(tokens):
            for size in range(min(self.longest, len(tokens) - i), 0, -1):
                label = self.table.get(tokens[i : i + size])
                if label:
                    spans.append((i, i + size, label))
                    i += size
                    break
            else:
                i += 1
        return spans_to_bio(spans, len(tokens))


class SpacyNER:
    """A spaCy pipeline over given tokens, with labels mapped to CoNLL-2002."""

    def __init__(self, name: str, nlp=None):
        import spacy

        self.name = name
        self.nlp = nlp or spacy.load(name)
        keep = {"ner", "tok2vec"} if self._ner_needs_tok2vec() else {"ner"}
        self.disable = [p for p in self.nlp.pipe_names if p not in keep]

    def _ner_needs_tok2vec(self) -> bool:
        # The Dutch pipelines carry their own tok2vec inside `ner`; a listener would need the
        # shared one. Keep it if the config says so.
        config = self.nlp.get_pipe_config("ner") if "ner" in self.nlp.pipe_names else {}
        return "Listener" in str(config.get("model", {}).get("tok2vec", {}).get("@architectures"))

    def __call__(self, sentences: Sequence[Sentence]) -> list[list[str]]:
        from spacy.tokens import Doc

        docs = [Doc(self.nlp.vocab, words=list(s.tokens) or [""]) for s in sentences]
        out = []
        for s, doc in zip(sentences, self.nlp.pipe(docs, disable=self.disable, batch_size=256)):
            if not s.tokens:
                out.append([])
                continue
            spans = [
                (e.start, e.end, SPACY_TO_CONLL[e.label_])
                for e in doc.ents
                if e.label_ in SPACY_TO_CONLL
            ]
            out.append(spans_to_bio(spans, len(s.tokens)))
        return out
