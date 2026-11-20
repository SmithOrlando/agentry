"""Database access: SQLite connection per request/thread + SQL migrations.

The SQL is deliberately plain (no SQLite-only features beyond what Postgres
also supports, except `INSERT OR IGNORE`, which is isolated in helpers) so the
project can move to Postgres later. See docs/MAINTENANCE.md › "Moving to Postgres".
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from flask import current_app, g

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_local = threading.local()


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def get_db() -> sqlite3.Connection:
    """Connection for the current request, or for the current worker thread."""
    try:
        if "db" not in g:
            g.db = _connect(current_app.config["DATABASE_PATH"])
        return g.db
    except RuntimeError:  # outside app context -> should not happen; be explicit
        raise RuntimeError("get_db() needs an app context")


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---------------------------------------------------------------- helpers
def query(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    return [dict(r) for r in get_db().execute(sql, tuple(params)).fetchall()]


def query_one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    row = get_db().execute(sql, tuple(params)).fetchone()
    return dict(row) if row else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Run a write and commit. Returns lastrowid."""
    db = get_db()
    cur = db.execute(sql, tuple(params))
    db.commit()
    return cur.lastrowid


def insert(table: str, data: dict) -> int:
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    return execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", data.values())


def update(table: str, row_id: int, data: dict) -> None:
    if not data:
        return
    sets = ", ".join(f"{k} = ?" for k in data)
    execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*data.values(), row_id])


def jdump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def jload(raw, default=None):
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- migrations
def migrate(db_path: Path) -> list[str]:
    """Apply every migrations/NNN_*.sql not yet recorded. Idempotent."""
    conn = _connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        applied = []
        for file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = file.stem
            if version in done:
                continue
            conn.executescript(file.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, utcnow()),
            )
            conn.commit()
            applied.append(version)
        return applied
    finally:
        conn.close()
