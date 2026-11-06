"""Swap person names and see who a model stops noticing.

Lists hold common names, typed by hand from general knowledge of each naming tradition. They are
not sampled from a census, so treat a gap as a signal to investigate. Combinations are random and
refer to nobody in particular. The sets are labelled by naming tradition, not by the nationality
or background of any person.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from .data import Sentence
from .spans import bio_spans, spans_to_bio

NAMES: dict[str, dict[str, list[str]]] = {
    "dutch": {
        "first": "Jan Pieter Sanne Lotte Daan Emma Bram Anouk Thijs Femke Ruben Marieke Joost "
        "Ilse Wouter Esther Koen Saskia Sander Marloes".split(),
        "last": "Jansen Bakker Visser Smit Meijer Mulder Bos Vos Peters Hendriks Dekker Brouwer "
        "Dijkstra Kok Vermeulen Scholten Postma Hoekstra Kuipers Willems".split(),
    },
    "turkish": {
        "first": "Mehmet Ayse Mustafa Fatma Ahmet Emine Hasan Zeynep Huseyin Elif Ibrahim Hatice "
        "Yusuf Merve Murat Esra Emre Sevgi Kemal Derya".split(),
        "last": "Yilmaz Kaya Demir Celik Sahin Yildiz Ozturk Aydin Arslan Dogan Kilic Aslan "
        "Cetin Kara Koc Kurt Ozdemir Polat Erdem Gunes".split(),
    },
    "moroccan": {
        "first": "Mohamed Fatima Youssef Khadija Hamza Naima Rachid Samira Karim Malika Abdel "
        "Nadia Said Latifa Driss Soumaya Bilal Hanane Ayoub Ikram".split(),
        "last": "Bouzid Amrani Benali Ouali Aziz Haddouchi Bouazza Tahiri Achahbar Boukhari "
        "Elkaddouri Azzouzi Ziani Lamrabet Moussaoui Chakir Idrissi Bakkali Saidi Rahmouni".split(),
    },
    "polish": {
        "first": "Piotr Anna Krzysztof Maria Andrzej Katarzyna Tomasz Malgorzata Pawel Agnieszka "
        "Michal Barbara Marcin Joanna Grzegorz Ewa Jakub Magdalena Adam Monika".split(),
        "last": "Kowalski Nowak Wisniewski Wojcik Kowalczyk Kaminski Lewandowski Zielinski "
        "Szymanski Wozniak Dabrowski Kozlowski Jankowski Mazur Krawczyk Piotrowski Grabowski "
        "Pawlak Michalski Adamczyk".split(),
    },
    "hindustani": {
        "first": "Rajesh Sita Anand Shanti Ravi Radha Vikash Asha Dinesh Geeta Sunil Meena Ashok "
        "Rekha Krishna Usha Prem Lata Mahesh Kavita".split(),
        "last": "Ramdin Sardjoe Biharie Ramsoedh Jagroep Mahabier Bansie Ramlakhan Debipersad "
        "Kalpoe Soekhai Chotkan Baldew Ramcharan Gangadin Sewnarain Autar Ganga Rambaran "
        "Lachman".split(),
    },
}


@dataclass(frozen=True)
class Mention:
    sentence: int
    start: int
    end: int
    doc_id: str
    first_name: str | None
    last_name: str


def swap_names(
    sentences: Sequence[Sentence], group: str, seed: int = 0
) -> tuple[list[Sentence], list[Mention]]:
    """Replace every gold PER span by a name from `group`, keeping the rest of the sentence.

    A one-token mention gets a surname (newspapers mostly repeat surnames), a longer one gets
    first name + surname. Within an article one original name stays one new name, and because the
    random draw depends only on the seed and position, all groups see the same design.
    """
    pool = NAMES[group]
    rng = random.Random(seed)
    assigned: dict[tuple[str, str], tuple[str, str]] = {}
    out, mentions = [], []
    for index, s in enumerate(sentences):
        tokens, new_spans, cursor = [], [], 0
        located = []
        for start, end, label in bio_spans(s.tags):
            tokens.extend(s.tokens[cursor:start])
            cursor = end
            if label != "PER":
                new_spans.append((len(tokens), len(tokens) + end - start, label))
                tokens.extend(s.tokens[start:end])
                continue
            # The same draws happen for every group: same seed, same order, same list lengths.
            draw = (rng.randrange(len(pool["first"])), rng.randrange(len(pool["last"])))
            key = (s.doc_id, s.tokens[end - 1].lower())
            first_i, last_i = assigned.setdefault(key, draw)
            first, last = pool["first"][first_i], pool["last"][last_i]
            new = [first, last] if end - start > 1 else [last]
            at = len(tokens)
            new_spans.append((at, at + len(new), "PER"))
            located.append(
                Mention(index, at, at + len(new), s.doc_id, new[0] if len(new) > 1 else None, last)
            )
            tokens.extend(new)
        tokens.extend(s.tokens[cursor:])
        out.append(Sentence(tuple(tokens), tuple(spans_to_bio(new_spans, len(tokens))), s.doc_id))
        mentions.extend(located)
    return out, mentions
