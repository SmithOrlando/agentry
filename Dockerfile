FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/agentry.db UPLOAD_DIR=/data/uploads INSTANCE_DIR=/data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home --uid 10001 agentry && mkdir -p /data && chown -R agentry /data
USER agentry
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

# ONE worker process on purpose: background jobs run in an in-process thread pool
# and the database is SQLite. Scale with --threads, not --workers (docs/MAINTENANCE.md).
CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "16", "--timeout", "120", "--access-logfile", "-"]
