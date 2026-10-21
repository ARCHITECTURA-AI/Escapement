# One image for the API, the jobs worker and the reference worker.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY engine ./engine
COPY api ./api
COPY client ./client
COPY worker ./worker
RUN pip install ./engine ./api[s3] ./client ./worker
RUN useradd --create-home --uid 10001 escapement && mkdir -p /data && chown escapement /data
USER escapement
ENV ESCAPEMENT_DATA_DIR=/data
EXPOSE 8000
CMD ["escapement-api", "serve", "--host", "0.0.0.0", "--port", "8000", "--no-worker"]
