from flask import g, jsonify, request

from ..db import execute, jdump, jload, query, query_one, update
from ..security import role_required
from ..services import conversations as conv
from ..services.conversations import DEFAULT_RULES
from ..services.settings import audit
from . import body, bp, err, ws


@bp.get("/inbox/chats")
@role_required("viewer")
def chats():
    f = request.args.get("filter", "all")
    sql = ("SELECT c.id, c.mode, c.agent_id, c.handoff_active, c.unread_count, c.last_message_at, "
           "c.last_message_preview, c.connection_id, ct.name AS contact_name, ct.wa_id, a.name AS agent_name, "
           "a.color AS agent_color, w.name AS connection_name, "
           "(SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id AND m.status = 'draft') AS drafts "
           "FROM chats c JOIN contacts ct ON ct.id = c.contact_id "
           "JOIN wa_connections w ON w.id = c.connection_id "
           "LEFT JOIN agents a ON a.id = c.agent_id WHERE c.workspace_id = ?")
    params = [ws()]
    if request.args.get("connection_id"):
        sql += " AND c.connection_id = ?"
        params.append(int(request.args["connection_id"]))
    if q := (request.args.get("q") or "").strip():
        sql += " AND (ct.name LIKE ? OR ct.wa_id LIKE ? OR c.last_message_preview LIKE ?)"
        params += [f"%{q}%"] * 3
    if f == "drafts":
        sql += " AND EXISTS (SELECT 1 FROM messages m WHERE m.chat_id = c.id AND m.status = 'draft')"
    elif f == "needs_you":
        sql += " AND c.handoff_active = 1"
    elif f == "unassigned":
        sql += " AND c.agent_id IS NULL"
    sql += " ORDER BY c.last_message_at DESC LIMIT 200"
    rows = query(sql, params)
    counts = query_one("SELECT "
                       "(SELECT COUNT(*) FROM chats WHERE workspace_id = ?) AS all_, "
                       "(SELECT COUNT(DISTINCT c.id) FROM chats c JOIN messages m ON m.chat_id = c.id "
                       " WHERE c.workspace_id = ? AND m.status = 'draft') AS drafts, "
                       "(SELECT COUNT(*) FROM chats WHERE workspace_id = ? AND handoff_active = 1) AS needs_you, "
                       "(SELECT COUNT(*) FROM chats WHERE workspace_id = ? AND unread_count > 0) AS unread",
                       [ws(), ws(), ws(), ws()])
    return jsonify(chats=rows, counts=counts)


def _chat(cid):
    return query_one("SELECT c.*, ct.name AS contact_name, ct.wa_id, ct.tags, ct.opted_out, ct.created_at AS contact_since, "
                     "w.name AS connection_name FROM chats c JOIN contacts ct ON ct.id = c.contact_id "
                     "JOIN wa_connections w ON w.id = c.connection_id WHERE c.id = ? AND c.workspace_id = ?",
                     [cid, ws()])


@bp.get("/inbox/chats/<int:cid>")
@role_required("viewer")
def chat_detail(cid):
    c = _chat(cid)
    if not c:
        return err("not found", 404)
    c["rules"] = {**DEFAULT_RULES, **jload(c["rules"], {})}
    c["tags"] = jload(c["tags"], [])
    msgs = query("SELECT m.id, m.direction, m.author, m.text, m.status, m.sources, m.error, m.created_at, "
                 "a.name AS agent_name, u.name AS user_name FROM messages m "
                 "LEFT JOIN agents a ON a.id = m.agent_id LEFT JOIN users u ON u.id = m.user_id "
                 "WHERE m.chat_id = ? AND m.status != 'discarded' ORDER BY m.id", [cid])
    for m in msgs:
        m["sources"] = jload(m["sources"], [])
    stats = query_one("SELECT SUM(author = 'agent' AND status = 'sent') AS agent_replies, "
                      "SUM(author = 'agent' AND status = 'sent' AND user_id IS NOT NULL) AS drafts_approved, "
                      "MIN(created_at) AS first_message FROM messages WHERE chat_id = ?", [cid])
    if c["unread_count"] and request.args.get("mark_read", "1") == "1":
        update("chats", cid, {"unread_count": 0})
    return jsonify(chat=c, messages=msgs, stats=stats)


@bp.patch("/inbox/chats/<int:cid>")
@role_required("supervisor")
def chat_update(cid):
    c = _chat(cid)
    if not c:
        return err("not found", 404)
    d = body()
    patch = {}
    if "agent_id" in d:
        if d["agent_id"] and not query_one("SELECT id FROM agents WHERE id = ? AND workspace_id = ?",
                                           [d["agent_id"], ws()]):
            return err("unknown agent")
        patch["agent_id"] = d["agent_id"] or None
    if d.get("mode") in ("auto", "draft", "off"):
        patch["mode"] = d["mode"]
    if isinstance(d.get("rules"), dict):
        rules = {**DEFAULT_RULES, **jload(c["rules"], {})}
        rules.update({k: bool(v) for k, v in d["rules"].items() if k in DEFAULT_RULES})
        patch["rules"] = jdump(rules)
    if isinstance(d.get("tags"), list):
        update("contacts", c["contact_id"], {"tags": jdump([str(t)[:30] for t in d["tags"]][:20])})
    update("chats", cid, patch)
    if d.get("apply_to_connection"):
        # Make these the defaults for new chats on this number, and apply to its existing chats.
        conn_patch, chat_patch = {}, {}
        if "mode" in patch:
            conn_patch["default_mode"] = chat_patch["mode"] = patch["mode"]
        if "agent_id" in patch:
            conn_patch["default_agent_id"] = chat_patch["agent_id"] = patch["agent_id"]
        update("wa_connections", c["connection_id"], conn_patch)
        for chat in query("SELECT id FROM chats WHERE connection_id = ?", [c["connection_id"]]):
            update("chats", chat["id"], chat_patch)
    return jsonify(ok=True)


def _guard(fn, *a):
    try:
        return fn(*a)
    except LookupError as exc:
        return err(str(exc), 404)


@bp.post("/inbox/chats/<int:cid>/messages")
@role_required("supervisor")
def chat_send(cid):
    text = (body().get("text") or "").strip()
    if not text:
        return err("Message is empty")
    r = _guard(conv.send_human, ws(), cid, g.user["id"], text)
    return r if isinstance(r, tuple) else (jsonify(id=r), 201)


@bp.post("/inbox/chats/<int:cid>/takeover")
@role_required("supervisor")
def chat_takeover(cid):
    r = _guard(conv.take_over, ws(), cid)
    return r if isinstance(r, tuple) else jsonify(ok=True)


@bp.post("/inbox/chats/<int:cid>/resume")
@role_required("supervisor")
def chat_resume(cid):
    r = _guard(conv.resume_agent, ws(), cid)
    return r if isinstance(r, tuple) else jsonify(ok=True)


@bp.post("/inbox/chats/<int:cid>/ask-agent")
@role_required("supervisor")
def chat_ask(cid):
    r = _guard(conv.ask_agent, ws(), cid)
    if isinstance(r, tuple):
        return r
    if r is None:
        return err("The agent could not reply (model error)", 502)
    return jsonify(id=r), 201


@bp.post("/inbox/messages/<int:mid>/approve")
@role_required("supervisor")
def draft_approve(mid):
    r = _guard(conv.approve_draft, ws(), mid, g.user["id"], body().get("text"))
    return r if isinstance(r, tuple) else jsonify(message=r)


@bp.post("/inbox/messages/<int:mid>/discard")
@role_required("supervisor")
def draft_discard(mid):
    r = _guard(conv.discard_draft, ws(), mid)
    return r if isinstance(r, tuple) else jsonify(ok=True)


@bp.delete("/inbox/chats/<int:cid>")
@role_required("supervisor")
def delete_chat(cid):
    """Delete a chat and its messages. The contact goes too if it has no other chats."""
    c = query_one("SELECT id, contact_id FROM chats WHERE id = ? AND workspace_id = ?", [cid, ws()])
    if not c:
        return err("not found", 404)
    execute("DELETE FROM chats WHERE id = ?", [cid])
    execute("DELETE FROM contacts WHERE id = ? AND NOT EXISTS (SELECT 1 FROM chats WHERE contact_id = ?)",
            [c["contact_id"], c["contact_id"]])
    audit(ws(), g.user["id"], "deleted chat", str(cid))
    return jsonify(ok=True)
