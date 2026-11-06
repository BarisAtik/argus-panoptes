"""Map spaCy's Dutch label set onto CoNLL-2002. Fixed before any score was seen.

The choice matters and is not neutral: GPE becomes LOC, so a country named as an actor counts as
LOC here, whatever the CoNLL annotators chose. MISC mapping is a best effort, which is why the
primary comparison leaves MISC out. Numeric and date labels have no CoNLL counterpart.
"""

from __future__ import annotations

SPACY_TO_CONLL = {
    "PERSON": "PER",
    "GPE": "LOC",
    "LOC": "LOC",
    "FAC": "LOC",
    "ORG": "ORG",
    "NORP": "MISC",
    "EVENT": "MISC",
    "PRODUCT": "MISC",
    "WORK_OF_ART": "MISC",
    "LANGUAGE": "MISC",
    "LAW": "MISC",
}
