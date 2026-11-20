"""JSON API under /api. All routes are workspace-scoped through g.workspace_id."""
from flask import Blueprint, g, jsonify, request

bp = Blueprint("api", __name__, url_prefix="/api")


def body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def ws() -> int:
    return g.workspace_id


def err(message: str, status: int = 400, **extra):
    return jsonify(error=message, **extra), status


from . import auth, playground, agents, knowledge, whatsapp, inbox, settings  # noqa: E402,F401
