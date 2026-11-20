"""WSGI entry point: `gunicorn wsgi:app` (production) or `flask --app wsgi run` (dev)."""
from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402

app = create_app()
