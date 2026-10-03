# docker/api.Dockerfile — Recommendation API runtime (+ the React frontend build).
# No JVM here on purpose (NFR, PRD §15 Latency: "Spark training không chạy trong request
# path") — the API only reads prepared artifacts from MongoDB via pymongo.
#
# Two stages (change rebuild-ui-react, design D-10): the first builds web/ with Node, the second is the
# API image and receives only the built files. Node is not in the final image. The build is placed at
# /app/web-dist, outside src/ and configs/, which docker-compose mounts over the image.

# ---- stage 1: build the frontend (needs the npm registry; `npm ci` follows web/package-lock.json) ----
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- stage 2: the API ----
FROM python:3.12-slim

ENV PYTHONPATH=/app/src
ENV WEB_DIST_DIR=/app/web-dist

COPY configs/requirements_serving.txt /tmp/requirements_serving.txt
RUN pip install --no-cache-dir -r /tmp/requirements_serving.txt

COPY --from=web /web/dist /app/web-dist

WORKDIR /app
EXPOSE 8000
