# proxbox-scheduler: standalone container that fires periodic Proxbox sync
# triggers against proxbox-api (or via `manage.py proxbox_sync`).
#
# Build:
#   docker build -t proxbox-scheduler:0.0.15 proxbox_scheduler/
#
# Run (HTTP invocation, the default):
#   docker run --rm \
#     -e PROXBOX_MODE='cron=0 */4 * * *' \
#     -e PROXBOX_SCHEDULER_TZ=America/Sao_Paulo \
#     -e PROXBOX_API_URL=http://proxbox-api:8000 \
#     -e PROXBOX_API_KEY=... \
#     proxbox-scheduler:0.0.15

FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY proxbox_scheduler ./proxbox_scheduler

RUN pip install --no-cache-dir --upgrade pip build && \
    python -m build --wheel --outdir /dist

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random

RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 scheduler

COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl

USER scheduler
WORKDIR /home/scheduler

ENV PROXBOX_MODE=off \
    PROXBOX_SCHEDULER_INVOKE=http \
    PROXBOX_SCHEDULER_TZ=UTC \
    PROXBOX_SCHEDULER_BACKOFF_ON_ERROR_SECONDS=30 \
    PROXBOX_SCHEDULER_LOG_JSON=true \
    PROXBOX_SCHEDULER_LOG_LEVEL=INFO

ENTRYPOINT ["python", "-m", "proxbox_scheduler"]
