from flask import g, jsonify

from ..db import execute, insert, jdump, jload, query, query_one, utcnow
from ..llm import router
from ..llm.providers import LLMError
from ..security import role_required
from ..services import agents as agents_svc
from . import body, bp, err, ws


@bp.get("/playground/sessions")
@role_required("supervisor")
def pg_sessions():
    rows = query("SELECT id, title, agent_id, updated_at FROM playground_sessions "
                 "WHERE workspace_id = ? AND user_id = ? ORDER BY updated_at DESC LIMIT 30", [ws(), g.user["id"]])
    return jsonify(sessions=rows)


@bp.post("/playground/sessions")
@role_required("supervisor")
def pg_new():
    d = body()
    agent = agents_svc.get_agent(ws(), d.get("agent_id"))
    now = utcnow()
    sid = insert("playground_sessions", {"workspace_id": ws(), "user_id": g.user["id"],
                                         "agent_id": agent["id"] if agent else None, "title": "New chat",
                                         "created_at": now, "updated_at": now})
    return jsonify(id=sid), 201


def _session(sid):
    return query_one("SELECT * FROM playground_sessions WHERE id = ? AND workspace_id = ? AND user_id = ?",
                     [sid, ws(), g.user["id"]])


@bp.get("/playground/sessions/<int:sid>")
@role_required("supervisor")
def pg_get(sid):
    s = _session(sid)
    if not s:
        return err("not found", 404)
    msgs = query("SELECT id, role, text, sources, meta, created_at FROM playground_messages "
                 "WHERE session_id = ? ORDER BY id", [sid])
    for m in msgs:
        m["sources"], m["meta"] = jload(m["sources"], []), jload(m["meta"], {})
    return jsonify(session=s, messages=msgs)


@bp.delete("/playground/sessions/<int:sid>")
@role_required("supervisor")
def pg_delete(sid):
    if not _session(sid):
        return err("not found", 404)
    execute("DELETE FROM playground_sessions WHERE id = ?", [sid])
    return jsonify(ok=True)


@bp.post("/playground/sessions/<int:sid>/messages")
@role_required("supervisor")
def pg_send(sid):
    s = _session(sid)
    if not s:
        return err("not found", 404)
    d = body()
    text = (d.get("text") or "").strip()
    if not text:
        return err("Message is empty")
    agent = agents_svc.get_agent(ws(), d.get("agent_id") or s["agent_id"])
    use_knowledge = d.get("use_knowledge", True)
    history = [{"role": m["role"], "content": m["text"]} for m in
               query("SELECT role, text FROM playground_messages WHERE session_id = ? ORDER BY id DESC LIMIT 12", [sid])][::-1]
    now = utcnow()
    insert("playground_messages", {"session_id": sid, "role": "user", "text": text, "created_at": now})
    if s["title"] == "New chat":
        execute("UPDATE playground_sessions SET title = ? WHERE id = ?", [text[:60], sid])
    messages, sources = agents_svc.build_messages(ws(), agent, history, text, channel="playground",
                                                  use_knowledge=bool(use_knowledge))
    try:
        result = router.generate(ws(), agent, messages)
    except LLMError as exc:
        return err(f"The model could not answer: {exc}", 502)
    meta = {"model": "Platform default" if result.provider == "platform" else f"{result.provider} · {result.model}",
            "agent": agent["name"] if agent else None}
    mid = insert("playground_messages", {"session_id": sid, "role": "assistant", "text": result.text,
                                         "sources": jdump(sources), "meta": jdump(meta), "created_at": utcnow()})
    execute("UPDATE playground_sessions SET updated_at = ?, agent_id = ? WHERE id = ?",
            [utcnow(), agent["id"] if agent else None, sid])
    return jsonify(id=mid, role="assistant", text=result.text, sources=sources, meta=meta)
