# docker/spark.Dockerfile — Spark runtime for loaders, streaming and orchestration jobs.
# pyspark version matches Person 1's pin (configs/requirements.txt: pyspark==3.5.7) so
# ALSModel.load() reads a model written by the same Spark version (design.md D-1).
FROM python:3.12-slim

# default-jdk-headless -> /usr/lib/jvm/default-java (stable symlink across amd64/arm64;
# Spark 3.5.x supports Java 17). procps gives `ps`, useful when debugging a running job.
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-jdk-headless \
        procps \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/default-java
ENV PATH="${JAVA_HOME}/bin:${PATH}"
ENV PYTHONPATH=/app/src

COPY configs/requirements_serving.txt /tmp/requirements_serving.txt
RUN pip install --no-cache-dir -r /tmp/requirements_serving.txt "pyspark==3.5.7"

WORKDIR /app
