# The pipeline, packaged. No source data, no results and no instance are baked in; they are
# mounted at run time (see compose.yaml). The base image is pinned by digest, python:3.12-slim
# as pulled on 11 September 2026.
FROM python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DAGSTER_HOME=/app/.dagster

# Dependencies first, so they cache; then the package itself, installed the way a user would.
COPY requirements.txt pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements.txt
COPY simd_ingest/ simd_ingest/
RUN pip install --no-cache-dir --no-deps .

COPY config/ config/
COPY tests/ tests/
COPY docs/ docs/
COPY workspace.yaml ./
RUN mkdir -p manual_data data results .dagster && printf 'telemetry:\n  enabled: false\n' > .dagster/dagster.yaml

ENTRYPOINT ["simd-ingest"]
CMD ["build"]
