"""Background job runner.

`enqueue(fn, *args)` runs `fn` outside the HTTP request, inside an app context
with its own DB connection. Two modes (WORKER_MODE):

* thread (default) – a fixed in-process thread pool. Fine for one web process.
* sync             – run inline; used by tests.

Jobs must be idempotent: a crash mid-job loses it (no persistence). For
multi-process / multi-server deployments replace this module with RQ or Celery
(same `enqueue` signature) — see docs/MAINTENANCE.md › "Scaling the worker".
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, current_app

log = logging.getLogger(__name__)
_pool: ThreadPoolExecutor | None = None
_app: Flask | None = None


def init_worker(app: Flask) -> None:
    global _pool, _app
    _app = app
    if app.config["WORKER_MODE"] == "thread" and _pool is None:
        _pool = ThreadPoolExecutor(max_workers=app.config["WORKER_THREADS"], thread_name_prefix="agentry-job")


def _run(fn, args, kwargs):
    app = _app or current_app._get_current_object()
    with app.app_context():
        try:
            fn(*args, **kwargs)
        except Exception:
            log.exception("background job %s failed", getattr(fn, "__name__", fn))


def enqueue(fn, *args, **kwargs) -> None:
    app = _app or current_app._get_current_object()
    if app.config["WORKER_MODE"] == "sync" or _pool is None:
        _run(fn, args, kwargs)
    else:
        _pool.submit(_run, fn, args, kwargs)
