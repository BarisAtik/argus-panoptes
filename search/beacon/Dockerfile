# The Beacon web app. Torch-free: quantised ONNX embeddings and no build tools at run time.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[web,onnx,files,compounds]"
RUN useradd --create-home --uid 10001 beacon
USER beacon
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/healthz')"
CMD ["beacon", "serve", "--host", "0.0.0.0"]
