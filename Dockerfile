# ── Stage 1: Frontend build ────────────────────────────────────
FROM node:20-slim AS frontend
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci --production=false
COPY web/ .
RUN npm run build

# ── Stage 2: Python build ─────────────────────────────────────
FROM python:3.10-slim AS builder
WORKDIR /build

# System deps for C extensions (scipy, netCDF4, HDF5)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libhdf5-dev libnetcdf-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir --prefix=/install -e .

# ── Stage 3: Runtime ──────────────────────────────────────────
FROM python:3.10-slim

# Runtime-only system libs (no compiler, no Node.js)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libhdf5-103 libnetcdf19 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (UID 1000 = standard)
RUN useradd --create-home --uid 1000 aria
USER aria
WORKDIR /home/aria/app

# Copy installed packages + source from builder
COPY --from=builder /install /usr/local
COPY --chown=aria:aria src/ src/
COPY --chown=aria:aria data/ data/
COPY --chown=aria:aria configs/ configs/
COPY --chown=aria:aria pyproject.toml .

# Copy React production build from frontend stage
COPY --from=frontend --chown=aria:aria /web/dist/ web/dist/

# Create log directory
RUN mkdir -p logs

ENV ARIA_PORT=8090
ENV ARIA_HOST=0.0.0.0
EXPOSE 8090

# Health check for Docker Compose / Swarm
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8090/healthz')" || exit 1

ENTRYPOINT ["python", "-m", "aria.simulator.web_dashboard"]
CMD ["--port", "8090"]
