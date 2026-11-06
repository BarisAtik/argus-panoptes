"""Command line interface. Run `beacon --help`."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from importlib.resources import files
from pathlib import Path

from . import evaluate as ev
from . import quality
from .backends import Backend, get_backend
from .chunking import DEFAULT_MAX_WORDS, DEFAULT_OVERLAP_WORDS, chunk_document
from .compounds import Decompounder, compound_vocabulary
from .config import Settings, load_dotenv
from .embeddings import Embedder, get_embedder
from .models import Chunk, Document, Filters, read_corpus, read_jsonl
from .rag import answer, get_generator
from .retrieval import MODES, Retriever

BATCH = 64
DEMO_WARNING = (
    "SYNTHETIC demo corpus, written by the author of the queries. These numbers test the "
    "pipeline. They do not estimate performance on real documents."
)


def demo_path(name: str) -> Path:
    return Path(str(files("beacon.demo").joinpath(name)))


def embed_and_add(backend: Backend, embedder: Embedder, chunks: list[Chunk]) -> None:
    for start in range(0, len(chunks), BATCH):
        batch = chunks[start : start + BATCH]
        backend.add(batch, embedder.embed_passages([c.text for c in batch]))


def index_documents(
    backend: Backend,
    embedder: Embedder,
    documents: list[Document],
    recreate: bool = False,
    include_summary: bool = True,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
    title_prefix: bool = False,
) -> int:
    backend.create(embedder.dims, recreate=recreate)
    chunks = [
        chunk
        for document in documents
        for chunk in chunk_document(
            document,
            max_words=max_words,
            overlap_words=overlap_words,
            include_summary=include_summary,
            title_prefix=title_prefix,
        )
    ]
    embed_and_add(backend, embedder, chunks)
    return len(chunks)


def add_stack_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--backend", choices=["elastic", "local"], help="default: BEACON_BACKEND")
    parser.add_argument("--embedder", help="st:<model>, onnx:<dir>, spacy:<model> or hash[:dims]")
    parser.add_argument("--embedding-cache", help="directory that keeps passage vectors on disk")
    parser.add_argument("--corpus", help="JSONL corpus; the local backend loads it at start")
    parser.add_argument("--demo", action="store_true", help="use the synthetic demo corpus")
    parser.add_argument("--title-prefix", action="store_true", help="repeat titles in chunks")


def build_stack(args, include_summary: bool = True) -> tuple[Retriever, list[Document]]:
    settings = Settings.from_env()
    backend_name = "local" if args.demo else (args.backend or settings.backend)
    embedder = get_embedder(args.embedder or settings.embedder, args.embedding_cache)
    backend = get_backend(backend_name, settings)
    corpus = demo_path("corpus.jsonl") if args.demo else args.corpus
    documents = read_corpus(corpus) if corpus else []
    if backend_name == "local":
        if not documents:
            sys.exit("the local backend needs --corpus or --demo")
        if getattr(args, "compounds", False):
            backend.decompounder = Decompounder(compound_vocabulary(d.text for d in documents))
        index_documents(
            backend, embedder, documents, include_summary=include_summary,
            title_prefix=getattr(args, "title_prefix", False),
        )  # fmt: skip
    retriever = Retriever(
        backend, embedder, rrf_k=settings.rrf_k, groups=groups_from(args, settings),
        routing=settings.routing, synonyms=True, refs=True,
    )  # fmt: skip
    return retriever, documents


def groups_from(args, settings: Settings) -> frozenset[str] | None:
    """Access groups of the caller, set by whoever starts the process, never by the agent."""
    value = getattr(args, "groups", None)
    if value is None:
        value = settings.groups
    if value is None:
        return None
    return frozenset(g.strip() for g in value.split(",") if g.strip())


def add_filter_arguments(parser: argparse.ArgumentParser) -> None:
    for name in ("court", "subject", "doc-type", "date-from", "date-to"):
        parser.add_argument(f"--{name}")


def filters_from(args) -> Filters | None:
    filters = Filters(args.court, args.subject, args.doc_type, args.date_from, args.date_to)
    return None if filters == Filters() else filters


def cmd_fetch_ak(args) -> None:
    from .sources import algoritmekader as ak

    checkout = Path(args.checkout)
    commit = ak.clone(checkout, args.ref or ak.PINNED_COMMIT)
    print(json.dumps(ak.build(checkout, Path(args.output), commit), indent=2))


def cmd_fetch_model(args) -> None:
    from .model_fetch import fetch

    print(f"model ready in {fetch(args.directory)}")


def cmd_fetch(args) -> None:
    from .sources.rechtspraak import RechtspraakClient, fetch_corpus

    client = RechtspraakClient(requests_per_second=args.rate, cache_dir=args.cache)
    counts = fetch_corpus(
        client, args.output, args.date_from, args.date_to, args.subject, args.max_docs
    )
    print(json.dumps(counts))


def cmd_ingest(args) -> None:
    settings = Settings.from_env()
    if (args.backend or settings.backend) == "local":
        sys.exit("the local backend is in memory; it loads --corpus on each command")
    embedder = get_embedder(args.embedder or settings.embedder, args.embedding_cache)
    backend = get_backend(args.backend or settings.backend, settings)
    documents = read_corpus(args.corpus)
    if args.compounds:
        vocabulary = compound_vocabulary(d.text for d in documents)
        backend.compound_words = sorted(vocabulary, key=lambda w: -vocabulary[w])[:30_000]
    count = index_documents(
        backend, embedder, documents, args.recreate, include_summary=not args.no_summaries,
        title_prefix=args.title_prefix,
    )  # fmt: skip
    print(f"indexed {count} chunks from {len(documents)} documents with {embedder.name}")
    print(json.dumps(backend.stats()))


def cmd_search(args) -> None:
    retriever, _ = build_stack(args)
    for rank, hit in enumerate(
        retriever.search(args.query, args.mode, args.k, filters_from(args)), start=1
    ):
        chunk = hit.chunk
        print(f"{rank}. [{hit.score:.4f}] {chunk.doc_id}  {chunk.court}  {chunk.date}")
        print(f"   {chunk.section}: {(hit.highlight or chunk.text)[:220]}")


def cmd_ask(args) -> None:
    retriever, _ = build_stack(args)
    result = answer(
        args.question, retriever, get_generator(args.generator), args.k, args.mode,
        filters_from(args),
    )  # fmt: skip
    print(result.text)
    print(f"\ngenerator={result.generator} abstained={result.abstained} grounded={result.grounded}")
    for number, hit in enumerate(result.contexts, start=1):
        print(f"[{number}] {hit.chunk.doc_id}: {hit.chunk.title}")


def ranker(retriever: Retriever, mode: str, k: int = 10, filters: Filters | None = None):
    return lambda query: [h.chunk.doc_id for h in retriever.search(query, mode, k, filters)]


def cmd_eval(args) -> None:
    include_summary = not args.known_item or args.keep_summaries
    retriever, documents = build_stack(args, include_summary=include_summary)
    notes: list[str] = []
    if args.known_item:
        if not documents:
            sys.exit("--known-item needs --corpus")
        queries = ev.known_item_queries(documents, limit=args.limit)
        notes.append(
            "Known-item evaluation: the first sentence of each summary is the query, and "
            "summaries are not indexed. On Elasticsearch, ingest with --no-summaries first."
        )
        if args.keep_summaries:
            notes.append("LEAKY BY DESIGN: summaries are indexed, so queries match themselves.")
    else:
        path = demo_path("queries.jsonl") if args.demo else args.queries
        if not path:
            sys.exit("give --queries, --demo or --known-item")
        queries = [q for q in ev.load_queries(path) if q.relevant]
        if args.split:
            queries = [q for q in queries if q.split == args.split]
        if not queries:
            sys.exit("no labelled queries selected")
        if documents:
            broken = ev.check_labels(queries, {d.id for d in documents})
            if broken:
                sys.exit(f"labels point at unknown documents: {broken}")
    if args.demo:
        notes.insert(0, DEMO_WARNING)
    embedder_name = retriever.embedder.name
    notes.append(f"Embedder: {embedder_name}. Backend: {retriever.backend.stats()['backend']}.")
    if embedder_name.startswith("hash"):
        notes.append(
            "The hash embedder is a character n-gram method and not semantic. "
            "Its dense and hybrid rows are no evidence about embedding models."
        )

    filters = Filters(doc_type=args.doc_type) if args.doc_type else None
    if filters:
        notes.append(f"Only documents of type {args.doc_type} are ranked.")
    runs = [
        ev.evaluate_run(mode, ranker(retriever, mode, filters=filters), queries)
        for mode in ("bm25", "dense", "rrf")
    ]

    def make_linear(alpha: float):
        tuned = Retriever(retriever.backend, retriever.embedder, alpha=alpha)
        return ranker(tuned, "linear", filters=filters)

    linear, alphas = ev.tune_alpha_cv(make_linear, queries)
    runs.append(linear)
    notes.append(f"linear(cv): alpha tuned on other folds; chosen per fold: {alphas}.")

    summary = ev.summarise(runs, queries, baseline=args.baseline)
    markdown = ev.to_markdown(summary, args.title, notes)
    print(markdown)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(markdown, encoding="utf-8")
        ev.save(summary, Path(args.out).with_suffix(".json"))


def cmd_eval_rag(args) -> None:
    retriever, _ = build_stack(args)
    path = demo_path("queries.jsonl") if args.demo else args.queries
    if not path:
        sys.exit("give --queries or --demo")
    generator = get_generator(args.generator)
    answerable = {"n": 0, "context_hit": 0, "answered": 0, "cited_relevant": 0}
    unanswerable = {"n": 0, "abstained": 0}
    grounded = invalid = 0
    queries = ev.load_queries(path)
    for query in queries:
        result = answer(query.text, retriever, generator, args.k, args.mode)
        grounded += result.grounded
        invalid += bool(result.invalid_citations)
        if not query.relevant:
            unanswerable["n"] += 1
            unanswerable["abstained"] += result.abstained
            continue
        answerable["n"] += 1
        context = {hit.chunk.doc_id for hit in result.contexts}
        answerable["context_hit"] += bool(context & set(query.relevant))
        answerable["answered"] += not result.abstained
        answerable["cited_relevant"] += bool(set(result.cited_documents) & set(query.relevant))
    report = {
        "generator": generator.name,
        "embedder": retriever.embedder.name,
        "k": args.k,
        "queries": len(queries),
        "answerable": answerable,
        "unanswerable": unanswerable,
        "grounded": grounded,
        "answers_with_invalid_citations": invalid,
    }
    print(json.dumps(report, indent=2))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")


def cmd_pool(args) -> None:
    from .labelling import save_pool

    retriever, _ = build_stack(args)
    filters = Filters(doc_type=args.doc_type) if args.doc_type else None
    rows = []
    for query in ev.load_queries(args.queries):
        rankings = {
            mode: ranker(retriever, mode, args.depth, filters)(query.text)
            for mode in ("bm25", "dense", "rrf")
        }
        rows.append(
            {
                "id": query.id,
                "query": query.text,
                "kind": query.kind,
                "pool": ev.pool(rankings, args.depth),
            }
        )
    save_pool(args.out, rows)
    print(f"pooled {sum(len(r['pool']) for r in rows)} judgements for {len(rows)} queries")


def cmd_label(args) -> None:
    from .labelling import label_pool

    documents = {d.id: d for d in read_corpus(args.corpus)}
    added = label_pool(list(read_jsonl(args.pool)), documents, args.out)
    print(f"added {added} judgements to {args.out}")


def cmd_inject_eval(args) -> None:
    from .injection import evaluate_injection, to_markdown

    settings = Settings.from_env()
    embedder = get_embedder(args.embedder or settings.embedder, args.embedding_cache)
    documents = read_corpus(args.corpus)
    report = evaluate_injection(
        documents, embedder, get_generator(args.generator), k=args.k, mode=args.mode
    )
    markdown = to_markdown(report)
    print(markdown)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(markdown, encoding="utf-8")
        Path(args.out).with_suffix(".json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def cmd_quality(args) -> None:
    path = demo_path("corpus.jsonl") if args.demo else args.corpus
    if not path:
        sys.exit("give --corpus or --demo")
    markdown = quality.to_markdown(quality.report(read_corpus(path)))
    print(markdown)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(markdown, encoding="utf-8")


def cmd_mcp(args) -> None:
    from .mcp_server import build_server

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    retriever, _ = build_stack(args)
    build_server(retriever, get_generator(args.generator)).run("stdio")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="beacon", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser("fetch", help="download decisions from rechtspraak.nl")
    fetch.add_argument("--date-from", required=True, help="YYYY-MM-DD")
    fetch.add_argument("--date-to")
    fetch.add_argument("--subject", help="rechtsgebied URI from /Waardelijst/Rechtsgebieden")
    fetch.add_argument("--max-docs", type=int, default=500)
    fetch.add_argument("--rate", type=float, default=2.0, help="requests per second, at most 10")
    fetch.add_argument("--output", default="data/corpus.jsonl")
    fetch.add_argument("--cache", default="data/raw")
    fetch.set_defaults(handler=cmd_fetch)

    fetch_ak = commands.add_parser(
        "fetch-ak", help="download the Algoritmekader with its audit and requirement labels"
    )
    fetch_ak.add_argument("--ref", default=None, help="commit or branch; default: pinned commit")
    fetch_ak.add_argument("--checkout", default="data/ak-source")
    fetch_ak.add_argument("--output", default="data/ak")
    fetch_ak.set_defaults(handler=cmd_fetch_ak)

    fetch_model = commands.add_parser(
        "fetch-model", help="download multilingual-e5-small as ONNX, without torch"
    )
    fetch_model.add_argument("--directory", default="data/models/multilingual-e5-small")
    fetch_model.set_defaults(handler=cmd_fetch_model)

    ingest = commands.add_parser("ingest", help="chunk, embed and index a corpus")
    add_stack_arguments(ingest)
    ingest.add_argument("--compounds", action="store_true", help="split Dutch compounds")
    ingest.add_argument("--recreate", action="store_true", help="drop the index first")
    ingest.add_argument("--no-summaries", action="store_true", help="for known-item evaluation")
    ingest.set_defaults(handler=cmd_ingest)

    search = commands.add_parser("search", help="search the index")
    search.add_argument("query")
    add_stack_arguments(search)
    add_filter_arguments(search)
    search.add_argument("--compounds", action="store_true", help="local backend only")
    search.add_argument("--mode", default="smart", choices=MODES)
    search.add_argument("-k", type=int, default=5)
    search.set_defaults(handler=cmd_search)

    ask = commands.add_parser("ask", help="answer a question with citations")
    ask.add_argument("question")
    add_stack_arguments(ask)
    add_filter_arguments(ask)
    ask.add_argument("--generator", default="extractive", help="extractive, ollama[:model], ...")
    ask.add_argument("--mode", default="smart", choices=MODES)
    ask.add_argument("-k", type=int, default=5)
    ask.set_defaults(handler=cmd_ask)

    evaluation = commands.add_parser("eval", help="compare retrieval configurations")
    add_stack_arguments(evaluation)
    evaluation.add_argument("--queries", help="JSONL with id, query, relevant, kind")
    evaluation.add_argument("--known-item", action="store_true", help="summaries as queries")
    evaluation.add_argument("--limit", type=int, help="cap the number of known-item queries")
    evaluation.add_argument(
        "--keep-summaries", action="store_true", help="index summaries anyway, to show the leak"
    )
    evaluation.add_argument("--split", help="only queries from this split, such as dev")
    evaluation.add_argument("--doc-type", help="rank only documents of this type")
    evaluation.add_argument("--compounds", action="store_true", help="local backend only")
    evaluation.add_argument("--baseline", default="bm25", help="run to compare the others against")
    evaluation.add_argument("--title", default="Retrieval evaluation")
    evaluation.add_argument("--out", help="write .md and .json here")
    evaluation.set_defaults(handler=cmd_eval)

    rag = commands.add_parser("eval-rag", help="measure answers, abstentions and citations")
    add_stack_arguments(rag)
    rag.add_argument("--queries")
    rag.add_argument("--generator", default="extractive")
    rag.add_argument("--mode", default="rrf", choices=["bm25", "dense", "rrf", "linear"])
    rag.add_argument("-k", type=int, default=5)
    rag.add_argument("--out")
    rag.set_defaults(handler=cmd_eval_rag)

    pool = commands.add_parser("pool", help="collect top results of each run for labelling")
    add_stack_arguments(pool)
    pool.add_argument("--queries", required=True)
    pool.add_argument("--doc-type")
    pool.add_argument("--depth", type=int, default=10)
    pool.add_argument("--out", required=True)
    pool.set_defaults(handler=cmd_pool)

    label = commands.add_parser("label", help="judge pooled results by hand")
    label.add_argument("--corpus", required=True)
    label.add_argument("--pool", required=True)
    label.add_argument("--out", required=True)
    label.set_defaults(handler=cmd_label)

    inject = commands.add_parser("inject-eval", help="measure prompt injection through documents")
    add_stack_arguments(inject)
    inject.add_argument("--generator", default="extractive")
    inject.add_argument("--mode", default="rrf", choices=["bm25", "dense", "rrf", "linear"])
    inject.add_argument("-k", type=int, default=5)
    inject.add_argument("--out")
    inject.set_defaults(handler=cmd_inject_eval)

    quality_parser = commands.add_parser("quality", help="data quality report")
    quality_parser.add_argument("--corpus")
    quality_parser.add_argument("--demo", action="store_true")
    quality_parser.add_argument("--out")
    quality_parser.set_defaults(handler=cmd_quality)

    mcp = commands.add_parser("mcp", help="run the MCP server over stdio")
    add_stack_arguments(mcp)
    mcp.add_argument("--generator", default="extractive")
    mcp.add_argument("--groups", help="comma-separated access groups for this server process")
    mcp.set_defaults(handler=cmd_mcp)
    return parser


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    args = build_parser().parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
