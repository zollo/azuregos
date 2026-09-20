# ── Base ────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System deps: build tools + libs required by python3-saml (xmlsec/libxml2)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxmlsec1-dev \
        libxmlsec1-openssl \
        pkg-config \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for layer caching
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install ".[dev]"

# ── Dev target (hot reload; source is bind-mounted at runtime) ───────────
FROM base AS dev
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Prod target ─────────────────────────────────────────────────────────
FROM base AS prod
COPY . .
RUN pip install "." --no-deps
# Drop privileges
RUN useradd -m appuser && chown -R appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
