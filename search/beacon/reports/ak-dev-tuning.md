# Dev tuning on the Algoritmekader

100 dev queries, measures only, embedder `onnx:multilingual-e5-small`, in-process backend. Every value is mean nDCG@10 unless the column says otherwise.

| Trial | bm25 | dense | rrf | recall@10 rrf |
| --- | --- | --- | --- | --- |
| default | 0.573 | 0.471 | 0.572 | 0.663 |
| chunks-120 | 0.588 | 0.491 | 0.566 | 0.660 |
| chunks-350 | 0.578 | 0.465 | 0.570 | 0.662 |
| title-prefix | 0.576 | 0.537 | 0.608 | 0.654 |
| compounds | 0.589 | 0.471 | 0.583 | 0.668 |
| rrf-k-10 | 0.573 | 0.471 | 0.567 | 0.650 |
| rrf-k-30 | 0.573 | 0.471 | 0.578 | 0.675 |
| rrf-k-100 | 0.573 | 0.471 | 0.570 | 0.661 |

## Decisions

- `chunks-350`: -0.002 on rrf, dropped
- `title-prefix`: +0.036 on rrf, kept
- `compounds`: +0.010 on rrf, kept
- `rrf-k-30`: +0.005 on rrf, kept

Frozen: `{"max_words": 220, "overlap_words": 40, "title_prefix": true, "compounds": true, "rrf_k": 30}`, combined dev nDCG@10 0.606.

Copying check: a relevant page holds 49% of a query's stems, against 17% for the average measure.
