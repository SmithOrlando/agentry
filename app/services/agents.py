"""Agents and the prompt every reply is built from."""
from __future__ import annotations

from flask import current_app

from ..db import jdump, jload, query, query_one, utcnow
from ..knowledge.retrieval import search
from .settings import get_section, get_workspace

TEMPLATES = {
    "Customer Service": ("Orders, returns, FAQs", "#1F6FEB",
                         "You are the customer service agent for {business}. Be warm and brief — two or three "
                         "sentences. Only answer from the knowledge sources. If you are not sure, say a teammate "
                         "will follow up."),
    "Project Manager": ("Tasks, deadlines, follow-ups", "#E8590C",
                        "You coordinate projects for {business}. Confirm dates, owners and next steps clearly. "
                        "Never promise a date that is not in the sources."),
    "Marketing": ("Promos, campaigns, new leads", "#D6336C",
                  "You handle marketing conversations for {business}. Be upbeat and concise, describe current "
                  "promotions only from the sources, and ask interested people what they are looking for."),
    "Sales": ("Quotes and product questions", "#0E9F6E",
              "You answer product and pricing questions for {business}. Quote only prices found in the sources; "
              "otherwise offer to have a teammate send a quote."),
}

HANDOFF_TOKEN = "[HANDOFF]"


def list_agents(workspace_id: int) -> list[dict]:
    rows = query("SELECT a.*, "
                 " (SELECT COUNT(*) FROM agent_files af WHERE af.agent_id = a.id) AS file_count, "
                 " (SELECT COUNT(*) FROM chats c WHERE c.agent_id = a.id) AS chat_count "
                 "FROM agents a WHERE a.workspace_id = ? ORDER BY a.id", [workspace_id])
    for r in rows:
        r["model_override"] = jload(r["model_override"])
    return rows


def get_agent(workspace_id: int, agent_id) -> dict | None:
    if agent_id is None:
        return None
    return query_one("SELECT * FROM agents WHERE id = ? AND workspace_id = ?", [agent_id, workspace_id])


def agent_row(workspace_id: int, data: dict) -> dict:
    now = utcnow()
    return {"workspace_id": workspace_id, "name": data["name"].strip()[:80],
            "description": data.get("description", "")[:200], "color": data.get("color", "#1F6FEB"),
            "instructions": data.get("instructions", ""), "active": 1 if data.get("active", True) else 0,
            "model_override": jdump(data["model_override"]) if data.get("model_override") else None,
            "created_at": now, "updated_at": now}


def build_messages(workspace_id: int, agent: dict | None, history: list[dict], user_text: str,
                   channel: str = "whatsapp", use_knowledge: bool = True) -> tuple[list[dict], list[dict]]:
    """Return (messages for the LLM, sources used).

    history: [{"role": "user"|"assistant", "content": str}] oldest first, NOT including user_text.
    """
    ws = get_workspace(workspace_id)
    defaults = get_section(workspace_id, "agent_defaults")
    k = current_app.config["RETRIEVAL_TOP_K"]
    hits = search(workspace_id, agent["id"] if agent else None, user_text, k) if use_knowledge else []
    sources = [{"file": h["filename"], "locator": h["locator"]} for h in hits]

    parts = []
    instructions = (agent or {}).get("instructions") or "You are a helpful assistant for this business."
    parts.append(instructions.replace("{business}", ws["name"]))
    rules = [
        f"Reply in the customer's language; if unclear, use {ws['default_language']}.",
        "Use only the knowledge sources below for facts about the business (prices, policies, dates). "
        "If the answer is not in them, say you will check with a teammate.",
    ]
    if channel == "whatsapp":
        rules.append("This is a WhatsApp chat: keep replies short, plain text, no markdown headings.")
        rules.append(f"If the customer asks for a human, is upset, or you cannot help, reply with exactly "
                     f"{HANDOFF_TOKEN} and nothing else.")
    if defaults["never_topics"]:
        rules.append("Never discuss: " + ", ".join(defaults["never_topics"]) + f". If asked, reply {HANDOFF_TOKEN}."
                     if channel == "whatsapp" else "Politely decline to discuss: " + ", ".join(defaults["never_topics"]) + ".")
    parts.append("Rules:\n- " + "\n- ".join(rules))
    if hits:
        src = "\n".join(f'<source file="{h["filename"]}" where="{h["locator"]}">\n{h["text"]}\n</source>'
                        for h in hits)
        parts.append("Knowledge sources:\n" + src)
    else:
        parts.append("Knowledge sources: (none matched this question)")

    messages = [{"role": "system", "content": "\n\n".join(parts)}]
    messages += history[-12:]
    messages.append({"role": "user", "content": user_text})
    return messages, sources
