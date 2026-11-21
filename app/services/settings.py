"""Workspace-level settings stored as JSON columns, with typed defaults.

Reading always merges stored values over the defaults below, so adding a new
setting only needs a default here (no migration).
"""
from __future__ import annotations

from ..db import jdump, jload, query_one, execute, utcnow, insert

LLM_DEFAULTS = {
    "source": "platform",      # "platform" | "byok"
    "provider": "openai",      # used when source == "byok"
    "model": "",
    "temperature": 0.4,
    "max_tokens": 500,
    "fallback": True,          # fall back to the platform default if BYOK fails
}

WHATSAPP_DEFAULTS = {
    "default_agent_id": None,
    "default_mode": "draft",   # auto | draft | off
    "ignore_groups": True,
    "max_per_minute": 20,
    "delay_min": 3,
    "delay_max": 8,
    "optout_keywords": ["STOP", "BAJA", "退订"],
}

AGENT_DEFAULTS = {
    "handoff_keywords": ["human", "agent", "person", "complaint", "refund"],
    "never_topics": ["legal advice", "medical advice", "competitor prices"],
    "sign_replies": False,
    "general_knowledge": True,   # answer general questions; False = only questions about the business
}

SECURITY_DEFAULTS = {
    "retention_days": 90,      # 0 = keep forever; enforced by `flask purge` (cron)
}

DEFAULT_HOURS = {d: ["09:00", "18:00"] for d in ("mon", "tue", "wed", "thu", "fri")} | {"sat": None, "sun": None}

COLUMNS = {
    "llm_settings": LLM_DEFAULTS,
    "whatsapp_settings": WHATSAPP_DEFAULTS,
    "agent_defaults": AGENT_DEFAULTS,
    "security_settings": SECURITY_DEFAULTS,
}


def get_workspace(workspace_id: int) -> dict:
    ws = query_one("SELECT * FROM workspaces WHERE id = ?", [workspace_id])
    if not ws:
        raise LookupError("workspace not found")
    for col, defaults in COLUMNS.items():
        ws[col] = {**defaults, **jload(ws[col], {})}
    ws["business_hours"] = {**DEFAULT_HOURS, **jload(ws["business_hours"], {})}
    return ws


def get_section(workspace_id: int, column: str) -> dict:
    return get_workspace(workspace_id)[column]


def update_section(workspace_id: int, column: str, patch: dict) -> dict:
    """Validate keys against defaults and persist. Unknown keys are ignored."""
    if column not in COLUMNS:
        raise ValueError(column)
    defaults = COLUMNS[column]
    current = get_section(workspace_id, column)
    for key, value in patch.items():
        if key in defaults:
            current[key] = value
    execute(f"UPDATE workspaces SET {column} = ? WHERE id = ?", [jdump(current), workspace_id])
    return current


def update_general(workspace_id: int, patch: dict) -> dict:
    allowed = {"name", "default_language", "timezone", "away_message"}
    sets = {k: v for k, v in patch.items() if k in allowed and isinstance(v, str)}
    if "business_hours" in patch and isinstance(patch["business_hours"], dict):
        sets["business_hours"] = jdump(patch["business_hours"])
    if sets:
        cols = ", ".join(f"{k} = ?" for k in sets)
        execute(f"UPDATE workspaces SET {cols} WHERE id = ?", [*sets.values(), workspace_id])
    return get_workspace(workspace_id)


def audit(workspace_id: int, user_id: int | None, action: str, target: str = "") -> None:
    insert("audit_log", {"workspace_id": workspace_id, "user_id": user_id, "action": action,
                         "target": target, "created_at": utcnow()})


def record_usage(workspace_id: int, kind: str, amount: int) -> None:
    if amount:
        insert("usage_events", {"workspace_id": workspace_id, "kind": kind, "amount": int(amount),
                                "created_at": utcnow()})
