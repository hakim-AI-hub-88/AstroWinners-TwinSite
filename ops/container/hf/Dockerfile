# Hugging Face Space wrapper for TwinSite (visionary platform).
# The Space repo holds only this Dockerfile and README.md. The build clones the GitHub branch on
# Hugging Face's network, so the ~260 MB data_ready/ never has to be uploaded (no Git LFS needed).
# To pick up new commits: Space -> Settings -> Factory rebuild (or bump REF to a commit SHA).

# --- Stage 0: source --------------------------------------------------------------------------
FROM debian:bookworm-slim AS src
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
ARG REPO=https://github.com/hakim-AI-hub-88/AstroWinners-TwinSite.git
ARG REF=platform-integration
RUN git clone --depth 1 --branch "$REF" "$REPO" /src && rm -rf /src/.git /src/frontend/node_modules /src/frontend/dist

# --- Stage 1: React mission console -----------------------------------------------------------
FROM node:20-slim AS console
WORKDIR /build/frontend
COPY --from=src /src/frontend/package.json /src/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY --from=src /src/contracts/ /build/contracts/
COPY --from=src /src/frontend/ ./
RUN npm run build

# --- Stage 2: Python runtime (Flask site + platform API + worker) ------------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    PORT=7860 APP_DIR=/app TWINSITE_DATA_DIR=/data/twinsite
WORKDIR /app
COPY --from=src /src/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd -m -u 1000 twinsite && mkdir -p /data/twinsite && chown -R twinsite:twinsite /data
COPY --from=src --chown=twinsite:twinsite /src /app
COPY --from=console --chown=twinsite:twinsite /build/frontend/dist /app/frontend/dist
RUN chmod +x /app/ops/container/start.sh
USER twinsite
EXPOSE 7860
CMD ["/app/ops/container/start.sh"]
