# Using Beacon as a private document search template

The idea: search and cited answers over documents that may not leave the building. Everything
runs on the owner's machine, which is the part hosted assistants cannot offer.

## What makes it private

| Layer | Private setup |
| --- | --- |
| Engine | Self-managed Elasticsearch, bound to localhost or an internal network |
| Embeddings | Run locally with `st:` or `spacy:` |
| Answers | `extractive` or `ollama:<model>`. **Do not use `anthropic:` on private documents**, since passages leave the machine |
| Agents | MCP over stdio, read-only tools |

## Adapting it to a new collection

1. Write a source in `src/beacon/sources/` that produces `Document` objects. PDF, Word and mail
   parsers are the usual work, and most of the effort goes here.
2. Run `beacon quality`, and adapt its checks to the collection.
3. Label 50 to 100 real queries with the people who will use the system, then run `beacon eval`.
   Choose the embedder and fusion from that data, not from defaults.
4. Add access control before real use.

## Missing before this is a product

- **Document-level permissions.** There are none. Everyone who can search can see everything.
  Filter per user in `filter_clauses`, and test that it cannot be bypassed.
- **A user interface.** There is a CLI and MCP only.
- **File parsing and OCR.** Only rechtspraak XML is implemented.
- **Incremental sync, deletion and audit logging.** Deletion matters for GDPR requests.
- **TLS and a real secrets setup** for anything beyond one machine.
- **Evaluation on real user questions.**

## Licensing notes (not legal advice)

- Elasticsearch is free to self-manage. Elastic's FAQ says a contractor may set it up for a client's
  internal use, and it may be used inside your own application.
- Elastic's licence does not allow offering it to others as a **managed service**, for example giving
  customers direct access to substantial parts of the API or Kibana. Keep it behind your own app.
- Hybrid fusion in the client avoids any need for a paid tier.
