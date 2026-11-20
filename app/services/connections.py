"""WhatsApp connections (numbers) and their adapters."""
from __future__ import annotations

import re
import secrets

from flask import current_app

from ..db import execute, insert, query, query_one, update, utcnow
from ..security import decrypt_json, encrypt_json
from ..whatsapp.adapters import ADAPTERS, Adapter, WhatsAppError

REQUIRED = {
    "evolution": ["server_url", "api_key"],
    "meta_cloud": ["phone_number_id", "access_token", "app_secret", "verify_token"],
    "generic": ["send_url"],
    "sandbox": [],
}


def public(conn: dict) -> dict:
    """Connection as returned by the API: no secrets."""
    keep = ("id", "name", "provider", "phone_number", "account_name", "profile_picture", "status", "status_detail",
            "default_agent_id", "default_mode", "last_event_at", "created_at")
    out = {k: conn[k] for k in keep}
    out["webhook_url"] = webhook_url(conn)
    return out


def webhook_url(conn: dict) -> str:
    base = current_app.config["PUBLIC_BASE_URL"]
    if conn["provider"] == "meta_cloud":
        return f"{base}/webhooks/meta/{conn['id']}"
    return f"{base}/webhooks/{conn['provider']}/{conn['id']}/{conn['webhook_token']}"


def list_connections(workspace_id: int) -> list[dict]:
    rows = query("SELECT * FROM wa_connections WHERE workspace_id = ? ORDER BY id", [workspace_id])
    out = []
    for r in rows:
        p = public(r)
        last = query_one("SELECT MAX(m.created_at) AS t FROM messages m JOIN chats c ON c.id = m.chat_id "
                         "WHERE c.connection_id = ?", [r["id"]])
        p["last_message_at"] = last["t"] if last else None
        out.append(p)
    return out


def get(workspace_id: int, conn_id: int) -> dict | None:
    return query_one("SELECT * FROM wa_connections WHERE id = ? AND workspace_id = ?", [conn_id, workspace_id])


def adapter_for(conn: dict) -> Adapter:
    cfg = decrypt_json(conn["config_enc"]) if conn["config_enc"] else {}
    if conn["provider"] == "meta_cloud":
        cfg.setdefault("graph_version", current_app.config["META_GRAPH_VERSION"])
    return ADAPTERS[conn["provider"]](cfg, current_app.config["WHATSAPP_HTTP_TIMEOUT"])


def create(workspace_id: int, name: str, provider: str, config: dict, phone_number: str = "") -> dict:
    if provider not in ADAPTERS or (provider == "sandbox" and not current_app.config.get("ENABLE_TEST_TOOLS")):
        raise ValueError("unknown provider")
    missing = [k for k in REQUIRED[provider] if not str(config.get(k, "")).strip()]
    if missing:
        raise ValueError("missing: " + ", ".join(missing))
    if provider == "evolution":
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "number"
        config["instance"] = config.get("instance") or f"agentry-{workspace_id}-{slug}-{secrets.token_hex(3)}"
    cid = insert("wa_connections", {
        "workspace_id": workspace_id, "name": name.strip() or "WhatsApp number", "provider": provider,
        "phone_number": phone_number, "config_enc": encrypt_json(config),
        "webhook_token": secrets.token_urlsafe(24),
        "status": "connected" if provider in ("sandbox", "generic") else "pending",
        "created_at": utcnow()})
    conn = get(workspace_id, cid)
    if provider == "evolution":
        try:
            info = adapter_for(conn).setup(webhook_url(conn))
            return {**public(conn), **info}
        except WhatsAppError as exc:
            update("wa_connections", cid, {"status": "error", "status_detail": str(exc)[:300]})
            conn = get(workspace_id, cid)
    return public(conn)


def save_profile(conn_id: int, phone: str = "", account: str = "", picture: str = "") -> None:
    """Remember which WhatsApp account is linked (shown on the number's card)."""
    patch = {}
    if phone:
        patch["phone_number"] = "+" + phone
    if account:
        patch["account_name"] = account[:80]
    if picture:
        patch["profile_picture"] = picture[:500]
    if patch:
        update("wa_connections", conn_id, patch)


def refresh_state(conn: dict) -> dict:
    try:
        adapter = adapter_for(conn)
        state = adapter.state()
        update("wa_connections", conn["id"], {"status": state, "status_detail": ""})
        if state == "connected" and (not conn["account_name"] or not conn["phone_number"]):
            try:
                save_profile(conn["id"], **adapter.profile())
            except WhatsAppError:
                pass  # details are a nice-to-have
    except WhatsAppError as exc:
        update("wa_connections", conn["id"], {"status": "error", "status_detail": str(exc)[:300]})
    return public(get(conn["workspace_id"], conn["id"]))


def set_status(conn_id: int, status: str, detail: str = "", phone: str = "", account: str = "", picture: str = "") -> None:
    if status == "disconnected":
        # A linked device that drops after being connected is an expired session.
        prev = query_one("SELECT status FROM wa_connections WHERE id = ?", [conn_id])
        if prev and prev["status"] == "connected":
            status = "expired"
    update("wa_connections", conn_id, {"status": status, "status_detail": detail, "last_event_at": utcnow()})
    if status == "connected":
        save_profile(conn_id, phone, account, picture)


def delete(workspace_id: int, conn_id: int) -> bool:
    """Remove a number and its chats. For Evolution this also unlinks the phone and deletes the
    instance on the Evolution server (best effort: removal from Agentry happens even if that fails)."""
    conn = get(workspace_id, conn_id)
    if not conn:
        return False
    try:
        adapter_for(conn).teardown()
    except Exception as exc:  # never block removal on the provider
        current_app.logger.info("teardown of connection %s failed: %s", conn_id, exc)
    execute("DELETE FROM wa_connections WHERE id = ? AND workspace_id = ?", [conn_id, workspace_id])
    return True
