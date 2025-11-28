FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/root/.local/bin:$PATH"

WORKDIR /app

RUN apk add --no-cache build-base

COPY pyproject.toml uv.lock README.md /app/

RUN pip install --no-cache-dir uv

COPY config.yaml config.yaml.template /app/
COPY src /app/src

RUN uv sync --locked --no-dev

ENV SCRAPER_CONFIG=/app/config.yaml
CMD ["uv", "run", "--no-sync", "otel-api-scraper"]
