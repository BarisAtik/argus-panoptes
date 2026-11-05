FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY adapters ./adapters
COPY analysis ./analysis
RUN pip install --no-cache-dir ".[llm,mcp]"
USER nobody
ENTRYPOINT ["gauntlet"]
