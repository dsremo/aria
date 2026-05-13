# ARIA Conjunction Screener — production image.
#
# Multi-stage build keeps the runtime image lean.  We only ship the
# Python source tree under ``src/aria/products/conjunction_screener``
# plus its imports — no scientific notebooks, no test data.

FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY pyproject.toml requirements*.txt /build/ 2>/dev/null || true
COPY src/ /build/src/

RUN pip install --upgrade pip && \
    pip install --prefix=/install \
        aiohttp==3.9.5 \
        numpy \
        sgp4 \
        scipy \
        pyerfa \
        astropy \
        tomli

# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ARIA_SCREENER_DB=/data/screener_tenants.sqlite3 \
    PYTHONPATH=/app/src

RUN groupadd -r aria && useradd -r -g aria aria

COPY --from=builder /install /usr/local
COPY src/ /app/src/

RUN mkdir -p /data && chown -R aria:aria /data

USER aria
WORKDIR /app

EXPOSE 8443

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys;\
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8443/v1/healthz', timeout=2).status==200 else 1)"

ENTRYPOINT ["python", "-m", "aria.products.conjunction_screener", "serve", \
            "--host", "0.0.0.0", "--port", "8443"]
