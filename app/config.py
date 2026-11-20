"""Runtime configuration, read once from environment variables.

Every setting has a safe development default. See docs/CONFIGURATION.md
for the full table and production recommendations.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # --- core -------------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")
    INSTANCE_DIR = Path(os.environ.get("INSTANCE_DIR", BASE_DIR / "instance"))
    DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", INSTANCE_DIR / "agentry.db"))
    UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", INSTANCE_DIR / "uploads"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "20")) * 1024 * 1024
    # Public URL WhatsApp providers use to reach our webhooks.
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:5001").rstrip("/")
    # Where people open the Vue app (used in invite links). Same origin as the API in
    # production (nginx serves both); the Vite dev server in development.
    FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    # Fernet key (urlsafe base64, 32 bytes) for encrypting API keys/tokens at rest.
    # If unset in development a key is generated into INSTANCE_DIR/encryption.key.
    ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")
    ALLOW_REGISTRATION = _bool("ALLOW_REGISTRATION", True)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    # --- hidden platform default LLM (never exposed to users) --------------
    # Empty = no platform model: each workspace must add its own key (Settings › Models).
    PLATFORM_LLM_PROVIDER = os.environ.get("PLATFORM_LLM_PROVIDER", "")
    PLATFORM_LLM_MODEL = os.environ.get("PLATFORM_LLM_MODEL", "")
    PLATFORM_LLM_API_KEY = os.environ.get("PLATFORM_LLM_API_KEY", "")
    PLATFORM_LLM_BASE_URL = os.environ.get("PLATFORM_LLM_BASE_URL", "")
    LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))

    # --- WhatsApp -----------------------------------------------------------
    META_GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v24.0")
    WHATSAPP_HTTP_TIMEOUT = int(os.environ.get("WHATSAPP_HTTP_TIMEOUT", "20"))
    # Disable the human-like reply delay (tests, local dev).
    REPLY_DELAYS_ENABLED = _bool("REPLY_DELAYS_ENABLED", True)

    # --- background worker --------------------------------------------------
    WORKER_THREADS = int(os.environ.get("WORKER_THREADS", "4"))
    # "thread" runs jobs in-process; "sync" runs them inline (tests).
    WORKER_MODE = os.environ.get("WORKER_MODE", "thread")

    # --- knowledge ----------------------------------------------------------
    CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "900"))
    CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "120"))
    RETRIEVAL_TOP_K = int(os.environ.get("RETRIEVAL_TOP_K", "4"))
    ALLOW_PRIVATE_URL_FETCH = _bool("ALLOW_PRIVATE_URL_FETCH", False)

    # --- testing tools ------------------------------------------------------
    # Sandbox numbers, the Simulate button and the placeholder ("mock") model. Off in production;
    # the automated tests turn them on. Never enable on a public server.
    ENABLE_TEST_TOOLS = _bool("ENABLE_TEST_TOOLS", False)


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test"
    WORKER_MODE = "sync"
    REPLY_DELAYS_ENABLED = False
    PLATFORM_LLM_PROVIDER = "mock"
    PLATFORM_LLM_MODEL = "mock-1"
    ENABLE_TEST_TOOLS = True
