"""Inbound webhooks from WhatsApp providers.

Rules: authenticate, store, enqueue, return 200 fast. Never call the LLM here.
  Evolution / generic / sandbox:  POST /webhooks/<provider>/<conn_id>/<secret token>
  Meta Cloud API:                 GET  /webhooks/meta/<conn_id>   (verify handshake)
                                  POST /webhooks/meta/<conn_id>   (X-Hub-Signature-256)
"""
import hmac

from flask import Blueprint, abort, current_app, jsonify, request

from .db import query_one
from .services import connections as csvc
from .services.conversations import handle_inbound
from .whatsapp.adapters import ConnectionUpdate, Inbound

bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")


def _dispatch(conn, events):
    handled = 0
    for ev in events:
        if isinstance(ev, Inbound):
            if handle_inbound(conn, ev):
                handled += 1
        elif isinstance(ev, ConnectionUpdate):
            csvc.set_status(conn["id"], ev.status, ev.detail)
    return handled


@bp.post("/<provider>/<int:conn_id>/<token>")
def token_webhook(provider, conn_id, token):
    if provider not in ("evolution", "generic", "sandbox") or (provider == "sandbox" and not current_app.config.get("ENABLE_TEST_TOOLS")):
        abort(404)
    conn = query_one("SELECT * FROM wa_connections WHERE id = ? AND provider = ?", [conn_id, provider])
    if not conn or not hmac.compare_digest(conn["webhook_token"], token):
        abort(404)  # do not reveal whether the connection exists
    payload = request.get_json(silent=True) or {}
    try:
        n = _dispatch(conn, csvc.adapter_for(conn).parse_webhook(payload))
    except Exception:
        current_app.logger.exception("webhook processing failed for connection %s", conn_id)
        return jsonify(ok=False), 200  # 200 so the provider does not retry-storm; error is logged
    return jsonify(ok=True, handled=n)


@bp.get("/meta/<int:conn_id>")
def meta_verify(conn_id):
    conn = query_one("SELECT * FROM wa_connections WHERE id = ? AND provider = 'meta_cloud'", [conn_id])
    if not conn:
        abort(404)
    cfg = csvc.adapter_for(conn).config
    if (request.args.get("hub.mode") == "subscribe"
            and hmac.compare_digest(request.args.get("hub.verify_token", ""), cfg.get("verify_token", ""))):
        csvc.set_status(conn_id, "connected", "")
        return request.args.get("hub.challenge", ""), 200, {"Content-Type": "text/plain"}
    abort(403)


@bp.post("/meta/<int:conn_id>")
def meta_receive(conn_id):
    conn = query_one("SELECT * FROM wa_connections WHERE id = ? AND provider = 'meta_cloud'", [conn_id])
    if not conn:
        abort(404)
    adapter = csvc.adapter_for(conn)
    if not adapter.verify_signature(request.get_data(), request.headers.get("X-Hub-Signature-256", "")):
        abort(401)
    try:
        n = _dispatch(conn, adapter.parse_webhook(request.get_json(silent=True) or {}))
    except Exception:
        current_app.logger.exception("meta webhook failed for connection %s", conn_id)
        return jsonify(ok=False), 200
    return jsonify(ok=True, handled=n)
