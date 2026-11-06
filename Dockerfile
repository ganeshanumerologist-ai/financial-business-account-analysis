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
# Set ARTHIVIO_SEED_DEMO=0 on a real deployment so the first-run /setup page
# creates the owner and the first real business instead of demo books.
CMD ["sh", "-c", "if [ \"${ARTHIVIO_SEED_DEMO:-1}\" != \"0\" ]; then python scripts/seed_demo.py; fi; exec python -m app.server"]
