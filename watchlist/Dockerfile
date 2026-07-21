# Portable image for the watchlist bot — run on any container host (Fly.io, etc.).
# From the repo root:  docker build -f watchlist/Dockerfile -t watchlist-bot .
FROM python:3.12-slim

WORKDIR /app

# Only the deps the bot actually needs at runtime.
RUN pip install --no-cache-dir requests cloudscraper

# The bot imports from the pipeline package, so copy both.
COPY pipeline/ ./pipeline/
COPY watchlist/ ./watchlist/

# Persist the subscriber list outside the image (mount a volume at /data).
ENV SUBSCRIBERS_FILE=/data/subscribers.json
VOLUME ["/data"]

CMD ["python", "-m", "watchlist", "bot"]
