# docker/api.Dockerfile — Recommendation API runtime.
# No JVM here on purpose (NFR, PRD §15 Latency: "Spark training không chạy trong request
# path") — the API only reads prepared artifacts from MongoDB via pymongo.
FROM python:3.12-slim

ENV PYTHONPATH=/app/src

COPY configs/requirements_serving.txt /tmp/requirements_serving.txt
RUN pip install --no-cache-dir -r /tmp/requirements_serving.txt

WORKDIR /app
EXPOSE 8000
