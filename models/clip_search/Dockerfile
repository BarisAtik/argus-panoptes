# Demo image. Build from the models/ folder:
#   docker build -f clip_search/Dockerfile -t forge-clip .
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY forge ./forge
COPY asr_nl ./asr_nl
COPY text_nl ./text_nl
COPY clip_search ./clip_search
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu ".[vision,demo]"
EXPOSE 7860
CMD ["python", "-m", "clip_search.app", "--host", "0.0.0.0", \
     "--index-dir", "/runs/index", "--image-dir", "/images", \
     "--model", "openclip:xlm-roberta-base-ViT-B-32:laion5b_s13b_b90k"]
