"""Agentry — build AI agents that answer WhatsApp chats.

create_app() wires config, database, auth hooks, blueprints and the worker.
"""
from __future__ import annotations

import logging
from datetime import timedelta

import click
from flask import Flask, jsonify

from .config import Config


def create_app(config_object=Config, **overrides) -> Flask:
    # static_folder=None: this app serves no files; the Vue frontend is built and served separately.
    app = Flask(__name__, instance_relative_config=False, static_folder=None)
    app.config.from_object(config_object)
    app.config.update(overrides)
    app.permanent_session_lifetime = timedelta(days=14)
    logging.basicConfig(level=app.config["LOG_LEVEL"],
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    from .db import close_db, migrate
    app.config["INSTANCE_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)
    applied = migrate(app.config["DATABASE_PATH"])
    if applied:
        app.logger.info("applied migrations: %s", ", ".join(applied))
    app.teardown_appcontext(close_db)

    from .security import check_csrf, load_user

    @app.before_request
    def _before():
        load_user()
        return check_csrf()

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    @app.errorhandler(413)
    def _too_big(_e):
        return jsonify(error=f"File too large (max {app.config['MAX_CONTENT_LENGTH'] // 1024 // 1024} MB)"), 413

    @app.errorhandler(404)
    def _nf(_e):
        return jsonify(error="not_found"), 404

    @app.errorhandler(405)
    def _na(_e):
        return jsonify(error="method_not_allowed"), 405

    @app.get("/")
    def root():
        # The UI is the separate Vue app (frontend/). This process only serves the API.
        return jsonify(service="agentry-api", docs="see docs/API.md", health="/healthz")

    @app.get("/healthz")
    def healthz():
        from .db import query_one
        query_one("SELECT 1 AS ok")
        return jsonify(status="ok")

    from . import api, webhooks
    app.register_blueprint(api.bp)
    app.register_blueprint(webhooks.bp)

    from .worker import init_worker
    init_worker(app)
    _register_cli(app)
    return app


def _register_cli(app: Flask) -> None:
    @app.cli.command("purge")
    def purge():
        """Delete messages older than each workspace's retention setting."""
        from .db import query
        from .services.conversations import purge_old_messages
        total = sum(purge_old_messages(w["id"]) for w in query("SELECT id FROM workspaces"))
        click.echo(f"deleted {total} messages")

    @app.cli.command("reindex")
    def reindex():
        """Re-index every knowledge file (e.g. after changing chunk size)."""
        from .db import query
        from .services.knowledge import index_file
        for f in query("SELECT id FROM knowledge_files"):
            index_file(f["id"])
        click.echo("done")

    @app.cli.command("create-owner")
    @click.option("--email", required=True)
    @click.option("--password", required=True)
    @click.option("--workspace", default="My workspace")
    def create_owner(email, password, workspace):
        """Create a workspace + owner without the web form (registration closed)."""
        with app.test_request_context():
            app.config["ALLOW_REGISTRATION"] = True
            client = app.test_client()
            r = client.post("/api/auth/register", json={"email": email, "password": password, "workspace": workspace})
            click.echo(r.get_json())
