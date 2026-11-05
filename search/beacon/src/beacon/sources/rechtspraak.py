"""Fetch and parse Dutch court decisions from the Open Data service of rechtspraak.nl.

Written against "Technische documentatie Open Data van de Rechtspraak" v1.15.

Service rules kept here: at most 10 requests per second (the default is 2), no parallel
requests, and no bulk download of everything. Pick a date range or a legal area.

Privacy: decisions are pseudonymised by the courts, but names of judges, clerks and lawyers
can remain. So contributor metadata and the `uitspraak.info` header block are not parsed at
all, and nothing fetched here is committed: it lands under data/, which git ignores.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import quote

import httpx
from lxml import etree

from ..models import Document, Section, write_jsonl

log = logging.getLogger(__name__)

BASE_URL = "https://data.rechtspraak.nl"
DEEPLINK = "https://deeplink.rechtspraak.nl/uitspraak?id={ecli}"
PAGE_SIZE = 200
USER_AGENT = "beacon-search/0.1 (hobby research project)"

ATOM = "{http://www.w3.org/2005/Atom}"
DCTERMS = "{http://purl.org/dc/terms/}"
PSI = "{http://psi.rechtspraak.nl/}"
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"

_BLOCKS = {
    "para", "parablock", "paragroup", "orderedlist", "itemizedlist", "table", "informaltable",
}  # fmt: skip
_SKIPPED = {"uitspraak.info", "conclusie.info", "info"}
_NO_SUMMARY = {"", "-", "geen", "geen inhoudsindicatie", "geen inhoudsindicatie."}


class ParseError(ValueError):
    pass


def _parser() -> etree.XMLParser:
    # Remote XML is untrusted: no entity expansion, no DTD and no network access.
    return etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False
    )


def _local(element) -> str:
    return etree.QName(element).localname if isinstance(element.tag, str) else ""


def _text(element) -> str:
    return " ".join(" ".join(element.itertext()).split())


def _title_of(section) -> str:
    title = next((c for c in section if _local(c) == "title"), None)
    return _text(title) if title is not None else ""


def _block_text(block) -> str:
    if _local(block) != "paragroup":
        return _text(block)
    # A paragroup holds a number plus its paragraphs: <nr>4.1</nr><para>...</para>
    return " ".join(part for part in (_text(child) for child in block) if part)


def _sections(element, title: str) -> Iterator[Section]:
    paragraphs: list[str] = []
    for child in element:
        name = _local(child)
        if name in _SKIPPED or name in {"title", "nr", ""}:
            continue
        if name == "section":
            if paragraphs:
                yield Section(title, paragraphs)
                paragraphs = []
            heading = _title_of(child) or child.get("role", "") or title
            yield from _sections(child, heading)
        elif name in _BLOCKS:
            text = _block_text(child)
            if text:
                paragraphs.append(text)
        else:
            yield from _sections(child, title)
    if paragraphs:
        yield Section(title, paragraphs)


def _split(text: str | None) -> list[str]:
    return [part.strip() for part in (text or "").split(";") if part.strip()]


def parse_document(xml: bytes) -> Document:
    """Parse one `open-rechtspraak` document into a Document."""
    try:
        root = etree.fromstring(xml, _parser())
    except etree.XMLSyntaxError as error:
        raise ParseError(f"invalid XML: {error}") from error

    descriptions = list(root.iter(f"{RDF}Description"))
    if not descriptions:
        raise ParseError("no rdf:Description found")
    register = next((d for d in descriptions if d.get(f"{RDF}about") is None), descriptions[0])
    publication = next((d for d in descriptions if d.get(f"{RDF}about") is not None), None)

    ecli = (register.findtext(f"{DCTERMS}identifier") or "").strip()
    if not ecli.startswith("ECLI:"):
        raise ParseError(f"no ECLI in metadata, got {ecli!r}")

    summary_element = next((e for e in root.iter() if _local(e) == "inhoudsindicatie"), None)
    summary = _text(summary_element) if summary_element is not None else ""
    if summary.lower() in _NO_SUMMARY:
        summary = ""

    body = next((e for e in root if _local(e) in {"uitspraak", "conclusie"}), None)
    sections = list(_sections(body, "Uitspraak")) if body is not None else []
    if body is not None and not sections:
        fallback = _text(body)
        sections = [Section("Uitspraak", [fallback])] if fallback else []

    title = publication.findtext(f"{DCTERMS}title") if publication is not None else None
    case_numbers: list[str] = []
    for element in register.findall(f"{PSI}zaaknummer"):
        case_numbers.extend(p.strip() for p in (element.text or "").split(",") if p.strip())

    return Document(
        id=ecli,
        title=(title or ecli).strip(),
        court=(register.findtext(f"{DCTERMS}creator") or "").strip(),
        date=(register.findtext(f"{DCTERMS}date") or "").strip(),
        doc_type=(register.findtext(f"{DCTERMS}type") or "").strip(),
        subjects=[s for e in register.findall(f"{DCTERMS}subject") for s in _split(e.text)],
        case_numbers=case_numbers,
        procedure=[
            (e.text or "").strip()
            for e in register.findall(f"{PSI}procedure")
            if (e.text or "").strip()
        ],
        place=(register.findtext(f"{DCTERMS}spatial") or "").strip(),
        summary=summary,
        url=DEEPLINK.format(ecli=ecli),
        sections=sections,
    )


@dataclass
class FeedEntry:
    ecli: str
    updated: str
    summary: str
    deleted: str | None


def parse_feed(xml: bytes) -> list[FeedEntry]:
    try:
        root = etree.fromstring(xml, _parser())
    except etree.XMLSyntaxError as error:
        raise ParseError(f"invalid feed: {error}") from error
    return [
        FeedEntry(
            ecli=(entry.findtext(f"{ATOM}id") or "").strip(),
            updated=(entry.findtext(f"{ATOM}updated") or "").strip(),
            summary=(entry.findtext(f"{ATOM}summary") or "").strip(),
            deleted=entry.get("deleted"),
        )
        for entry in root.findall(f"{ATOM}entry")
    ]


class RechtspraakClient:
    def __init__(
        self,
        http: httpx.Client | None = None,
        requests_per_second: float = 2.0,
        cache_dir: str | Path | None = None,
        max_retries: int = 4,
        sleep=time.sleep,
    ):
        if not 0 < requests_per_second <= 10:
            raise ValueError("the service allows at most 10 requests per second")
        self.http = http or httpx.Client(
            base_url=BASE_URL,
            timeout=60,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        self.interval = 1.0 / requests_per_second
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.max_retries = max_retries
        self.sleep = sleep
        self._last = 0.0

    def _get(self, path: str, params: list[tuple[str, str]]) -> bytes:
        for attempt in range(self.max_retries + 1):
            wait = self.interval - (time.monotonic() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = time.monotonic()
            try:
                response = self.http.get(path, params=params)
            except httpx.TransportError:
                if attempt == self.max_retries:
                    raise
                self.sleep(2.0**attempt)
                continue
            if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                self.sleep(2.0**attempt)
                continue
            response.raise_for_status()
            return response.content
        raise RuntimeError("unreachable")

    def search(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        subject: str | None = None,
        creator: str | None = None,
        doc_type: str | None = "Uitspraak",
        limit: int | None = None,
    ) -> Iterator[FeedEntry]:
        """Yield live feed entries that have a document, paging until the feed runs out."""
        params: list[tuple[str, str]] = [("return", "DOC"), ("max", str(PAGE_SIZE))]
        if doc_type:
            params.append(("type", doc_type))
        if date_from:
            params.append(("date", date_from))
            params.append(("date", date_to or date_from))
        if subject:
            params.append(("subject", subject))
        if creator:
            params.append(("creator", creator))

        seen: set[str] = set()
        offset = 0
        while True:
            page = parse_feed(self._get("/uitspraken/zoeken", [*params, ("from", str(offset))]))
            if not page:
                return
            # The docs and third-party notes disagree on whether `from` starts at 0 or 1,
            # so deduplicate instead of trusting the page boundary.
            fresh = [entry for entry in page if entry.ecli not in seen]
            if not fresh:
                return
            for entry in fresh:
                seen.add(entry.ecli)
                if entry.deleted:
                    continue
                yield entry
                if limit is not None and len(seen) >= limit:
                    return
            offset += len(page)

    def content(self, ecli: str) -> bytes:
        cached = self._cache_path(ecli)
        if cached and cached.exists():
            return cached.read_bytes()
        xml = self._get("/uitspraken/content", [("id", ecli)])
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(xml)
        return xml

    def _cache_path(self, ecli: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / (re.sub(r"[^A-Za-z0-9.-]", "_", quote(ecli, safe="")) + ".xml")


def fetch_corpus(
    client: RechtspraakClient,
    output: str | Path,
    date_from: str,
    date_to: str | None = None,
    subject: str | None = None,
    max_docs: int = 500,
) -> dict:
    """Download decisions to JSONL. A document that fails to parse is counted, not fatal."""
    counts = {"written": 0, "parse_errors": 0, "empty": 0}

    def rows() -> Iterator[dict]:
        for entry in client.search(date_from, date_to, subject, limit=max_docs):
            try:
                document = parse_document(client.content(entry.ecli))
            except ParseError as error:
                log.warning("skipping %s: %s", entry.ecli, error)
                counts["parse_errors"] += 1
                continue
            if not document.text.strip():
                counts["empty"] += 1
                continue
            counts["written"] += 1
            yield _as_dict(document)

    write_jsonl(output, rows())
    return counts


def _as_dict(document: Document) -> dict:
    return asdict(document)
