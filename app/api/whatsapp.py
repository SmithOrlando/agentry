from flask import current_app, g, jsonify

from ..db import update
from ..security import role_required
from ..services import connections as csvc
from ..services.conversations import handle_inbound
from ..services.settings import audit
from ..whatsapp.adapters import Inbound, WhatsAppError
from . import body, bp, err, ws


@bp.get("/whatsapp/connections")
@role_required("viewer")
def wa_list():
    return jsonify(connections=csvc.list_connections(ws()))


@bp.post("/whatsapp/connections")
@role_required("admin")
def wa_create():
    d = body()
    try:
        conn = csvc.create(ws(), d.get("name") or "", d.get("provider") or "", d.get("config") or {},
                           d.get("phone_number") or "")
    except ValueError as exc:
        return err(str(exc))
    audit(ws(), g.user["id"], "added WhatsApp number", conn["name"])
    return jsonify(connection=conn), 201


def _conn(cid):
    return csvc.get(ws(), cid)


@bp.get("/whatsapp/connections/<int:cid>/qr")
@role_required("admin")
def wa_qr(cid):
    conn = _conn(cid)
    if not conn:
        return err("not found", 404)
    if conn["provider"] != "evolution":
        return err("QR codes are only used by Evolution API connections")
    try:
        return jsonify(csvc.adapter_for(conn).qr())
    except WhatsAppError as exc:
        return err(str(exc), 502)


@bp.post("/whatsapp/connections/<int:cid>/refresh")
@role_required("viewer")
def wa_refresh(cid):
    conn = _conn(cid)
    if not conn:
        return err("not found", 404)
    return jsonify(connection=csvc.refresh_state(conn))


@bp.patch("/whatsapp/connections/<int:cid>")
@role_required("admin")
def wa_update(cid):
    conn = _conn(cid)
    if not conn:
        return err("not found", 404)
    d = body()
    patch = {}
    if "name" in d:
        patch["name"] = str(d["name"])[:80]
    if "phone_number" in d:
        patch["phone_number"] = str(d["phone_number"])[:30]
    if "default_agent_id" in d:
        patch["default_agent_id"] = d["default_agent_id"] or None
    if d.get("default_mode") in ("auto", "draft", "off", None):
        if "default_mode" in d:
            patch["default_mode"] = d["default_mode"]
    update("wa_connections", cid, patch)
    return jsonify(connection=csvc.public(_conn(cid)))


@bp.delete("/whatsapp/connections/<int:cid>")
@role_required("admin")
def wa_delete(cid):
    if not csvc.delete(ws(), cid):
        return err("not found", 404)
    audit(ws(), g.user["id"], "removed WhatsApp number", str(cid))
    return jsonify(ok=True)


@bp.post("/whatsapp/connections/<int:cid>/simulate")
@role_required("admin")
def wa_simulate(cid):
    """Inject an inbound message as if a customer sent it (testing without a phone). Test tools only."""
    if not current_app.config.get("ENABLE_TEST_TOOLS"):
        return err("not found", 404)
    conn = _conn(cid)
    if not conn:
        return err("not found", 404)
    d = body()
    if not (d.get("text") or "").strip():
        return err("text is required")
    import secrets
    mid = handle_inbound(conn, Inbound(str(d.get("from") or "10000000000"), d.get("name") or "Test customer",
                                       d["text"], f"sim-{secrets.token_hex(6)}"))
    return jsonify(message_id=mid), 201
