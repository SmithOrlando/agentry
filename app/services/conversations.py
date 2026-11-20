"""The routing engine: what happens when a WhatsApp message arrives.

handle_inbound()  is called by webhooks (fast path: store + enqueue).
respond()         runs in the worker: rules -> LLM -> send or draft.
approve_draft(), send_human(), take_over(), resume_agent() back the Inbox UI.

Order of checks for an inbound message (see docs/ARCHITECTURE.md › Reply pipeline):
  dedupe -> opt-out keyword -> contact opted out -> group filter -> mode off / no agent
  -> human handoff active -> handoff keyword -> business hours -> rate limit -> LLM
"""
from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import current_app

from ..db import execute, get_db, insert, jdump, jload, query, query_one, update, utcnow
from ..llm import router
from ..llm.providers import LLMError
from ..whatsapp.adapters import Inbound, WhatsAppError
from ..worker import enqueue
from . import agents as agents_svc
from . import connections as conn_svc
from .settings import get_section, get_workspace, record_usage

DEFAULT_RULES = {"handoff": True, "business_hours_only": False, "match_language": True}
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# ------------------------------------------------------------------ helpers
def _upsert_contact(workspace_id, wa_id, name) -> dict:
    get_db().execute("INSERT OR IGNORE INTO contacts (workspace_id, wa_id, name, created_at) VALUES (?,?,?,?)",
                     [workspace_id, wa_id, name or "", utcnow()])
    get_db().commit()
    c = query_one("SELECT * FROM contacts WHERE workspace_id = ? AND wa_id = ?", [workspace_id, wa_id])
    if name and not c["name"]:
        update("contacts", c["id"], {"name": name})
        c["name"] = name
    return c


def _upsert_chat(conn: dict, contact: dict) -> dict:
    wa = get_section(conn["workspace_id"], "whatsapp_settings")
    agent_id = conn["default_agent_id"] or wa["default_agent_id"]
    mode = conn["default_mode"] or wa["default_mode"]
    get_db().execute(
        "INSERT OR IGNORE INTO chats (workspace_id, connection_id, contact_id, agent_id, mode, rules, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        [conn["workspace_id"], conn["id"], contact["id"], agent_id, mode, jdump(DEFAULT_RULES), utcnow()])
    get_db().commit()
    return query_one("SELECT * FROM chats WHERE connection_id = ? AND contact_id = ?", [conn["id"], contact["id"]])


def add_message(chat_id, direction, author, text, status, **extra) -> int:
    now = utcnow()
    mid = insert("messages", {"chat_id": chat_id, "direction": direction, "author": author, "text": text,
                              "status": status, "created_at": now,
                              **{k: (jdump(v) if k == "sources" else v) for k, v in extra.items()}})
    if status in ("received", "sent"):  # drafts/notes don't change the chat-list preview
        execute("UPDATE chats SET last_message_at = ?, last_message_preview = ? WHERE id = ?",
                [now, text[:140], chat_id])
    return mid


def _note(chat_id, text):
    add_message(chat_id, "system", "system", text, "note")


def _in_business_hours(ws: dict) -> bool:
    try:
        now = datetime.now(ZoneInfo(ws["timezone"]))
    except Exception:
        now = datetime.now(timezone.utc)
    hours = ws["business_hours"].get(DAYS[now.weekday()])
    if not hours:
        return False
    start, end = hours
    return start <= now.strftime("%H:%M") < end


def _rate_limited(conn_id: int, per_minute: int) -> bool:
    since = (datetime.now(timezone.utc) - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = query_one("SELECT COUNT(*) AS n FROM messages m JOIN chats c ON c.id = m.chat_id "
                    "WHERE c.connection_id = ? AND m.direction = 'out' AND m.status = 'sent' AND m.created_at >= ?",
                    [conn_id, since])
    return row["n"] >= max(1, int(per_minute))


def _contains_keyword(text: str, keywords) -> bool:
    low = f" {text.lower()} "
    return any(f" {k.lower()} " in low or low.strip() == k.lower() for k in keywords if k)


# ------------------------------------------------------------------ inbound
def handle_inbound(conn: dict, msg: Inbound) -> int | None:
    """Store the message and schedule a reply. Returns message id (None if duplicate/ignored)."""
    wa = get_section(conn["workspace_id"], "whatsapp_settings")
    if msg.is_group and wa["ignore_groups"]:
        return None
    contact = _upsert_contact(conn["workspace_id"], msg.wa_id, msg.name)
    chat = _upsert_chat(conn, contact)
    if msg.provider_message_id and query_one(
            "SELECT id FROM messages WHERE chat_id = ? AND provider_message_id = ?", [chat["id"], msg.provider_message_id]):
        return None  # provider retry
    mid = add_message(chat["id"], "in", "customer", msg.text, "received",
                      provider_message_id=msg.provider_message_id or None)
    execute("UPDATE chats SET unread_count = unread_count + 1 WHERE id = ?", [chat["id"]])
    update("wa_connections", conn["id"], {"last_event_at": utcnow()})
    enqueue(respond, chat["id"], mid)
    return mid


def respond(chat_id: int, inbound_id: int) -> None:
    """Worker job: decide what to do with one inbound message."""
    chat = query_one("SELECT * FROM chats WHERE id = ?", [chat_id])
    inbound = query_one("SELECT * FROM messages WHERE id = ?", [inbound_id])
    if not chat or not inbound:
        return
    latest = query_one("SELECT MAX(id) AS id FROM messages WHERE chat_id = ? AND direction = 'in'", [chat_id])
    if latest["id"] != inbound_id:
        return  # a newer customer message arrived; its own job will answer both
    ws_id = chat["workspace_id"]
    ws = get_workspace(ws_id)
    wa = ws["whatsapp_settings"]
    defaults = ws["agent_defaults"]
    rules = {**DEFAULT_RULES, **jload(chat["rules"], {})}
    contact = query_one("SELECT * FROM contacts WHERE id = ?", [chat["contact_id"]])
    conn = query_one("SELECT * FROM wa_connections WHERE id = ?", [chat["connection_id"]])
    text = inbound["text"].strip()

    # 1. opt-out
    if text.upper() in {k.upper() for k in wa["optout_keywords"]}:
        update("contacts", contact["id"], {"opted_out": 1})
        update("chats", chat_id, {"mode": "off"})
        _note(chat_id, "Customer opted out — agents will not message this contact again")
        return
    if contact["opted_out"]:
        return
    # 2. agent switched off / none assigned / human in control
    agent = agents_svc.get_agent(ws_id, chat["agent_id"])
    if chat["mode"] == "off" or not agent or not agent["active"] or chat["handoff_active"]:
        return
    # 3. handoff keyword
    if rules["handoff"] and _contains_keyword(text, defaults["handoff_keywords"]):
        _handoff(chat_id, "Customer asked for a person")
        return
    # 4. business hours
    if rules["business_hours_only"] and not _in_business_hours(ws):
        last = chat["last_away_sent_at"]
        if ws["away_message"] and (not last or last < (datetime.now(timezone.utc) - timedelta(hours=12))
                                   .strftime("%Y-%m-%dT%H:%M:%SZ")):
            _send(conn, chat, ws["away_message"], agent_id=agent["id"], author="agent")
            update("chats", chat_id, {"last_away_sent_at": utcnow()})
        return
    # 5. generate
    reply, sources = _generate(ws_id, agent, chat_id, text)
    if reply is None:
        return
    if reply.strip() == agents_svc.HANDOFF_TOKEN or agents_svc.HANDOFF_TOKEN in reply:
        _handoff(chat_id, f"{agent['name']} handed this chat to a human")
        return
    if defaults["sign_replies"]:
        reply = f"{reply}\n— {agent['name']}"
    record_usage(ws_id, "agent_reply", 1)
    # 6. deliver or draft
    if chat["mode"] == "draft":
        add_message(chat_id, "out", "agent", reply, "draft", agent_id=agent["id"], sources=sources)
        return
    if _rate_limited(conn["id"], wa["max_per_minute"]):
        add_message(chat_id, "out", "agent", reply, "draft", agent_id=agent["id"], sources=sources,
                    error="Held as draft: sending limit reached")
        return
    if current_app.config["REPLY_DELAYS_ENABLED"]:
        lo, hi = sorted((int(wa["delay_min"]), int(wa["delay_max"])))
        time.sleep(random.uniform(max(0, lo), max(0, hi)))
    _send(conn, chat, reply, agent_id=agent["id"], author="agent", sources=sources)


def _history(chat_id: int, before_text: str | None = None) -> list[dict]:
    rows = query("SELECT direction, author, text, status FROM messages WHERE chat_id = ? "
                 "AND status IN ('received','sent') ORDER BY id DESC LIMIT 14", [chat_id])
    rows.reverse()
    hist = [{"role": "user" if r["direction"] == "in" else "assistant", "content": r["text"]} for r in rows]
    if hist and hist[-1]["role"] == "user" and before_text is not None:
        hist = hist[:-1]  # the message being answered is appended by build_messages
    return hist


def _generate(ws_id, agent, chat_id, text):
    messages, sources = agents_svc.build_messages(ws_id, agent, _history(chat_id, text), text)
    try:
        result = router.generate(ws_id, agent, messages)
    except LLMError as exc:
        current_app.logger.error("chat %s: all models failed: %s", chat_id, exc)
        _note(chat_id, "The agent could not reply (model error). Check Settings › Models & API keys.")
        return None, []
    return result.text, sources


def _handoff(chat_id, reason):
    update("chats", chat_id, {"handoff_active": 1})
    _note(chat_id, reason)


def _send(conn, chat, text, *, agent_id=None, user_id=None, author="agent", sources=None, existing_id=None):
    contact = query_one("SELECT wa_id FROM contacts WHERE id = ?", [chat["contact_id"]])
    try:
        pid = conn_svc.adapter_for(conn).send_text(contact["wa_id"], text)
        status, error = "sent", None
    except WhatsAppError as exc:
        current_app.logger.error("send failed on connection %s: %s", conn["id"], exc)
        pid, status, error = None, "failed", str(exc)[:300]
    if existing_id:
        update("messages", existing_id, {"text": text, "status": status, "error": error,
                                         "provider_message_id": pid or None, "user_id": user_id,
                                         "created_at": utcnow()})
        execute("UPDATE chats SET last_message_at = ?, last_message_preview = ? WHERE id = ?",
                [utcnow(), text[:140], chat["id"]])
        return existing_id
    return add_message(chat["id"], "out", author, text, status, agent_id=agent_id, user_id=user_id,
                       sources=sources or [], error=error, provider_message_id=pid or None)


# ------------------------------------------------------------------ inbox actions
def _chat_conn(workspace_id, chat_id):
    chat = query_one("SELECT * FROM chats WHERE id = ? AND workspace_id = ?", [chat_id, workspace_id])
    if not chat:
        raise LookupError("chat not found")
    conn = query_one("SELECT * FROM wa_connections WHERE id = ?", [chat["connection_id"]])
    return chat, conn


def approve_draft(workspace_id: int, message_id: int, user_id: int, text: str | None = None) -> dict:
    msg = query_one("SELECT m.* FROM messages m JOIN chats c ON c.id = m.chat_id "
                    "WHERE m.id = ? AND c.workspace_id = ?", [message_id, workspace_id])
    if not msg or msg["status"] != "draft":
        raise LookupError("draft not found")
    chat, conn = _chat_conn(workspace_id, msg["chat_id"])
    _send(conn, chat, (text or msg["text"]).strip(), user_id=user_id, existing_id=message_id)
    return query_one("SELECT * FROM messages WHERE id = ?", [message_id])


def discard_draft(workspace_id: int, message_id: int) -> None:
    msg = query_one("SELECT m.id FROM messages m JOIN chats c ON c.id = m.chat_id "
                    "WHERE m.id = ? AND c.workspace_id = ? AND m.status = 'draft'", [message_id, workspace_id])
    if not msg:
        raise LookupError("draft not found")
    update("messages", message_id, {"status": "discarded"})


def send_human(workspace_id: int, chat_id: int, user_id: int, text: str) -> int:
    chat, conn = _chat_conn(workspace_id, chat_id)
    if not chat["handoff_active"]:
        update("chats", chat_id, {"handoff_active": 1})
        _note(chat_id, "A teammate took over — the agent is paused")
    return _send(conn, chat, text.strip(), user_id=user_id, author="human")


def take_over(workspace_id: int, chat_id: int) -> None:
    _chat_conn(workspace_id, chat_id)
    update("chats", chat_id, {"handoff_active": 1})
    _note(chat_id, "A teammate took over — the agent is paused")


def resume_agent(workspace_id: int, chat_id: int) -> None:
    _chat_conn(workspace_id, chat_id)
    update("chats", chat_id, {"handoff_active": 0})
    _note(chat_id, "Agent resumed")


def ask_agent(workspace_id: int, chat_id: int) -> int | None:
    """Generate a draft for the latest customer message on demand."""
    chat, _ = _chat_conn(workspace_id, chat_id)
    agent = agents_svc.get_agent(workspace_id, chat["agent_id"])
    if not agent:
        raise LookupError("assign an agent first")
    last = query_one("SELECT text FROM messages WHERE chat_id = ? AND direction = 'in' ORDER BY id DESC LIMIT 1",
                     [chat_id])
    if not last:
        raise LookupError("no customer message to answer")
    reply, sources = _generate(workspace_id, agent, chat_id, last["text"])
    if reply is None:
        return None
    return add_message(chat_id, "out", "agent", reply, "draft", agent_id=agent["id"], sources=sources)


def purge_old_messages(workspace_id: int) -> int:
    """Data retention (Settings › Security). Called by `flask purge`."""
    days = int(get_section(workspace_id, "security_settings")["retention_days"] or 0)
    if days <= 0:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = get_db().execute("DELETE FROM messages WHERE created_at < ? AND chat_id IN "
                           "(SELECT id FROM chats WHERE workspace_id = ?)", [cutoff, workspace_id])
    get_db().commit()
    return cur.rowcount
