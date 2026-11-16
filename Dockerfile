# TwinSite: one container = Flask site (gunicorn) + platform API + worker.
# Build:  docker build -t twinsite .
# Run:    docker run -p 7860:7860 -e GROQ_API_KEY=... twinsite
# Listens on $PORT (default 7860, the Hugging Face Spaces app_port).

# --- Stage 1: build the React console (frontend/dist is not tracked by git) ------------------
FROM node:20-slim AS console
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
# The console imports ../contracts (types + synthetic examples via the @contracts alias).
COPY contracts/ /build/contracts/
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python runtime -------------------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860 \
    APP_DIR=/app \
    TWINSITE_DATA_DIR=/data/twinsite
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Non-root user (uid 1000 is what Hugging Face Spaces runs as).
RUN useradd -m -u 1000 twinsite \
    && mkdir -p /data/twinsite \
    && chown -R twinsite:twinsite /data

COPY --chown=twinsite:twinsite . /app
COPY --from=console --chown=twinsite:twinsite /build/frontend/dist /app/frontend/dist
RUN chmod +x /app/ops/container/start.sh
# Train the PCA / K-means models once at build time (same data + seed = same models); at runtime the
# web process applies them with NumPy and never imports scikit-learn (~100 MB less RAM on 512 MB hosts).
RUN cd /app/backend && DATA_READY_DIR=/app/data_ready PYTHONPATH=/app/backend:/app \
    python -m services.ml_models export /app/ml_models.npz
ENV TWINSITE_ML_MODELS=/app/ml_models.npz

# Characterize the real analog sites (Earth) and targets (Moon, Mars) once at build time, from the live
# NASA/USGS sources, and bake them into the image. Hosts with an ephemeral disk (Render free, Hugging Face)
# then start with every site present instead of re-seeding for ~30 min after each restart. Sites a source
# could not serve during the build are retried by the idempotent runtime seeding in start.sh.
RUN cd /app && TWINSITE_DATA_DIR=/data/twinsite TWINSITE_SOURCE_DATA_DIR=/data/twinsite/source-cache \
    TWINSITE_SECRET_ENV_FILE=/nonexistent PYTHONPATH=/app/backend:/app DATA_READY_DIR=/app/data_ready \
    timeout 1800 python ops/seed_sites.py --workers 4 | tail -3 \
    || echo "build-time seeding incomplete; runtime seeding will finish it"; \
    chown -R twinsite:twinsite /data

USER twinsite
EXPOSE 7860
CMD ["/app/ops/container/start.sh"]
