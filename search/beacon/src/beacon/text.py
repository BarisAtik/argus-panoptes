"""Dutch text helpers used by the local backend and the extractive generator."""

from __future__ import annotations

import re
from functools import lru_cache

import snowballstemmer

STOPWORDS = frozenset(
    """aan al alles als altijd andere ben bij daar dan dat de der deze die dit doch doen door
    dus een eens en er ge geen geweest haar had heb hebben heeft hem het hier hij hoe hun iemand
    iets ik in is ja je kan kon kunnen maar me meer men met mij mijn moet na naar niet niets nog
    nu of om omdat onder ons ook op over reeds te tegen toch toen tot u uit uw van veel voor want
    waren was wat werd wezen wie wil worden wordt zal ze zelf zich zij zijn zo zonder zou""".split()
)

_STEMMER = snowballstemmer.stemmer("dutch")
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[(\"'])")


@lru_cache(maxsize=200_000)
def _stem(word: str) -> str:
    return _STEMMER.stemWord(word)


def tokens(text: str) -> list[str]:
    """Lowercase, drop stop words, stem. Close to Elasticsearch's `dutch` analyzer, not equal."""
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text) if s.strip()]
