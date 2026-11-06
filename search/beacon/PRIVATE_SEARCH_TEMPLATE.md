# Using Beacon as a private document search template

The idea: search and cited answers over documents that may not leave the building. Everything
runs on the owner's machine, which is the part hosted assistants cannot offer.

## What makes it private

| Layer | Private setup |
| --- | --- |
| Engine | Self-managed Elasticsearch, bound to localhost or an internal network |
| Embeddings | Run locally with `st:`, `onnx:` (no torch) or `spacy:` |
| Answers | `extractive` or `ollama:<model>`. **Do not use `anthropic:` on private documents**, since passages leave the machine |
| Agents | MCP over stdio or HTTP, read-only tools, scoped per user |
| Records | Audit log with hashed queries, plain text only if the operator opts in |

## Try it on a folder

```bash
pip install -e ".[web,onnx,files,compounds]"
beacon fetch-model

cat > acl.yaml <<YAML
default: [admin]
rules:
  - path: "juridisch/*"
    groups: [juridisch]
  - path: "publiek/*"
    groups: [iedereen]
YAML

beacon ingest-dir ~/documenten --acl acl.yaml --out data/files/corpus.jsonl
cat data/files/ingest-report.md          # read this before you trust the search
beacon add-user lena --groups juridisch,iedereen
beacon serve --backend local --corpus data/files/corpus.jsonl \
  --embedder onnx:data/models/multilingual-e5-small --embedding-cache data/cache
# http://127.0.0.1:8080, log in with the token. MCP is at /mcp/ with `Authorization: Bearer`.
```

With Elasticsearch, add `--index` to `ingest-dir`. It keeps a state file and on each run re-indexes
only changed files, and removes deleted ones. A changed access rule counts as a change.

## Adapting it to a new collection

1. Run `beacon ingest-dir` and read its report. It lists unreadable files, scanned PDFs, duplicates
   and files without an access rule. Files without a rule go to the group `admin`.
2. Label 50 to 100 real queries with the people who will use the system, then run `beacon eval`.
   Choose the embedder and fusion from that data, not from defaults.
3. Replace the list in `synonyms.py` and the laws in `citations.py` with the client's own terms.

## Missing before this is a product

- **Directory sync and login.** Users and groups live in a YAML file, with tokens. A client will
  want groups from their directory and single sign-on.
- **OCR.** Scanned PDFs are reported, not read.
- **TLS and a real secrets setup.** The app has no TLS of its own, so put a reverse proxy in front
  of it for anything beyond one machine.
- **A hardening review.** Tests cover escaping, access, headers and throttling, but nobody
  independent has attacked it. Sessions live in one process, and adding a user needs a restart.
- **Mail and shared-drive connectors.** Only folders are read.
- **Evaluation on real user questions.**

## What a client demo can show today

Run it on the Algoritmekader, because it is public, Dutch and shareable:

- Search in English over Dutch text, side by side with BM25, which cannot do it.
- `reports/ak-holdout.md`: a one-shot score against labels the builder did not write. This is
  the part most vendors cannot show.
- `tests/test_acl.py` and `tests/test_web.py`: a user without the right group gets the same answer
  as for a missing file, in the browser, the API and MCP.
- `reports/ak-groundedness.md`: what the claim check catches, and the 42% of subtle errors it misses.
- `reports/ak-injection.md`: the honest limits of filtering planted instructions.

## Licensing notes (not legal advice)

- Elasticsearch is free to self-manage. Elastic's FAQ says a contractor may set it up for a client's
  internal use, and it may be used inside your own application.
- Elastic's licence does not allow offering it to others as a **managed service**, for example giving
  customers direct access to substantial parts of the API or Kibana. Keep it behind your own app.
- Hybrid fusion in the client avoids any need for a paid tier.
