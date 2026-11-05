# Reproducible CPU environment for the sklearn baseline and tests.
#   docker build -t ntl . && docker run --rm -v "$PWD/data:/app/data" ntl make test
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends make unzip && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app/src
CMD ["make", "test"]
