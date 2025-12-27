FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Install uv for faster installs
RUN pip install --no-cache-dir uv

# Copy dependency manifests
COPY scraper/pyproject.toml /app/scraper/pyproject.toml
COPY scraper/uv.lock /app/scraper/uv.lock
COPY api/requirements.txt /app/api/requirements.txt

# Install API deps (for shared db_models import)
RUN pip install --no-cache-dir -r /app/api/requirements.txt

# Copy source
COPY scraper /app/scraper
COPY api /app/api

WORKDIR /app/scraper

# Install scraper in editable mode (includes Celery)
RUN uv pip install --system -e .

ENV PYTHONPATH="/app/api:/app/scraper:${PYTHONPATH}"

CMD ["celery", "-A", "bets_scraper.celery_app.app", "worker", "--loglevel=info", "--queues=bets-scraper"]


