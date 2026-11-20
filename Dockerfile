# syntax=docker/dockerfile:1
# One container: FastAPI backend + the statically exported Next.js web app (no Node at runtime).

# ---- 1) build the web app as static files
FROM oven/bun:1 AS web
WORKDIR /repo
COPY package.json bun.lock ./
COPY web/package.json web/bun.lock* ./web/
RUN bun install --frozen-lockfile || bun install
COPY web ./web
RUN cd web && STATIC_EXPORT=1 bun run build

# ---- 2) runtime
FROM python:3.12-slim-bookworm AS runtime
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app:app /data
WORKDIR /app

COPY server/requirements.txt /tmp/server-req.txt
RUN pip install --no-cache-dir -r /tmp/server-req.txt

COPY --chown=app:app server/src /app/server/src
COPY --chown=app:app server/data /app/server/data
COPY --from=web --chown=app:app /repo/web/out /app/web/out

ENV WEB_DIR=/app/web/out \
    AROGYA_DB_PATH=/data/arogya.db \
    STATIC_DIR=/data/static \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status==200 else 1)"
CMD ["python", "/app/server/src/server.py"]
