# Using Beacon as a private document search template

The idea: search and cited answers over documents that may not leave the building. Everything
runs on the owner's machine, which is the part hosted assistants cannot offer.

## What makes it private

| Layer | Private setup |
| --- | --- |
| Engine | Self-managed Elasticsearch, bound to localhost or an internal network |
| Embeddings | Run locally with `st:`, `onnx:` (no torch) or `spacy:` |
| Answers | `extractive` or `ollama:<model>`. **Do not use `anthropic:` on private documents**, since passages leave the machine |
| Agents | MCP over stdio, read-only tools |

## Adapting it to a new collection

1. Write a source in `src/beacon/sources/` that produces `Document` objects. PDF, Word and mail
   parsers are the usual work, and most of the effort goes here.
2. Run `beacon quality`, and adapt its checks to the collection.
3. Label 50 to 100 real queries with the people who will use the system, then run `beacon eval`.
   Choose the embedder and fusion from that data, not from defaults.
4. Give each `Document` its `acl` groups, and start every server with `--groups` or
   `BEACON_GROUPS`.

## Missing before this is a product

- **Per-user permissions.** Group filters now hold on every path, tested in `tests/test_acl.py`.
  But one MCP process serves one set of groups, chosen when it starts. Serving many users from
  one process needs real authentication, and groups synced from the client's directory.
- **A user interface.** There is a CLI and MCP only.
- **File parsing and OCR.** Only rechtspraak XML and Markdown with front matter are implemented.
- **Incremental sync, deletion and audit logging.** Deletion matters for GDPR requests.
- **TLS and a real secrets setup** for anything beyond one machine.
- **Evaluation on real user questions.**

## What a client demo can show today

Run it on the Algoritmekader, because it is public, Dutch and shareable:

- Search in English over Dutch text, side by side with BM25, which cannot do it.
- `reports/ak-holdout.md`: a one-shot score against labels the builder did not write. This is
  the part most vendors cannot show.
- `tests/test_acl.py`: a user without the right group gets the same answer as for a missing file.
- `reports/ak-injection.md`: the honest limits of filtering planted instructions.

## Licensing notes (not legal advice)

- Elasticsearch is free to self-manage. Elastic's FAQ says a contractor may set it up for a client's
  internal use, and it may be used inside your own application.
- Elastic's licence does not allow offering it to others as a **managed service**, for example giving
  customers direct access to substantial parts of the API or Kibana. Keep it behind your own app.
- Hybrid fusion in the client avoids any need for a paid tier.
