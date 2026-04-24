FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
COPY app ./app
COPY config ./config
COPY data ./data
COPY samples ./samples
RUN uv sync --frozen --no-dev


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN groupadd --system sentinelops \
    && useradd --system --create-home --gid sentinelops --home-dir /home/sentinelops sentinelops

COPY --from=builder /app/.venv /app/.venv
COPY app ./app
COPY config ./config
COPY data ./data
COPY scripts ./scripts
COPY .env.example ./.env.example
COPY LICENSE ./LICENSE

RUN mkdir -p /app/data/runtime /tmp/sentinelops \
    && chown -R sentinelops:sentinelops /app /tmp/sentinelops

USER sentinelops

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
