import secrets
from datetime import datetime, timezone

from flask import current_app, g, jsonify

from ..db import execute, get_db, insert, query, query_one, update, utcnow
from ..llm import router
from ..llm.providers import PROVIDER_LABELS, PROVIDERS, LLMError
from ..security import encrypt, role_required
from ..services import settings as ssvc
from ..services.connections import list_connections
from . import body, bp, err, ws


# ------------------------------------------------------------- general
@bp.get("/settings/general")
@role_required("viewer")
def general_get():
    w = ssvc.get_workspace(ws())
    return jsonify({k: w[k] for k in ("name", "default_language", "timezone", "away_message", "business_hours")})


@bp.patch("/settings/general")
@role_required("admin")
def general_patch():
    w = ssvc.update_general(ws(), body())
    ssvc.audit(ws(), g.user["id"], "updated general settings")
    return jsonify({k: w[k] for k in ("name", "default_language", "timezone", "away_message", "business_hours")})


@bp.delete("/settings/workspace")
@role_required("owner")
def workspace_delete():
    if (body().get("confirm") or "") != "DELETE":
        return err('Type DELETE to confirm')
    execute("DELETE FROM workspaces WHERE id = ?", [ws()])
    return jsonify(ok=True)


# ------------------------------------------------------------- generic JSON sections
SECTIONS = {"whatsapp": "whatsapp_settings", "agent-defaults": "agent_defaults", "security": "security_settings"}


@bp.get("/settings/<section>")
@role_required("viewer")
def section_get(section):
    if section not in SECTIONS:
        return err("unknown section", 404)
    return jsonify(ssvc.get_section(ws(), SECTIONS[section]))


@bp.patch("/settings/<section>")
@role_required("admin")
def section_patch(section):
    if section not in SECTIONS:
        return err("unknown section", 404)
    out = ssvc.update_section(ws(), SECTIONS[section], body())
    ssvc.audit(ws(), g.user["id"], f"updated {section} settings")
    return jsonify(out)


# ------------------------------------------------------------- models & keys
@bp.get("/settings/llm")
@role_required("viewer")
def llm_get():
    keys = {r["provider"]: r for r in query(
        "SELECT provider, last4, base_url, verified_at FROM provider_keys WHERE workspace_id = ?", [ws()])}
    providers = [{"id": p, "label": PROVIDER_LABELS[p], "connected": p in keys,
                  "last4": keys.get(p, {}).get("last4"), "base_url": keys.get(p, {}).get("base_url", ""),
                  "verified_at": keys.get(p, {}).get("verified_at")} for p in PROVIDERS]
    return jsonify(settings=ssvc.get_section(ws(), "llm_settings"), providers=providers,
                   active_model=router.describe_active_model(ws(), None))


@bp.patch("/settings/llm")
@role_required("admin")
def llm_patch():
    d = body()
    if "source" in d and d["source"] not in ("platform", "byok"):
        return err("source must be platform or byok")
    if "temperature" in d:
        d["temperature"] = max(0.0, min(1.0, float(d["temperature"])))
    if "max_tokens" in d:
        d["max_tokens"] = max(50, min(4000, int(d["max_tokens"])))
    out = ssvc.update_section(ws(), "llm_settings", d)
    ssvc.audit(ws(), g.user["id"], "updated model settings")
    return jsonify(settings=out)


@bp.put("/settings/providers/<provider>")
@role_required("admin")
def provider_put(provider):
    if provider not in PROVIDERS:
        return err("unknown provider", 404)
    d = body()
    key = (d.get("api_key") or "").strip()
    base_url = (d.get("base_url") or "").strip()
    existing = query_one("SELECT id FROM provider_keys WHERE workspace_id = ? AND provider = ?", [ws(), provider])
    if existing:
        patch = {"base_url": base_url}
        if key:
            patch.update(api_key_enc=encrypt(key), last4=key[-4:], verified_at=None)
        update("provider_keys", existing["id"], patch)
    else:
        if not key:
            return err("API key is required")
        insert("provider_keys", {"workspace_id": ws(), "provider": provider, "api_key_enc": encrypt(key),
                                 "last4": key[-4:], "base_url": base_url, "created_at": utcnow()})
    ssvc.audit(ws(), g.user["id"], "saved API key", PROVIDER_LABELS[provider])
    # First real key while replies still come from the placeholder model: start using this key right away.
    # (Otherwise the workspace stays on "Platform default" and nothing visibly changes.)
    if not router.model_ready(ws()):
        cur = ssvc.get_section(ws(), "llm_settings")
        model = cur["model"] if cur["provider"] == provider and cur["model"] else router.STARTER_MODEL.get(provider, "")
        settings = ssvc.update_section(ws(), "llm_settings", {"source": "byok", "provider": provider, "model": model})
        ssvc.audit(ws(), g.user["id"], "switched to own API key", PROVIDER_LABELS[provider])
        return jsonify(ok=True, switched=True, settings=settings)
    return jsonify(ok=True, switched=False)


@bp.delete("/settings/providers/<provider>")
@role_required("admin")
def provider_delete(provider):
    execute("DELETE FROM provider_keys WHERE workspace_id = ? AND provider = ?", [ws(), provider])
    ssvc.audit(ws(), g.user["id"], "removed API key", PROVIDER_LABELS.get(provider, provider))
    return jsonify(ok=True)


@bp.post("/settings/providers/<provider>/test")
@role_required("admin")
def provider_test(provider):
    try:
        result = router.test_key(ws(), provider)
    except LLMError as exc:
        return err(str(exc), 502)
    # If this provider is the workspace model but no model name is set yet (custom endpoints), use the first one.
    llm = ssvc.get_section(ws(), "llm_settings")
    if llm["source"] == "byok" and llm["provider"] == provider and not llm["model"] and result.get("models"):
        ssvc.update_section(ws(), "llm_settings", {"model": result["models"][0]})
        result["model_selected"] = result["models"][0]
    return jsonify(result)


# ------------------------------------------------------------- team
@bp.get("/team")
@role_required("viewer")
def team_get():
    members = query("SELECT id, name, email, role, last_active_at FROM users WHERE workspace_id = ? ORDER BY id", [ws()])
    invites = query("SELECT id, email, role, created_at FROM invites WHERE workspace_id = ? AND accepted_at IS NULL",
                    [ws()])
    return jsonify(members=members, invites=invites, me=g.user["id"])


@bp.post("/team/invites")
@role_required("admin")
def team_invite():
    d = body()
    role = d.get("role") or "supervisor"
    if role not in ("admin", "supervisor", "viewer"):
        return err("invalid role")
    out = []
    for email in [e.strip().lower() for e in str(d.get("emails") or "").replace(";", ",").split(",") if e.strip()]:
        if "@" not in email:
            continue
        token = secrets.token_urlsafe(24)
        get_db().execute("INSERT OR REPLACE INTO invites (workspace_id, email, role, token, invited_by, created_at) "
                         "VALUES (?,?,?,?,?,?)", [ws(), email, role, token, g.user["id"], utcnow()])
        get_db().commit()
        # No email service is wired yet: return the link so an admin can share it.
        out.append({"email": email, "link": f"{current_app.config['FRONTEND_URL']}/register?invite={token}"})
    if not out:
        return err("Enter at least one email address")
    ssvc.audit(ws(), g.user["id"], "invited", ", ".join(o["email"] for o in out))
    return jsonify(invites=out), 201


@bp.delete("/team/invites/<int:iid>")
@role_required("admin")
def team_revoke(iid):
    execute("DELETE FROM invites WHERE id = ? AND workspace_id = ?", [iid, ws()])
    return jsonify(ok=True)


@bp.patch("/team/members/<int:uid>")
@role_required("admin")
def team_role(uid):
    role = body().get("role")
    target = query_one("SELECT * FROM users WHERE id = ? AND workspace_id = ?", [uid, ws()])
    if not target or role not in ("admin", "supervisor", "viewer"):
        return err("invalid member or role")
    if target["role"] == "owner":
        return err("The owner's role can't be changed", 403)
    update("users", uid, {"role": role})
    ssvc.audit(ws(), g.user["id"], "changed role", f"{target['email']} → {role}")
    return jsonify(ok=True)


@bp.delete("/team/members/<int:uid>")
@role_required("admin")
def team_remove(uid):
    target = query_one("SELECT * FROM users WHERE id = ? AND workspace_id = ?", [uid, ws()])
    if not target or target["role"] == "owner" or uid == g.user["id"]:
        return err("This member can't be removed", 403)
    execute("DELETE FROM users WHERE id = ?", [uid])
    ssvc.audit(ws(), g.user["id"], "removed member", target["email"])
    return jsonify(ok=True)


# ------------------------------------------------------------- usage & audit
@bp.get("/usage")
@role_required("viewer")
def usage():
    start = datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00Z")
    rows = query("SELECT kind, SUM(amount) AS total FROM usage_events WHERE workspace_id = ? AND created_at >= ? "
                 "GROUP BY kind", [ws(), start])
    totals = {r["kind"]: r["total"] for r in rows}
    storage = query_one("SELECT COALESCE(SUM(size_bytes),0) AS b FROM knowledge_files WHERE workspace_id = ?", [ws()])
    return jsonify(period_start=start, agent_replies=totals.get("agent_reply", 0),
                   platform_tokens=totals.get("platform_tokens", 0), byok_tokens=totals.get("byok_tokens", 0),
                   storage_bytes=storage["b"], numbers=len(list_connections(ws())))


@bp.get("/audit")
@role_required("admin")
def audit_list():
    rows = query("SELECT a.action, a.target, a.created_at, u.name AS user_name FROM audit_log a "
                 "LEFT JOIN users u ON u.id = a.user_id WHERE a.workspace_id = ? ORDER BY a.id DESC LIMIT 100", [ws()])
    return jsonify(entries=rows)


@bp.get("/export")
@role_required("admin")
def export():
    """Everything a workspace owns, as one JSON download (secrets excluded)."""
    w = ssvc.get_workspace(ws())
    chats = query("SELECT c.id, c.mode, c.agent_id, c.created_at, ct.wa_id, ct.name FROM chats c "
                  "JOIN contacts ct ON ct.id = c.contact_id WHERE c.workspace_id = ?", [ws()])
    for c in chats:
        c["messages"] = query("SELECT direction, author, text, status, created_at FROM messages "
                              "WHERE chat_id = ? ORDER BY id", [c["id"]])
    data = {"exported_at": utcnow(), "workspace": {k: w[k] for k in ("name", "default_language", "timezone")},
            "agents": query("SELECT name, description, instructions, active FROM agents WHERE workspace_id = ?", [ws()]),
            "knowledge_files": query("SELECT filename, kind, status, chunk_count, created_at FROM knowledge_files "
                                     "WHERE workspace_id = ?", [ws()]),
            "contacts": query("SELECT wa_id, name, tags, opted_out, created_at FROM contacts WHERE workspace_id = ?", [ws()]),
            "chats": chats}
    ssvc.audit(ws(), g.user["id"], "exported data")
    resp = jsonify(data)
    resp.headers["Content-Disposition"] = "attachment; filename=agentry-export.json"
    return resp
