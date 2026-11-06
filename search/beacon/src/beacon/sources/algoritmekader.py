"""The Algoritmekader: Dutch government guidance on algorithms and AI, as real test data.

Published by the Ministry of the Interior at github.com/MinBZK/Algoritmekader under EUPL-1.2.
It is useful for more than its text, because it comes with relevance labels nobody on this
project wrote:

* Audit task. The Auditdienst Rijk (ADR) and the Algemene Rekenkamer (ARK) each publish audit
  norms. The project behind the Algoritmekader mapped each norm to the measures (`maatregelen`)
  that cover it, in `relatie-ak-tot-toetsingskaders.csv`.
* Requirement task. Each measure lists the legal requirements (`vereisten`) it helps to meet.

So a query is a norm or a requirement, and the relevant documents are measures. The labels
are probably incomplete, because a mapping names the best fits and not every related page,
which lowers absolute scores. It should not favour one retrieval method by itself.

Metadata that encodes the answer is left out of the indexed text, and so are the sections
generated from it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
import subprocess
from pathlib import Path

import yaml

from ..models import Document, Section, write_jsonl

log = logging.getLogger(__name__)

REPOSITORY = "https://github.com/MinBZK/Algoritmekader"
# Pinned so that numbers can be reproduced. Pass --ref main for the latest text.
PINNED_COMMIT = "ade6b24e7f09d01a04dd84a76b953386b5137a49"
SITE = "https://minbzk.github.io/Algoritmekader"
CONTENT = "docs/voldoen-aan-wetten-en-regels"
NORMS_FILE = "script/maatregelen-adr-ark.csv"
RELATIONS_FILE = "relatie-ak-tot-toetsingskaders.csv"
KINDS = {"maatregelen": "maatregel", "vereisten": "vereiste", "hulpmiddelen": "hulpmiddel"}

# Sections generated from the labels, reference lists, author names and page boilerplate.
DROPPED_SECTIONS = re.compile(
    r"^(bijbehorende|hulpmiddelen|bronnen|maatregelen|vereisten|aanbevelingen|"
    r"mogelijke maatregelen|relevante|auteur|kan ik 100%)",
    re.IGNORECASE,
)
_URN = re.compile(r"urn:nl:ak:mtr:[a-z0-9-]+")
_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_ATTRIBUTES = re.compile(r"\s*\{[^{}\n]*\}\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_ADMONITION = re.compile(r'^\s*(!!!|\?\?\?\+?)\s+\w+(\s+"(.*)")?\s*$')
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_INVISIBLE = re.compile("[­​-‏⁠﻿]")


def clean_inline(text: str) -> str:
    text = _IMAGE.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _TAG.sub("", text)
    text = _INVISIBLE.sub("", text)
    text = re.sub(r"[*`]|^\s*[-+]\s+|^\s*\d+\.\s+|^\s*>\s?", "", text)
    return " ".join(text.split())


def split_front_matter(raw: str) -> tuple[dict, str]:
    match = _FRONT_MATTER.match(raw)
    if not match:
        return {}, raw
    loaded = yaml.safe_load(match.group(1))
    return (loaded if isinstance(loaded, dict) else {}), raw[match.end() :]


def body_sections(body: str) -> list[Section]:
    """Markdown body to sections, without comments, markup or label-derived sections."""
    sections: list[Section] = []
    title = "Inleiding"
    paragraphs: list[str] = []
    current: list[str] = []
    dropped = False

    def end_paragraph() -> None:
        nonlocal current
        text = clean_inline(" ".join(current))
        current = []
        if text and not dropped:
            paragraphs.append(text)

    def end_section() -> None:
        nonlocal paragraphs
        end_paragraph()
        if paragraphs:
            sections.append(Section(title, paragraphs))
        paragraphs = []

    for line in _COMMENT.sub("", body).splitlines():
        heading = _HEADING.match(line)
        if heading:
            end_section()
            title = clean_inline(_ATTRIBUTES.sub("", heading.group(2)))
            dropped = len(heading.group(1)) <= 2 and bool(DROPPED_SECTIONS.match(title))
            continue
        if _ADMONITION.match(line) or re.fullmatch(r"\s*\|?[\s:|-]*\|?\s*", line):
            end_paragraph()
            continue
        if re.match(r"\s*([-+*]|\d+\.)\s+", line):
            end_paragraph()
        current.append(line.strip())
    end_section()
    return sections


def page_id(meta: dict, kind: str, path: Path) -> str:
    return str(meta.get("id") or f"urn:beacon:ak:{kind}:{path.stem}")


def _text_list(value) -> list[str]:
    if value is None:
        return []
    return [str(v) for v in (value if isinstance(value, list) else [value])]


def parse_page(path: Path, folder: str) -> tuple[Document, dict]:
    meta, body = split_front_matter(path.read_text(encoding="utf-8"))
    kind = KINDS[folder]
    document = Document(
        id=page_id(meta, kind, path),
        title=str(meta.get("title") or path.stem),
        court="Algoritmekader",
        doc_type=kind,
        subjects=_text_list(meta.get("onderwerp")),
        summary=" ".join(str(meta.get("toelichting") or "").split()),
        url=f"{SITE}/voldoen-aan-wetten-en-regels/{folder}/{path.stem}/",
        sections=body_sections(body),
    )
    return document, meta


def load_pages(root: Path) -> list[tuple[Document, dict, str]]:
    pages = []
    for folder in KINDS:
        for path in sorted((root / CONTENT / folder).glob("*.md")):
            if path.stem == "index":
                continue
            document, meta = parse_page(path, folder)
            if document.sections:
                pages.append((document, meta, path.stem))
    return pages


def split_for(query_id: str) -> str:
    """Stable half split. It depends only on the id, so nobody can pick the easy queries."""
    return "test" if hashlib.sha256(query_id.encode()).digest()[0] % 2 else "dev"


def audit_queries(norms_csv: Path, relations_csv: Path) -> list[dict]:
    """Audit norms as queries. A measure is relevant when the ministry mapped the norm to it."""
    norms: dict[tuple[str, str], str] = {}
    with open(norms_csv, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            body = "ARK" if "Rekenkamer" in row["source"] else "ADR"
            norms[(body, row["nummer"].strip())] = " ".join(row["maatregel"].split())
    rows = []
    with open(relations_csv, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["bron"].strip(), row["nummer"].strip())
            documents = sorted(set(_URN.findall(row["maatregelen-ak"])))
            text = norms.get(key)
            if not text or not documents:
                continue
            query_id = f"audit-{key[0]}-{key[1]}"
            rows.append(
                {
                    "id": query_id,
                    "query": text,
                    "relevant": {doc: 1 for doc in documents},
                    "kind": f"audit-{key[0]}",
                    "split": split_for(query_id),
                }
            )
    return sorted(rows, key=lambda r: r["id"])


def requirement_queries(pages: list[tuple[Document, dict, str]]) -> list[dict]:
    """Requirement summaries as queries. A measure is relevant when it lists the requirement."""
    by_slug = {stem: document for document, _, stem in pages if document.doc_type == "vereiste"}
    relevant: dict[str, set[str]] = {}
    for document, meta, _ in pages:
        if document.doc_type != "maatregel":
            continue
        for slug in _text_list(meta.get("vereiste")):
            relevant.setdefault(slug.strip().removesuffix(".md"), set()).add(document.id)
    rows = []
    for slug, documents in sorted(relevant.items()):
        requirement = by_slug.get(slug)
        if requirement is None or not requirement.summary:
            continue
        query_id = f"req-{slug}"
        rows.append(
            {
                "id": query_id,
                "query": requirement.summary,
                "relevant": {doc: 1 for doc in sorted(documents)},
                "kind": "requirement",
                "split": split_for(query_id),
            }
        )
    return rows


def clone(destination: Path, ref: str = PINNED_COMMIT) -> str:
    """Shallow checkout of one ref. Images over 2 MB stay behind, and no repo code is run."""
    destination.mkdir(parents=True, exist_ok=True)

    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(destination), *args], check=True, capture_output=True, text=True
        )
        return done.stdout.strip()

    if not (destination / ".git").exists():
        git("init", "-q")
        git("remote", "add", "origin", REPOSITORY)
    git("fetch", "-q", "--depth", "1", "--filter=blob:limit=2m", "origin", ref)
    git("checkout", "-q", "FETCH_HEAD")
    return git("rev-parse", "HEAD")


def build(root: Path, output_dir: Path, commit: str = "") -> dict:
    """Write corpus.jsonl and the query sets. Returns counts."""
    pages = load_pages(root)
    documents = [document for document, _, _ in pages]
    ids = [document.id for document in documents]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate page ids")
    audit = audit_queries(root / NORMS_FILE, root / RELATIONS_FILE)
    requirements = requirement_queries(pages)
    known = {document.id for document in documents}
    for row in audit + requirements:
        row["relevant"] = {doc: g for doc, g in row["relevant"].items() if doc in known}
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "corpus.jsonl", (asdict_document(d) for d in documents))
    write_jsonl(output_dir / "queries-audit.jsonl", audit)
    write_jsonl(output_dir / "queries-requirements.jsonl", requirements)
    counts = {
        "commit": commit,
        "documents": len(documents),
        "by_type": {
            kind: sum(d.doc_type == kind for d in documents) for kind in KINDS.values()
        },
        "audit_queries": len(audit),
        "requirement_queries": len(requirements),
    }
    (output_dir / "manifest.json").write_text(json.dumps(counts, indent=2), encoding="utf-8")
    return counts


def asdict_document(document: Document) -> dict:
    from dataclasses import asdict

    return asdict(document)
