"""Authentication, authorization, CSRF and secret encryption."""
from __future__ import annotations

import functools
import hmac
import json
import secrets

from cryptography.fernet import Fernet, InvalidToken
from werkzeug.security import check_password_hash, generate_password_hash
from flask import current_app, g, jsonify, request, session

from .db import query_one

ROLES = ["viewer", "supervisor", "admin", "owner"]  # ascending privilege


# ------------------------------------------------------------ passwords
# PBKDF2-SHA256, 600k iterations (OWASP recommendation). Werkzeug's default is scrypt, but
# hashlib.scrypt is missing on Pythons built against LibreSSL (e.g. macOS's system Python 3.9),
# and a hash must verify on every machine that may run the app. check_password() accepts any
# werkzeug hash, so hashes created with another method keep working.
PASSWORD_METHOD = "pbkdf2:sha256:600000"


def hash_password(password: str) -> str:
    return generate_password_hash(password, method=PASSWORD_METHOD)


def check_password(stored_hash: str, password: str) -> bool:
    return check_password_hash(stored_hash, password)


# ------------------------------------------------------------ encryption
def _fernet() -> Fernet:
    key = current_app.config["ENCRYPTION_KEY"]
    if not key:
        key_file = current_app.config["INSTANCE_DIR"] / "encryption.key"
        if not key_file.exists():
            if not current_app.debug and not current_app.testing:
                current_app.logger.warning(
                    "ENCRYPTION_KEY not set: generating %s. Set ENCRYPTION_KEY in production.", key_file
                )
            key_file.parent.mkdir(parents=True, exist_ok=True)
            key_file.write_bytes(Fernet.generate_key())
        key = key_file.read_bytes().decode()
        current_app.config["ENCRYPTION_KEY"] = key
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        current_app.logger.error("Could not decrypt a stored secret: was ENCRYPTION_KEY rotated?")
        return ""


def encrypt_json(obj: dict) -> str:
    return encrypt(json.dumps(obj))


def decrypt_json(token: str) -> dict:
    raw = decrypt(token)
    return json.loads(raw) if raw else {}


# ------------------------------------------------------------ session / user
def load_user():
    """Populate g.user / g.workspace_id for the request (None when logged out)."""
    g.user = None
    uid = session.get("uid")
    if uid:
        user = query_one("SELECT id, workspace_id, email, name, role FROM users WHERE id = ?", [uid])
        if user:
            g.user = user
            g.workspace_id = user["workspace_id"]


def has_role(minimum: str) -> bool:
    return bool(g.user) and ROLES.index(g.user["role"]) >= ROLES.index(minimum)


def login_required(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        if not g.user:
            return jsonify(error="not_authenticated"), 401
        return view(*a, **kw)

    return wrapped


def role_required(minimum: str):
    def deco(view):
        @functools.wraps(view)
        @login_required
        def wrapped(*a, **kw):
            if not has_role(minimum):
                return jsonify(error="forbidden", required_role=minimum), 403
            return view(*a, **kw)

        return wrapped

    return deco


# ------------------------------------------------------------ CSRF
def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def check_csrf():
    """Mutating /api requests from the browser must echo the session token.

    Webhooks live under /webhooks and authenticate differently (secret path
    token or provider signature), so they are excluded.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if not request.path.startswith("/api/"):
        return
    if request.path in ("/api/auth/login", "/api/auth/register"):
        return
    sent = request.headers.get("X-CSRF-Token", "")
    if not sent or not hmac.compare_digest(sent, session.get("csrf", "")):
        return jsonify(error="csrf_failed"), 400
    return None
