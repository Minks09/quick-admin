FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Zurich

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scraper ./scraper
COPY scripts ./scripts
COPY data/csv ./data/csv

RUN chmod +x scripts/start_web.sh \
    && useradd --create-home --uid 1000 politrace \
    && mkdir -p data/raw data/ig_out \
    && chown -R politrace:politrace /app
USER politrace

EXPOSE 8000
CMD ["./scripts/start_web.sh"]
