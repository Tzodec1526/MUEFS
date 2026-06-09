# Production image for the public hosted demo: one container that builds the React
# SPA and serves it alongside the FastAPI API, with per-visitor SQLite isolation.
# Build context is the repo root. Run target: app.demo.server:app
#
#   docker build -t muefs-demo .
#   docker run -p 8000:8000 muefs-demo   # then open http://localhost:8000

# ---- Stage 1: build the React SPA ----
FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Same-origin: leave VITE_API_URL empty so the app calls /api/v1 on its own host.
ENV VITE_ALLOW_DEMO_MODE=true
RUN npm run build

# ---- Stage 2: backend serving the API + the built SPA ----
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install deps first for layer caching (base deps + the SQLite async driver).
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir -e . aiosqlite

COPY backend/ ./
COPY --from=frontend /fe/dist ./static

# Run as an unprivileged user. Pre-create the demo's writable dirs and hand /app to it.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/demo_data /app/demo_uploads \
    && chown -R appuser:appuser /app
USER appuser

ENV DEMO_ISOLATED_SESSIONS=true \
    ALLOW_DEMO_MODE=true \
    DATABASE_URL=sqlite+aiosqlite:///./demo_data/unused.db \
    RATE_LIMIT_ENABLED=true \
    RATE_LIMIT_BACKEND=memory \
    PAYMENTS_ARE_SIMULATED=true \
    PORT=8000

EXPOSE 8000

# Liveness: hit the FastAPI /health route (honors the injected $PORT).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:%s/health' % os.environ.get('PORT','8000'))" || exit 1

# Render injects $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn app.demo.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
