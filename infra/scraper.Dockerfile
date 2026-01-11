FROM python:3.13.3-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.6.5

COPY scraper/pyproject.toml /app/scraper/pyproject.toml
COPY scraper/uv.lock /app/scraper/uv.lock
COPY api/requirements.txt /app/api/requirements.txt

RUN pip install --no-cache-dir -r /app/api/requirements.txt

COPY scraper /app/scraper
COPY api /app/api

WORKDIR /app/scraper

# uv 0.6+ removed --system from sync; export requirements and pip install
RUN uv export --frozen --no-dev --no-hashes > /tmp/requirements.txt \
    && uv pip install --system -r /tmp/requirements.txt

RUN mkdir -p /ms-playwright \
    && python -m playwright install --with-deps chromium

RUN apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --system --uid 10001 --create-home appuser \
    && chown -R appuser:appuser /app /ms-playwright

USER appuser

ENV PYTHONPATH="/app/api:/app/scraper:${PYTHONPATH}"

CMD ["celery", "-A", "bets_scraper.celery_app.app", "worker", "--loglevel=info", "--queues=bets-scraper"]
