# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Dependencies layer: rebuilt only when pyproject.toml changes.
FROM base AS deps
COPY pyproject.toml ./
RUN mkdir -p app && touch app/__init__.py && pip install --prefix=/install .

FROM base AS runtime
RUN useradd --create-home --uid 10001 sanad
COPY --from=deps /install /usr/local
COPY . .
RUN pip install --no-deps . && chown -R sanad:sanad /app
USER sanad
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live').status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

# Development image: dev tools + hot reload (code is mounted as a volume).
FROM runtime AS dev
USER root
RUN pip install ".[dev]"
USER sanad
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
