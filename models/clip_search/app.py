"""Gradio demo: type a query in Dutch or English, see the closest images from a local index.

    python -m clip_search.app --index-dir runs/clip/index --image-dir runs/coco/val2017 \
        --model openclip:xlm-roberta-base-ViT-B-32:laion5b_s13b_b90k

Designed to be copied into a Hugging Face Space (Gradio SDK; ZeroGPU is optional).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from clip_search.backends import load_backend
from clip_search.index import ImageIndex


def search_gallery(query: str, backend, index: ImageIndex, image_dir: Path, k: int = 12) -> list:
    query = query.strip()
    if not query:
        return []
    vector = backend.encode_texts([query])[0]
    return [(str(image_dir / image_id), f"{score:.3f}") for image_id, score in
            index.search(vector, k)]


def build_app(backend, index: ImageIndex, image_dir: Path):
    import gradio as gr

    with gr.Blocks(title="Honderd Ogen: zoeken in beelden") as app:
        gr.Markdown("# Honderd Ogen\nBeschrijf wat je zoekt, in het Nederlands of Engels.")
        query = gr.Textbox(label="Zoekopdracht", placeholder="een hond op het strand")
        gallery = gr.Gallery(label="Resultaten", columns=4)
        query.submit(lambda q: search_gallery(q, backend, index, image_dir), query, gallery)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    app = build_app(load_backend(args.model), ImageIndex.load(args.index_dir), args.image_dir)
    app.launch(server_name=args.host, server_port=args.port)


if __name__ == "__main__":
    main()
