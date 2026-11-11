FROM node:22.23.4-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_ALLOW_DEMO_MODE=true
RUN npm run build
RUN find dist/assets -type f \( -name '*.js' -o -name '*.css' \) -exec gzip -9k {} +

FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/constraints.txt ./
RUN pip install --no-cache-dir -e . aiosqlite -c constraints.txt

COPY backend/ ./
COPY --from=frontend /fe/dist ./static

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/demo_data /app/demo_uploads \
    && chown -R appuser:appuser /app
USER appuser

ENV DEMO_ISOLATED_SESSIONS=true \
    ALLOW_DEMO_MODE=true \
    DEBUG=false \
    ENABLE_API_DOCS=false \
    DATABASE_URL=sqlite+aiosqlite:///./demo_data/unused.db \
    RATE_LIMIT_ENABLED=true \
    RATE_LIMIT_BACKEND=memory \
    TRUSTED_PROXY_IPS=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10,fc00::/7 \
    PAYMENTS_ARE_SIMULATED=true \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:%s/ready' % os.environ.get('PORT','8000'), timeout=4)" || exit 1

CMD ["sh", "-c", "exec uvicorn app.demo.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
