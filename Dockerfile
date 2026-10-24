# Installed package only; no source checkout, Task or runtime network requirement.
FROM python:3.12.12-slim-bookworm
ARG VERSION
LABEL org.opencontainers.image.source="https://github.com/Living-Proof-Labs/livingproof-capability-report"
LABEL org.opencontainers.image.version="${VERSION}"
COPY dist/wheels/ /tmp/wheels/
RUN python -m venv /opt/report && /opt/report/bin/pip install --no-index --find-links=/tmp/wheels "livingproof-capability-report==${VERSION}" && rm -rf /tmp/wheels
ENV PATH="/opt/report/bin:${PATH}"
WORKDIR /data
ENTRYPOINT ["livingproof-capability-report"]
CMD ["--help"]
