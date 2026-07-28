# Base Stage
FROM python:3.14-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WORKDIR=/app

WORKDIR $WORKDIR

# Build Stage
FROM base AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install poetry==2.4.1

COPY pyproject.toml README.md $WORKDIR/

RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi

# Production API Stage
FROM base AS api

# Copy installed site-packages and binaries from builder
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src $WORKDIR/src
COPY alembic.ini $WORKDIR/alembic.ini
COPY scripts/entrypoint.sh $WORKDIR/entrypoint.sh
RUN chmod +x $WORKDIR/entrypoint.sh

EXPOSE 8000
CMD ["/app/entrypoint.sh"]

# Production Worker Stage
FROM base AS worker

# Copy installed site-packages and binaries from builder
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src $WORKDIR/src
COPY alembic.ini $WORKDIR/alembic.ini

CMD ["celery", "-A", "src.workers.app.celery_app", "worker", "--loglevel=info"]
