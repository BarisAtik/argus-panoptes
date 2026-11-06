# Build from models/:  docker build -f scan_nl/Dockerfile -t scan-nl .
# Run:  docker run --rm --network none -v "$PWD/in:/in" scan-nl /in/page.png -o /in/out.png
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-nld \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY forge forge
COPY ner_nl ner_nl
COPY pii_nl pii_nl
COPY scan_nl scan_nl
COPY asr_nl asr_nl
COPY text_nl text_nl
COPY clip_search clip_search
RUN pip install --no-cache-dir ".[pii,scan]" \
    && python -m spacy download nl_core_news_md \
    && python -c "import nl_core_news_md"
ENTRYPOINT ["python", "-m", "scan_nl.cli", "--model", "nl_core_news_md"]
