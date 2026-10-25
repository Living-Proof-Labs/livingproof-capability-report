# Installed package only; no source checkout, Task or runtime network requirement.
ARG PYTHON_IMAGE=python:3.12.12-slim-bookworm
FROM ${PYTHON_IMAGE} AS python-base

FROM ghcr.io/astral-sh/uv:0.12.23 AS uv-tools

FROM python-base AS development
COPY --from=uv-tools /uv /uvx /usr/local/bin/
ARG TASK_VERSION=3.54.0
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates curl git && rm -rf /var/lib/apt/lists/*
RUN --mount=type=secret,id=ca,required=false set -eu; \
    if [ -f /run/secrets/ca ]; then export CURL_CA_BUNDLE=/run/secrets/ca; fi; \
    arch="$(dpkg --print-architecture)"; \
    mkdir /tmp/task; cd /tmp/task; \
    curl -fsSLO "https://github.com/go-task/task/releases/download/v${TASK_VERSION}/task_linux_${arch}.tar.gz"; \
    curl -fsSLO "https://github.com/go-task/task/releases/download/v${TASK_VERSION}/task_checksums.txt"; \
    sha256sum --ignore-missing -c task_checksums.txt; \
    tar -xzf "task_linux_${arch}.tar.gz" task; \
    install task /usr/local/bin/task; rm -rf /tmp/task
RUN useradd --create-home --uid 1000 --shell /bin/bash vscode
ENV UV_PROJECT_ENVIRONMENT=/tmp/report-venv UV_CACHE_DIR=/tmp/report-uv-cache
WORKDIR /workspace/report
USER vscode
CMD ["sleep", "infinity"]

FROM python-base AS runtime
ARG VERSION
LABEL org.opencontainers.image.source="https://github.com/Living-Proof-Labs/livingproof-capability-report"
LABEL org.opencontainers.image.version="${VERSION}"
COPY dist/wheels/ /tmp/wheels/
RUN python -m venv /opt/report && /opt/report/bin/pip install --no-index --find-links=/tmp/wheels "livingproof-capability-report==${VERSION}" && rm -rf /tmp/wheels
ENV PATH="/opt/report/bin:${PATH}"
WORKDIR /data
ENTRYPOINT ["livingproof-capability-report"]
CMD ["--help"]
