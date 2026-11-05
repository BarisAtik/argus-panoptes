"""Write an index as Elasticsearch bulk NDJSON, so a vector search stack can serve it.

    python -m clip_search.es_export --index-dir runs/clip/index --out runs/clip/bulk.ndjson
    curl -H 'Content-Type: application/x-ndjson' -XPOST localhost:9200/_bulk \
         --data-binary @runs/clip/bulk.ndjson
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clip_search.index import ImageIndex


def mapping(dims: int) -> dict:
    return {"mappings": {"properties": {
        "image_id": {"type": "keyword"},
        "embedding": {"type": "dense_vector", "dims": dims, "index": True,
                      "similarity": "cosine"},
    }}}


def export(index: ImageIndex, out: Path, index_name: str = "forge-images") -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for image_id, vector in zip(index.ids, index.embeddings):
            handle.write(json.dumps({"index": {"_index": index_name, "_id": image_id}}) + "\n")
            handle.write(json.dumps({"image_id": image_id,
                                     "embedding": [round(float(v), 6) for v in vector]}) + "\n")
    return len(index.ids)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    loaded = ImageIndex.load(args.index_dir)
    print(f"{export(loaded, args.out)} documents. Mapping:")
    print(json.dumps(mapping(loaded.embeddings.shape[1]), indent=2))
