"""Turn a folder of office files into a corpus, with access rules and an honest report.

    beacon ingest-dir ~/documents --acl acl.yaml --out data/files/corpus.jsonl

Supported: PDF (needs the `files` extra), DOCX, HTML, Markdown and plain text. Anything that cannot
be read is listed in the report instead of disappearing without a trace, because a search tool
that quietly skips scanned PDFs gives wrong answers with full confidence.

Access is deny by default. Every file needs a rule in the ACL file, or it gets the group `admin`.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import re
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml
from lxml import etree, html

from ..citations import extract_refs
from ..injection import scan
from ..models import Document, Section, write_jsonl

log = logging.getLogger(__name__)

SUFFIXES = {".pdf", ".docx", ".html", ".htm", ".md", ".markdown", ".txt"}
DENY_GROUP = "admin"
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_UNPACKED_BYTES = 200 * 1024 * 1024
MIN_WORDS_PER_PAGE = 20
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MD_HEADING = re.compile(r"^#{1,6}\s+(.*)$")


class Unreadable(Exception):
    """A file that cannot be turned into text. The message goes into the report."""


@dataclass
class Extracted:
    title: str
    sections: list[Section]
    pages: int = 0
    empty_pages: int = 0


@dataclass
class AclRules:
    """Ordered rules. The first pattern that matches a relative path decides."""

    rules: list[tuple[str, list[str]]] = field(default_factory=list)
    default: tuple[str, ...] = (DENY_GROUP,)

    @classmethod
    def load(cls, path: str | Path) -> AclRules:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        rules = []
        for rule in data.get("rules", []):
            groups = [str(g) for g in rule["groups"]]
            if not groups:
                raise ValueError(f"rule {rule['path']!r} has no groups")
            rules.append((str(rule["path"]), groups))
        return cls(rules, tuple(str(g) for g in data.get("default", [DENY_GROUP])))

    def groups_for(self, relative: str) -> list[str]:
        for pattern, groups in self.rules:
            if fnmatch.fnmatchcase(relative, pattern):
                return groups
        return list(self.default)


@dataclass
class Report:
    files_seen: int = 0
    documents: int = 0
    words: int = 0
    skipped_type: int = 0
    failed: dict[str, str] = field(default_factory=dict)
    likely_scanned: list[str] = field(default_factory=list)
    partly_scanned: list[str] = field(default_factory=list)
    duplicates: dict[str, str] = field(default_factory=dict)
    default_acl: list[str] = field(default_factory=list)
    injection_suspected: list[str] = field(default_factory=list)


def _paragraphs(text: str) -> list[str]:
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()]


def read_pdf(path: Path) -> Extracted:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError
    except ImportError as error:
        raise Unreadable('PDF needs the extra: pip install -e ".[files]"') from error
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise Unreadable("encrypted PDF")
        sections, empty = [], 0
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if len(text.split()) < MIN_WORDS_PER_PAGE:
                empty += 1
            paragraphs = _paragraphs(text)
            if paragraphs:
                sections.append(Section(f"Pagina {number}", paragraphs))
        meta_title = (reader.metadata.title if reader.metadata else "") or ""
    except PyPdfError as error:
        raise Unreadable(f"broken PDF: {error}") from error
    return Extracted(meta_title.strip(), sections, len(reader.pages), empty)


def read_docx(path: Path) -> Extracted:
    """Only document.xml is read: no macros, no linked content, and entities are refused."""
    try:
        with zipfile.ZipFile(path) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_UNPACKED_BYTES:
                raise Unreadable("unpacks to more than the size limit")
            raw = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as error:
        raise Unreadable(f"broken DOCX: {error}") from error
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    try:
        root = etree.fromstring(raw, parser)
    except etree.XMLSyntaxError as error:
        raise Unreadable(f"broken DOCX: {error}") from error
    title = ""
    sections = [Section("", [])]
    for paragraph in root.iter(f"{_W}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{_W}t")).strip()
        if not text:
            continue
        style = paragraph.find(f"{_W}pPr/{_W}pStyle")
        name = (style.get(f"{_W}val") or "").lower() if style is not None else ""
        if name.startswith("title") and not title:
            title = text
        elif name.startswith(("heading", "kop")):
            title = title or text
            sections.append(Section(text, []))
        else:
            sections[-1].paragraphs.append(" ".join(text.split()))
    return Extracted(title, [s for s in sections if s.paragraphs])


def read_html(path: Path) -> Extracted:
    parser = html.HTMLParser(no_network=True, encoding="utf-8")
    try:
        root = html.parse(str(path), parser).getroot()
    except (etree.LxmlError, OSError) as error:
        raise Unreadable(f"broken HTML: {error}") from error
    if root is None:
        return Extracted("", [])
    unwanted = ("script", "style", "noscript", "template", etree.Comment)
    etree.strip_elements(root, *unwanted, with_tail=False)
    title = (root.findtext(".//title") or "").strip()
    sections = [Section("", [])]
    for element in root.iter("h1", "h2", "h3", "p", "li", "td", "pre", "blockquote"):
        text = " ".join(element.text_content().split())
        if not text:
            continue
        if element.tag in ("h1", "h2", "h3"):
            title = title or text
            sections.append(Section(text, []))
        else:
            sections[-1].paragraphs.append(text)
    return Extracted(title, [s for s in sections if s.paragraphs])


def read_text(path: Path) -> Extracted:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    title = ""
    sections = [Section("", [])]
    buffer: list[str] = []

    def flush() -> None:
        sections[-1].paragraphs.extend(_paragraphs("\n".join(buffer)))
        buffer.clear()

    for line in text.splitlines():
        heading = _MD_HEADING.match(line) if path.suffix != ".txt" else None
        if heading:
            flush()
            title = title or heading[1].strip()
            sections.append(Section(heading[1].strip(), []))
        else:
            buffer.append(line)
    flush()
    return Extracted(title, [s for s in sections if s.paragraphs])


READERS = {
    ".pdf": read_pdf, ".docx": read_docx, ".html": read_html, ".htm": read_html,
    ".md": read_text, ".markdown": read_text, ".txt": read_text,
}  # fmt: skip


def read_file(path: Path) -> Extracted:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise Unreadable("larger than the size limit")
    return READERS[path.suffix.lower()](path)


def walk(root: Path) -> list[Path]:
    """Regular files under root, without hidden ones. Symlinks stay out, so nothing escapes root."""
    found = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink() or not path.is_file():
            continue
        if any(part.startswith((".", "~$")) for part in relative.parts):
            continue
        found.append(path)
    return found


def fingerprint(document: Document) -> str:
    """Changes with the text and with the access rules, so that a changed ACL gets re-indexed."""
    payload = json.dumps([document.title, document.text, sorted(document.acl)], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def load_directory(root: str | Path, acl: AclRules) -> tuple[list[Document], Report]:
    root = Path(root).resolve()
    report = Report()
    documents: list[Document] = []
    seen: dict[str, str] = {}
    for path in walk(root):
        relative = path.relative_to(root).as_posix()
        report.files_seen += 1
        if path.suffix.lower() not in SUFFIXES:
            report.skipped_type += 1
            continue
        try:
            extracted = read_file(path)
        except Unreadable as error:
            report.failed[relative] = str(error)
            continue
        except Exception as error:  # a hostile file must not stop the run
            log.warning("cannot read %s: %s", relative, type(error).__name__)
            report.failed[relative] = f"unexpected {type(error).__name__}"
            continue
        if extracted.pages and extracted.empty_pages == extracted.pages:
            report.likely_scanned.append(relative)
        elif extracted.empty_pages:
            report.partly_scanned.append(relative)
        if not extracted.sections:
            report.failed.setdefault(relative, "no text found")
            continue
        text = "\n".join(p for s in extracted.sections for p in s.paragraphs)
        digest = hashlib.sha256(text.encode()).hexdigest()
        groups = acl.groups_for(relative)
        # Two copies under different rules must both stay: dropping one could change who sees it.
        key = f"{digest}:{sorted(groups)}"
        if key in seen:
            report.duplicates[relative] = seen[key]
            continue
        seen[key] = relative
        if not any(fnmatch.fnmatchcase(relative, pattern) for pattern, _ in acl.rules):
            report.default_acl.append(relative)
        if scan(text):
            report.injection_suspected.append(relative)
        modified = datetime.fromtimestamp(path.stat().st_mtime, UTC).date().isoformat()
        document = Document(
            id=f"file:{relative}",
            title=extracted.title or path.stem,
            court=relative.split("/")[0] if "/" in relative else "",
            date=modified,
            doc_type=path.suffix.lower().lstrip("."),
            sections=extracted.sections,
            acl=groups,
            refs=extract_refs(text[:200_000]),
        )
        documents.append(document)
        report.documents += 1
        report.words += len(text.split())
    return documents, report


def plan_sync(
    documents: list[Document], state: dict[str, str]
) -> tuple[list[Document], list[str], dict[str, str]]:
    """Compare with the last run: documents to (re)index, ids to delete, and the new state."""
    current = {document.id: fingerprint(document) for document in documents}
    changed = [d for d in documents if state.get(d.id) != current[d.id]]
    removed = sorted(set(state) - set(current))
    return changed, removed, current


def report_markdown(report: Report) -> str:
    """Counts and file names. File names can be sensitive, so this stays next to the data."""
    lines = [
        "# Ingest report",
        "",
        f"- Files seen: {report.files_seen}",
        f"- Documents indexed: {report.documents} ({report.words} words)",
        f"- Skipped, unsupported type: {report.skipped_type}",
        f"- Failed: {len(report.failed)}",
        f"- Likely scanned, no text layer: {len(report.likely_scanned)}",
        f"- Partly scanned: {len(report.partly_scanned)}",
        f"- Duplicates left out: {len(report.duplicates)}",
        f"- No ACL rule, restricted to `{DENY_GROUP}`: {len(report.default_acl)}",
        f"- Planted instructions suspected: {len(report.injection_suspected)}",
    ]
    for title, values in (
        ("Failed", [f"{k}: {v}" for k, v in report.failed.items()]),
        ("Likely scanned (needs OCR, not searchable now)", report.likely_scanned),
        ("Partly scanned", report.partly_scanned),
        ("No ACL rule", report.default_acl),
        ("Planted instructions suspected", report.injection_suspected),
    ):
        if values:
            lines += ["", f"## {title}", "", *(f"- {value}" for value in values)]
    return "\n".join(lines) + "\n"


def write_corpus(documents: list[Document], report: Report, out: str | Path) -> None:
    out = Path(out)
    write_jsonl(out, (asdict(document) for document in documents))
    out.with_name("ingest-report.md").write_text(report_markdown(report), encoding="utf-8")
