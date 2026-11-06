# Build from models/:  docker build -f pii_nl/Dockerfile -t redact-nl .
# Run:                 docker run --rm --network none -i redact-nl - < notes.txt
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY forge forge
COPY ner_nl ner_nl
COPY pii_nl pii_nl
COPY asr_nl asr_nl
COPY text_nl text_nl
COPY clip_search clip_search
RUN pip install --no-cache-dir ".[pii]" \
    && python -m spacy download nl_core_news_md \
    && python -c "import nl_core_news_md"
ENTRYPOINT ["python", "-m", "pii_nl.cli", "--model", "nl_core_news_md"]
