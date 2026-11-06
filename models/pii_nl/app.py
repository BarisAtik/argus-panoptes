"""A small web demo, for fictional text. Run with `python -m pii_nl.app`, or deploy as a Space."""

from __future__ import annotations

import os

from .cli import load_model, redact_json

EXAMPLE = (
    "goedemiddag u spreekt met mehmet yilmaz ik woon op kerkstraat 12 en mijn nummer is "
    "nul zes een twee drie vier vijf zes zeven acht"
)
NOTICE = (
    "Eerste versie, geen garantie: in chat en transcripten bleef in de benchmark ongeveer 16% "
    "van de namen staan. Controleer de uitvoer. Plak geen echte persoonsgegevens in een demo "
    "die je niet zelf host."
)


def build(model: str):
    import gradio as gr

    nlp = load_model(model)

    def run(text: str):
        result = redact_json(text, nlp)
        rows = [[h["kind"], h["source"], h["value"]] for h in result["hits"]]
        return result["text"], rows

    with gr.Blocks(title="Dutch redaction") as demo:
        gr.Markdown(f"# Lokale Nederlandse redactie\n\n{NOTICE}")
        text = gr.Textbox(label="Tekst", value=EXAMPLE, lines=8)
        button = gr.Button("Redigeer")
        output = gr.Textbox(label="Resultaat", lines=8)
        table = gr.Dataframe(headers=["Soort", "Bron", "Waarde"], label="Gevonden")
        button.click(run, text, [output, table])
    return demo


if __name__ == "__main__":
    build(os.environ.get("SPACY_MODEL", "nl_core_news_md")).launch(
        server_name=os.environ.get("HOST", "127.0.0.1")
    )
