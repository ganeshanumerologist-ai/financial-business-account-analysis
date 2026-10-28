FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ARTHIVIO_HOST=0.0.0.0 \
    ARTHIVIO_DB=/app/data/arthivio.db

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Seed only when the database is empty. On an ephemeral host this recreates the
# synthetic demo books after a restart; on a persistent disk it is a no-op.
CMD ["sh", "-c", "python scripts/seed_demo.py && exec python -m app.server"]
