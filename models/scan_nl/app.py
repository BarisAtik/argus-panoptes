"""A small web demo for fictional pages. Run with `python -m scan_nl.app`, or deploy as a Space."""

from __future__ import annotations

import os

import numpy as np

from .cli import load_system, redact_image

NOTICE = (
    "Eerste versie, geen garantie. Getest op gegenereerde pagina's, niet op echte scans. "
    "Upload geen echte persoonsgegevens naar een demo die je niet zelf host."
)


def build(model: str):
    import gradio as gr

    system = load_system(model)

    def run(image):
        grey = np.asarray(image.convert("L"))
        out, words, regions, unread = redact_image(grey, system)
        flag = "nakijken" if unread > 0.05 else "geen signaal"
        return out, f"{words} woorden en {regions} ongelezen blokken zwart; ongelezen inkt " \
                    f"{unread:.1%}: {flag}"

    with gr.Blocks(title="Dutch scan redaction") as demo:
        gr.Markdown(f"# Scans lokaal zwartlakken\n\n{NOTICE}")
        image = gr.Image(type="pil", label="Pagina")
        button = gr.Button("Zwartlakken")
        output = gr.Image(label="Resultaat")
        summary = gr.Textbox(label="Samenvatting")
        button.click(run, image, [output, summary])
    return demo


if __name__ == "__main__":
    build(os.environ.get("SPACY_MODEL", "nl_core_news_md")).launch(
        server_name=os.environ.get("HOST", "127.0.0.1")
    )
