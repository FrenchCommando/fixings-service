# fixings-service image.
#
# arm64 (Raspberry Pi): build natively on the Pi via `docker compose up -d --build`,
# or cross-build from a desktop:
#   docker buildx build --platform linux/arm64 -t fixings-service .
# A wrong-arch image fails at runtime with `exec format error`.
#
# Contract with the proxy-auth stack: listen on 5000 (matches compose `expose` and the
# nginx upstream). The service has no auth of its own — Authelia protects it at the edge.
FROM python:3.13-slim

WORKDIR /app

# Deps first so this layer caches unless requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source + data files (seed_tickers.txt feeds `python -m seed`) — secrets are mounted at
# runtime (see compose), never baked in.
COPY *.py index.html seed_tickers.txt ./

EXPOSE 5000
CMD ["python", "-m", "service"]
