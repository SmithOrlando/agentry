"""Generate the API documentation from the code:

    docs/API_BACKEND.md   every HTTP endpoint: purpose, role, parameters, body fields,
                          example request, REAL example response, errors
    docs/openapi.json     the same as an OpenAPI 3.0 file (import into Swagger UI / Postman / Insomnia)
    docs/API_FRONTEND.md  the Vue app's internal API: client, session, utils, composables,
                          components (props/events), routes, and what each screen calls

    python3 scripts/gen_api_docs.py           # regenerate all three
    python3 scripts/gen_api_docs.py --check   # exit 1 if a route is undocumented or a handler
                                              # reads a body/query field the spec doesn't list

Example responses are captured by calling the real endpoints on a throw-away database
(mock LLM, sandbox WhatsApp), so they always match what the code returns.
Descriptions live in SPEC below — update them when you change an endpoint.
"""
from __future__ import annotations

import hashlib
import hmac
import inspect
import io
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app import create_app  # noqa: E402
from app.config import TestConfig  # noqa: E402
from app.services.settings import AGENT_DEFAULTS, LLM_DEFAULTS, SECURITY_DEFAULTS, WHATSAPP_DEFAULTS  # noqa: E402

DOCS = ROOT / "docs"

# ======================================================================================
# SPEC — one entry per (METHOD, path). Field tuple: (name, type, required, description)
# ======================================================================================
S, I, B, N, O = "string", "integer", "boolean", "number", "object"
A = lambda t: f"array<{t}>"  # noqa: E731


def F(name, typ, req, desc):
    return {"name": name, "type": typ, "required": req, "desc": desc}


SECTION_DOC = {
    "whatsapp": ("WhatsApp behaviour defaults and sending limits", WHATSAPP_DEFAULTS, {
        "default_agent_id": (I, "Agent for new chats when the number has no default (null = none)"),
        "default_mode": (S, "`auto` | `draft` | `off` for new chats"),
        "ignore_groups": (B, "Ignore WhatsApp group chats"),
        "max_per_minute": (I, "Max automatic sends per minute per number; extra replies become drafts"),
        "delay_min": (I, "Minimum random delay before an automatic reply (seconds)"),
        "delay_max": (I, "Maximum random delay (seconds)"),
        "optout_keywords": (A(S), "Exact messages that opt a customer out (case-insensitive)")}),
    "agent-defaults": ("Rules every agent follows", AGENT_DEFAULTS, {
        "handoff_keywords": (A(S), "Words that send the chat to a human"),
        "never_topics": (A(S), "Topics agents must decline (and hand off on WhatsApp)"),
        "sign_replies": (B, "Append the agent's name to WhatsApp replies")}),
    "security": ("Data retention", SECURITY_DEFAULTS, {
        "retention_days": (I, "Delete messages older than this many days (0 = keep forever). Applied by `flask purge`")}),
}

LLM_FIELDS = [F("source", S, False, "`platform` (hidden default model) or `byok` (workspace's own key)"),
              F("provider", S, False, "`openai` · `anthropic` · `gemini` · `deepseek` · `qwen` · `openai_compatible` (used when source = byok)"),
              F("model", S, False, "Model id at that provider, e.g. `gpt-4o-mini`"),
              F("temperature", N, False, "0–1 (clamped)"),
              F("max_tokens", I, False, "50–4000 (clamped)"),
              F("fallback", B, False, "Fall back to the platform default when the workspace key fails")]
assert {f["name"] for f in LLM_FIELDS} == set(LLM_DEFAULTS), "LLM_FIELDS out of sync with LLM_DEFAULTS"

SPEC = [
    # ------------------------------------------------------------------ auth
    dict(group="Auth", method="POST", path="/api/auth/register", role="public", csrf=False,
         summary="Create a workspace and its owner (or join a workspace with an invite).",
         body=[F("email", S, True, "Login email (unique across the system)"), F("password", S, True, "At least 8 characters"),
               F("name", S, False, "Display name (defaults to the part of the email before @)"),
               F("workspace", S, False, "Business name for the new workspace (ignored with an invite)"),
               F("invite_token", S, False, "Token from an invite link; joins that workspace with the invited role")],
         returns="`{ok: true}` and a session cookie. New workspaces get four starter agents.",
         errors=["400 invalid email/short password, or invalid/used invite", "403 registration closed (`ALLOW_REGISTRATION=false`)",
                 "409 email already registered"]),
    dict(group="Auth", method="POST", path="/api/auth/login", role="public", csrf=False,
         summary="Sign in. Sets the session cookie.",
         body=[F("email", S, True, "Login email"), F("password", S, True, "Password")],
         returns="`{ok: true}` and a session cookie. Call `GET /api/me` next for the CSRF token.",
         errors=["401 wrong email or password"]),
    dict(group="Auth", method="POST", path="/api/auth/logout", role="public",
         summary="Sign out (clears the session).", returns="`{ok: true}`"),
    dict(group="Auth", method="POST", path="/api/auth/password", role="any signed-in",
         summary="Change your own password.",
         body=[F("current", S, True, "Current password"), F("new", S, True, "New password, at least 8 characters")],
         returns="`{ok: true}`", errors=["400 new password too short", "403 current password wrong"]),
    dict(group="Auth", method="GET", path="/api/me", role="any signed-in",
         summary="Who is signed in, their workspace, and the CSRF token for write requests.",
         returns="`user` {id, workspace_id, email, name, role}, `workspace` {id, name}, `csrf` (send as `X-CSRF-Token`), "
                 "`setup` {model_ready: false while replies come from the placeholder model, real_whatsapp: false until a real (non-sandbox) number exists, test_tools: whether Sandbox/Simulate are enabled} (drives the sidebar's Finish setup card)."),
    # ------------------------------------------------------------------ playground
    dict(group="Playground", method="GET", path="/api/playground/sessions", role="supervisor",
         summary="Your recent Playground chats (max 30, newest first).", returns="`sessions[]` {id, title, agent_id, updated_at}"),
    dict(group="Playground", method="POST", path="/api/playground/sessions", role="supervisor",
         summary="Start a new Playground chat.", body=[F("agent_id", I, False, "Agent to talk to (can change per message)")],
         returns="`{id}` of the new session (201)."),
    dict(group="Playground", method="GET", path="/api/playground/sessions/{sid}", role="supervisor",
         summary="One Playground chat with all its messages.", params=[F("sid", I, True, "Session id")],
         returns="`session` and `messages[]` {id, role: user|assistant, text, sources[{file, locator}], meta{model, agent}, created_at}",
         errors=["404 not your session"]),
    dict(group="Playground", method="DELETE", path="/api/playground/sessions/{sid}", role="supervisor",
         summary="Delete a Playground chat.", params=[F("sid", I, True, "Session id")], returns="`{ok: true}`", errors=["404 not your session"]),
    dict(group="Playground", method="POST", path="/api/playground/sessions/{sid}/messages", role="supervisor",
         summary="Send a message to the agent and get its answer (synchronous; waits for the model). "
                 "With no AI model set up it answers 502 with \"No AI model is set up yet…\".",
         params=[F("sid", I, True, "Session id")],
         body=[F("text", S, True, "Your message"), F("agent_id", I, False, "Agent to answer (default: the session's)"),
               F("use_knowledge", B, False, "Search the agent's knowledge files (default true)")],
         returns="`{id, role: \"assistant\", text, sources[{file, locator}], meta{model, agent}}`. `meta.model` is \"Platform default\" when the hidden model answered.",
         errors=["400 empty message", "404 not your session", "502 every configured model failed (message lists why)"]),
    # ------------------------------------------------------------------ agents
    dict(group="Agents", method="GET", path="/api/agents", role="viewer",
         summary="All agents in the workspace, plus available templates.",
         returns="`agents[]` {id, name, description, color, instructions, model_override{provider, model}|null, active, file_count, chat_count, active_model}, `templates[]` (names)"),
    dict(group="Agents", method="POST", path="/api/agents", role="admin", summary="Create an agent (optionally from a template).",
         body=[F("name", S, True, "Unique in the workspace (or give `template` and it's used as the name)"),
               F("template", S, False, "`Customer Service` · `Project Manager` · `Marketing` · `Sales`: fills missing fields"),
               F("description", S, False, "Short description"), F("color", S, False, "Hex colour, e.g. `#1F6FEB`"),
               F("instructions", S, False, "System prompt; `{business}` becomes the workspace name"),
               F("active", B, False, "Default true"), F("model_override", O, False, "`{provider, model}` to use a specific model, or null")],
         returns="`{id}` (201)", errors=["400 name missing", "409 name already used"]),
    dict(group="Agents", method="PATCH", path="/api/agents/{aid}", role="admin", summary="Update an agent. Send only the fields to change.",
         params=[F("aid", I, True, "Agent id")],
         body=[F("name", S, False, "New name (unique)"), F("description", S, False, ""), F("color", S, False, ""),
               F("instructions", S, False, ""), F("active", B, False, "false = paused (never replies)"),
               F("model_override", O, False, "`{provider, model}` or null to use the workspace model")],
         returns="`{ok: true}`", errors=["404 unknown agent", "409 name already used"]),
    dict(group="Agents", method="DELETE", path="/api/agents/{aid}", role="admin", summary="Delete an agent. Its chats become unassigned.",
         params=[F("aid", I, True, "Agent id")], returns="`{ok: true}`", errors=["404 unknown agent"]),
    # ------------------------------------------------------------------ knowledge
    dict(group="Knowledge", method="GET", path="/api/knowledge/files", role="viewer", summary="All knowledge sources with indexing status.",
         returns="`files[]` {id, filename, kind, source_url, size_bytes, status: pending|indexing|ready|failed, error, chunk_count, agents[{id,name}], created_at, updated_at}, `total_chunks`"),
    dict(group="Knowledge", method="POST", path="/api/knowledge/files", role="supervisor", content="multipart/form-data",
         summary="Upload one or more files. Indexing runs in the background: poll the list until `status` is `ready`.",
         body=[F("files", A("file"), True, "PDF, DOCX, XLSX, CSV, TXT or MD (max `MAX_UPLOAD_MB` each request)"),
               F("agent_ids", A(I), False, "Agents allowed to use these files (repeat the field)")],
         returns="`{created: [file ids], errors: [{file, error}]}`: 201 if at least one file was accepted",
         errors=["400 no files, or every file unsupported", "413 request too large"]),
    dict(group="Knowledge", method="POST", path="/api/knowledge/text", role="supervisor", summary="Add pasted text / Q&A as a knowledge source.",
         body=[F("text", S, True, "The content"), F("title", S, False, "Shown in the file list (default \"Quick Q&A\")"),
               F("agent_ids", A(I), False, "Agents allowed to use it")], returns="`{id}` (201)", errors=["400 empty text"]),
    dict(group="Knowledge", method="POST", path="/api/knowledge/url", role="supervisor",
         summary="Add one public web page. It's fetched in the background (private/internal addresses are refused).",
         body=[F("url", S, True, "Full http(s) URL"), F("agent_ids", A(I), False, "Agents allowed to use it")],
         returns="`{id}` (201). If the fetch fails the file shows `status: failed` with the reason.", errors=["400 not an http(s) URL"]),
    dict(group="Knowledge", method="PATCH", path="/api/knowledge/files/{fid}", role="supervisor", summary="Change which agents may use a file.",
         params=[F("fid", I, True, "File id")], body=[F("agent_ids", A(I), False, "Full new list (replaces the old one)")],
         returns="`{ok: true}`", errors=["404 unknown file"]),
    dict(group="Knowledge", method="POST", path="/api/knowledge/files/{fid}/reindex", role="supervisor", summary="Extract and index the file again.",
         params=[F("fid", I, True, "File id")], returns="`{ok: true}`; status goes back to `pending`", errors=["404 unknown file"]),
    dict(group="Knowledge", method="DELETE", path="/api/knowledge/files/{fid}", role="supervisor", summary="Delete a file, its chunks and agent links.",
         params=[F("fid", I, True, "File id")], returns="`{ok: true}`", errors=["404 unknown file"]),
    # ------------------------------------------------------------------ whatsapp
    dict(group="WhatsApp numbers", method="GET", path="/api/whatsapp/connections", role="viewer", summary="All connected numbers (no secrets).",
         returns="`connections[]` {id, name, provider, phone_number, account_name, profile_picture, status: pending|connected|disconnected|expired|error, status_detail, default_agent_id, default_mode, webhook_url, last_event_at, last_message_at, created_at}"),
    dict(group="WhatsApp numbers", method="POST", path="/api/whatsapp/connections", role="admin",
         summary="Add a number. For Evolution API this also creates the instance, registers our webhook and returns the first QR code.",
         body=[F("name", S, False, "Label, e.g. \"Support line\""),
               F("provider", S, True, "`evolution` · `meta_cloud` · `generic` (· `sandbox` with test tools)"),
               F("phone_number", S, False, "Display only"),
               F("config", O, True, "Credentials (stored encrypted). evolution: `{server_url, api_key}` · meta_cloud: `{phone_number_id, access_token, app_secret, verify_token}` · generic: `{send_url, token?}` · sandbox: `{}`")],
         returns="`connection` (201). Evolution adds `qr` (data URL) and `pairing_code` when the server answered; if it didn't, `status` is `error` with the reason in `status_detail`.",
         errors=["400 unknown provider or missing config keys"]),
    dict(group="WhatsApp numbers", method="PATCH", path="/api/whatsapp/connections/{cid}", role="admin", summary="Rename a number or set its defaults for new chats.",
         params=[F("cid", I, True, "Connection id")],
         body=[F("name", S, False, ""), F("phone_number", S, False, ""), F("default_agent_id", I, False, "Agent for new chats on this number (null = workspace default)"),
               F("default_mode", S, False, "`auto` · `draft` · `off` · null")],
         returns="`connection`", errors=["404 unknown connection"]),
    dict(group="WhatsApp numbers", method="DELETE", path="/api/whatsapp/connections/{cid}", role="admin",
         summary="Remove a number and all its chats. For Evolution it also logs the phone out and deletes the instance on the Evolution server (best effort).",
         params=[F("cid", I, True, "Connection id")], returns="`{ok: true}`", errors=["404 unknown connection"]),
    dict(group="WhatsApp numbers", method="GET", path="/api/whatsapp/connections/{cid}/qr", role="admin", summary="Current QR code to link an Evolution number.",
         params=[F("cid", I, True, "Connection id")], returns="`{qr: \"data:image/png;base64,…\" | null, pairing_code}`; `qr` is null when already linked",
         errors=["400 not an Evolution connection", "404 unknown connection", "502 Evolution server unreachable / error"],
         static_example=(200, {"qr": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA…", "pairing_code": "WZYEH1YY"})),
    dict(group="WhatsApp numbers", method="POST", path="/api/whatsapp/connections/{cid}/refresh", role="viewer",
         summary="Ask the provider for the live status and store it.", params=[F("cid", I, True, "Connection id")],
         returns="`connection` with updated `status`", errors=["404 unknown connection"]),
    dict(group="WhatsApp numbers", method="POST", path="/api/whatsapp/connections/{cid}/simulate", role="admin",
         summary="**Test tools only** (`ENABLE_TEST_TOOLS=true`; answers 404 otherwise). Inject a customer message as if it came from WhatsApp. Runs the full reply pipeline (testing without a phone).",
         params=[F("cid", I, True, "Connection id")],
         body=[F("text", S, True, "Customer message"), F("from", S, False, "Customer phone, digits (default 10000000000)"),
               F("name", S, False, "Customer name (default \"Test customer\")")],
         returns="`{message_id}` (201); null if ignored (e.g. duplicate).", errors=["400 text missing", "404 unknown connection"]),
    # ------------------------------------------------------------------ inbox
    dict(group="Inbox", method="GET", path="/api/inbox/chats", role="viewer", summary="Chat list for the Inbox (max 200, most recent first).",
         query=[F("filter", S, False, "`all` (default) · `drafts` · `needs_you` · `unassigned`"),
                F("q", S, False, "Search name, phone or last message"), F("connection_id", I, False, "Only this number")],
         returns="`chats[]` {id, mode, agent_id, agent_name, agent_color, handoff_active, unread_count, drafts, last_message_at, last_message_preview, connection_id, connection_name, contact_name, wa_id}, `counts` {all_, drafts, needs_you, unread (chats with unread messages)}"),
    dict(group="Inbox", method="GET", path="/api/inbox/chats/{cid}", role="viewer", summary="One chat: details, messages and stats. Marks it read.",
         params=[F("cid", I, True, "Chat id")], query=[F("mark_read", S, False, "`0` to leave unread_count unchanged (default `1`)")],
         returns="`chat` {…, rules{handoff, business_hours_only, match_language}, tags[], opted_out, contact_since}, `messages[]` {id, direction: in|out|system, author: customer|agent|human|system, text, status: received|draft|sent|failed|note, sources[], error, agent_name, user_name, created_at}, `stats` {agent_replies, drafts_approved, first_message}",
         errors=["404 unknown chat"]),
    dict(group="Inbox", method="PATCH", path="/api/inbox/chats/{cid}", role="supervisor", summary="Change a chat's agent, reply mode, rules or tags.",
         params=[F("cid", I, True, "Chat id")],
         body=[F("agent_id", I, False, "Agent id, or null for none"), F("mode", S, False, "`auto` · `draft` · `off`"),
               F("rules", O, False, "Any of `{handoff, business_hours_only, match_language}` (booleans); merged"),
               F("tags", A(S), False, "Replace the contact's tags (max 20)"),
               F("apply_to_connection", B, False, "Also make agent/mode the number's defaults and apply them to all its chats")],
         returns="`{ok: true}`", errors=["400 unknown agent", "404 unknown chat"]),
    dict(group="Inbox", method="DELETE", path="/api/inbox/chats/{cid}", role="supervisor",
         summary="Delete a chat and all its messages. The contact is removed too when it has no other chats.",
         params=[F("cid", I, True, "Chat id")], returns="`{ok: true}`", errors=["404 unknown chat"]),
    dict(group="Inbox", method="POST", path="/api/inbox/chats/{cid}/messages", role="supervisor",
         summary="Send a message as yourself. Pauses the agent (sets handoff).", params=[F("cid", I, True, "Chat id")],
         body=[F("text", S, True, "Message")], returns="`{id}` (201): message status is `sent` or `failed`", errors=["400 empty", "404 unknown chat"]),
    dict(group="Inbox", method="POST", path="/api/inbox/chats/{cid}/takeover", role="supervisor", summary="Pause the agent on this chat (\"Needs you\").",
         params=[F("cid", I, True, "Chat id")], returns="`{ok: true}`", errors=["404 unknown chat"]),
    dict(group="Inbox", method="POST", path="/api/inbox/chats/{cid}/resume", role="supervisor", summary="Let the agent reply again.",
         params=[F("cid", I, True, "Chat id")], returns="`{ok: true}`", errors=["404 unknown chat"]),
    dict(group="Inbox", method="POST", path="/api/inbox/chats/{cid}/ask-agent", role="supervisor",
         summary="Have the agent draft a reply to the latest customer message now.", params=[F("cid", I, True, "Chat id")],
         returns="`{id}` of the new draft (201)", errors=["404 no agent assigned / no customer message", "502 model error"]),
    dict(group="Inbox", method="POST", path="/api/inbox/messages/{mid}/approve", role="supervisor", summary="Send a draft (optionally edited).",
         params=[F("mid", I, True, "Draft message id")], body=[F("text", S, False, "Edited text (default: the draft as is)")],
         returns="`message`: status `sent` or `failed`", errors=["404 not a draft"]),
    dict(group="Inbox", method="POST", path="/api/inbox/messages/{mid}/discard", role="supervisor", summary="Throw a draft away.",
         params=[F("mid", I, True, "Draft message id")], returns="`{ok: true}`", errors=["404 not a draft"]),
    # ------------------------------------------------------------------ settings
    dict(group="Settings", method="GET", path="/api/settings/general", role="viewer", summary="Workspace name, language, time zone, hours, away message.",
         returns="`{name, default_language, timezone, away_message, business_hours}`. business_hours: `{mon: [\"09:00\",\"18:00\"], …, sun: null}` (null = closed)"),
    dict(group="Settings", method="PATCH", path="/api/settings/general", role="admin", summary="Update general settings. Send only what changes.",
         body=[F("name", S, False, "Workspace name"), F("default_language", S, False, "e.g. `English`, `Español`"),
               F("timezone", S, False, "IANA name, e.g. `America/Bogota`"), F("away_message", S, False, "Sent outside business hours"),
               F("business_hours", O, False, "Per day `[open, close]` (HH:MM) or null")],
         returns="The full general settings after saving", service_fields=True),
    dict(group="Settings", method="DELETE", path="/api/settings/workspace", role="owner", summary="Permanently delete the workspace and everything in it.",
         body=[F("confirm", S, True, "Must be exactly `DELETE`")], returns="`{ok: true}`", errors=["400 confirm missing"], capture_last=True),
    dict(group="Settings", method="GET", path="/api/settings/llm", role="viewer", summary="Model settings and which providers have keys.",
         returns="`settings` (see PATCH), `providers[]` {id, label, connected, last4, base_url, verified_at}, `active_model` (\"Platform default\" or \"provider · model\"). Keys are never returned."),
    dict(group="Settings", method="PATCH", path="/api/settings/llm", role="admin", summary="Change the workspace model settings.",
         body=LLM_FIELDS, returns="`settings` after saving", errors=["400 invalid source"], service_fields=True),
    dict(group="Settings", method="PUT", path="/api/settings/providers/{provider}", role="admin", summary="Save (or replace) an API key for a provider. Stored encrypted.",
         params=[F("provider", S, True, "`openai` · `anthropic` · `gemini` · `deepseek` · `qwen` · `openai_compatible`")],
         body=[F("api_key", S, False, "Required the first time; blank keeps the stored key"),
               F("base_url", S, False, "Proxy / Azure / self-hosted endpoint (required for openai_compatible)")],
         returns="`{ok: true, switched}`. If the workspace had no real model yet, it is switched to this key automatically "
                 "(source `byok`, a starter model such as `gpt-4o-mini`, or the first model the key lists if that one isn't available) and the response includes `switched: true` and the new `settings`.",
         errors=["400 key required", "404 unknown provider"]),
    dict(group="Settings", method="DELETE", path="/api/settings/providers/{provider}", role="admin", summary="Remove a provider's key.",
         params=[F("provider", S, True, "Provider id")], returns="`{ok: true}`"),
    dict(group="Settings", method="GET", path="/api/settings/providers/{provider}/models", role="admin",
         summary="Models the saved key can use (for the model pickers). Cached for 10 minutes.",
         params=[F("provider", S, True, "Provider id")], query=[F("fresh", S, False, "`1` to skip the cache")],
         returns="`{models: [ids]}`", errors=["502 no key saved, or the provider rejected it (message included)"],
         static_example=(200, {"models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash-preview", "…"]})),
    dict(group="Settings", method="POST", path="/api/settings/providers/{provider}/test", role="admin",
         summary="Check the saved key by listing the provider's models.", params=[F("provider", S, True, "Provider id")],
         returns="`{ok: true, models: [ids]}`; also marks the key verified. If this provider is the workspace model and no model name is set, "
                 "the first listed model is selected and returned as `model_selected`.", errors=["502 no key saved, or the provider rejected it (message included)"],
         static_example=(200, {"ok": True, "models": ["gpt-4o", "gpt-4o-mini", "…"]})),
] + [
    dict(group="Settings", method=m, path=f"/api/settings/{sec}", role=("viewer" if m == "GET" else "admin"),
         summary=(f"Read: {doc[0].lower()}." if m == "GET" else f"Update: {doc[0].lower()}. Send only the keys to change; unknown keys are ignored."),
         body=[] if m == "GET" else [F(k, doc[2][k][0], False, doc[2][k][1]) for k in doc[1]],
         returns="All keys with current values" if m == "GET" else "All keys after saving", service_fields=True, section=sec)
    for sec, doc in SECTION_DOC.items() for m in ("GET", "PATCH")
] + [
    # ------------------------------------------------------------------ team, usage, audit
    dict(group="Team", method="GET", path="/api/team", role="viewer", summary="Members and pending invites.",
         returns="`members[]` {id, name, email, role, last_active_at}, `invites[]` {id, email, role, created_at}, `me` (your user id)"),
    dict(group="Team", method="POST", path="/api/team/invites", role="admin",
         summary="Create invite links (no email is sent; share the link).",
         body=[F("emails", S, True, "One or more addresses, comma or semicolon separated"), F("role", S, False, "`admin` · `supervisor` (default) · `viewer`")],
         returns="`invites[]` {email, link} (201)", errors=["400 no valid email / invalid role"]),
    dict(group="Team", method="DELETE", path="/api/team/invites/{iid}", role="admin", summary="Revoke a pending invite.",
         params=[F("iid", I, True, "Invite id")], returns="`{ok: true}`"),
    dict(group="Team", method="PATCH", path="/api/team/members/{uid}", role="admin", summary="Change a member's role.",
         params=[F("uid", I, True, "User id")], body=[F("role", S, True, "`admin` · `supervisor` · `viewer`")],
         returns="`{ok: true}`", errors=["400 invalid member or role", "403 the owner's role can't change"]),
    dict(group="Team", method="DELETE", path="/api/team/members/{uid}", role="admin", summary="Remove a member.",
         params=[F("uid", I, True, "User id")], returns="`{ok: true}`", errors=["403 owner or yourself"]),
    dict(group="Usage & audit", method="GET", path="/api/usage", role="viewer", summary="This month's usage.",
         returns="`{period_start, agent_replies, platform_tokens, byok_tokens, storage_bytes, numbers}`"),
    dict(group="Usage & audit", method="GET", path="/api/audit", role="admin", summary="Last 100 audit entries (who changed what).",
         returns="`entries[]` {action, target, created_at, user_name}"),
    dict(group="Usage & audit", method="GET", path="/api/export", role="admin", summary="Download everything the workspace owns as JSON (no secrets).",
         returns="JSON file (`Content-Disposition: attachment`) with workspace, agents, knowledge_files, contacts, chats[messages]"),
    # ------------------------------------------------------------------ webhooks + service
    dict(group="Webhooks", method="POST", path="/webhooks/{provider}/{conn_id}/{token}", role="webhook", csrf=False,
         summary="Inbound events from Evolution API, a generic gateway or the sandbox. The URL (with its secret token) is shown in the number's details.",
         params=[F("provider", S, True, "`evolution` · `generic` · `sandbox`"), F("conn_id", I, True, "Connection id"),
                 F("token", S, True, "Secret per-connection token")],
         body_note="Evolution v2: `{event: \"messages.upsert\" | \"connection.update\" | \"qrcode.updated\", instance, data}`. Generic/sandbox: `{from, name, text, id}`.",
         returns="`{ok: true, handled: n}`. Always 200 once authenticated (errors are logged) so providers don't retry-storm. Duplicate message ids are ignored.",
         errors=["404 unknown connection or wrong token"]),
    dict(group="Webhooks", method="GET", path="/webhooks/meta/{conn_id}", role="webhook", csrf=False,
         summary="Meta's webhook verification handshake.", params=[F("conn_id", I, True, "Connection id")],
         query=[F("hub.mode", S, True, "`subscribe`"), F("hub.verify_token", S, True, "Must equal the connection's verify token"),
                F("hub.challenge", S, True, "Echoed back as plain text")],
         returns="The `hub.challenge` value (text/plain); marks the number connected", errors=["403 wrong token", "404 unknown connection"]),
    dict(group="Webhooks", method="POST", path="/webhooks/meta/{conn_id}", role="webhook", csrf=False,
         summary="Inbound messages from the WhatsApp Cloud API. Requires a valid `X-Hub-Signature-256` (HMAC-SHA256 of the raw body with the app secret).",
         params=[F("conn_id", I, True, "Connection id")], body_note="Meta's standard payload: `entry[].changes[].value.messages[]` (text messages are handled).",
         returns="`{ok: true, handled: n}`", errors=["401 bad signature", "404 unknown connection"]),
    dict(group="Service", method="GET", path="/healthz", role="public", summary="Health check (does a database round-trip).", returns="`{status: \"ok\"}`"),
    dict(group="Service", method="GET", path="/", role="public", summary="Service info.", returns="`{service, docs, health}`"),
]

GROUP_ORDER = ["Auth", "Playground", "Agents", "Knowledge", "WhatsApp numbers", "Inbox", "Settings", "Team", "Usage & audit", "Webhooks", "Service"]


# ======================================================================================
# Capture real examples
# ======================================================================================
def _trim(v, depth=0):
    if isinstance(v, list):
        out = [_trim(x, depth + 1) for x in v[:2]]
        if len(v) > 2:
            out.append(f"… {len(v) - 2} more")
        return out
    if isinstance(v, dict):
        return {k: _trim(x, depth + 1) for k, x in v.items()}
    if isinstance(v, str) and len(v) > 140:
        return v[:137] + "…"
    return v


def capture():
    """Call every endpoint on a fresh database and record (status, json) per (method, path-template)."""
    # The test model prefixes answers with "(mock) "; drop it so the examples read like real replies.
    from app.llm import providers as _p
    _orig = _p.Mock.chat
    def _clean(self, *a, **k):
        r = _orig(self, *a, **k)
        r.text = r.text.removeprefix("(mock) ").replace("You said: ", "")
        return r
    _p.Mock.chat = _clean
    tmp = Path(tempfile.mkdtemp())
    app = create_app(TestConfig, INSTANCE_DIR=tmp, DATABASE_PATH=tmp / "doc.db", UPLOAD_DIR=tmp / "u", LOG_LEVEL="ERROR",
                     WHATSAPP_HTTP_TIMEOUT=1, LLM_TIMEOUT_SECONDS=1, PUBLIC_BASE_URL="https://agents.example.com",
                     FRONTEND_URL="https://agents.example.com")
    c = app.test_client()
    ex = {}
    H = {}

    def call(method, template, url, json_body=None, record=True, **kw):
        headers = dict(H, **kw.pop("headers", {}))
        r = getattr(c, method.lower())(url, json=json_body, headers=headers, **kw)
        data = r.get_json(silent=True)
        if data is None:
            data = r.get_data(as_text=True)
        if record and (method, template) not in ex:
            ex[(method, template)] = {"status": r.status_code, "request_url": url, "request": json_body, "response": _trim(data)}
        return r, data

    call("POST", "/api/auth/register", "/api/auth/register",
         {"email": "owner@example.com", "password": "correct-horse", "name": "Ana Owner", "workspace": "Andes Coffee Co."})
    call("POST", "/api/auth/login", "/api/auth/login", {"email": "owner@example.com", "password": "correct-horse"})
    _, me = call("GET", "/api/me", "/api/me")
    H["X-CSRF-Token"] = me["csrf"]
    _, ag = call("GET", "/api/agents", "/api/agents")
    cs = ag["agents"][0]["id"]
    _, new_agent = call("POST", "/api/agents", "/api/agents", {"name": "Receptionist", "description": "Hours and location", "color": "#0EA5E9",
                                                               "instructions": "Greet customers of {business} and share opening hours."})
    call("PATCH", "/api/agents/{aid}", f"/api/agents/{cs}", {"instructions": "You are the customer service agent for {business}. Be brief.",
                                                           "model_override": None})
    # knowledge
    _, kt = call("POST", "/api/knowledge/text", "/api/knowledge/text",
                 {"title": "Returns FAQ", "text": "Sale items can be returned within 14 days for store credit.", "agent_ids": [cs]})
    form = {"files": (io.BytesIO(b"Shipping to Bogota takes 2-3 business days."), "shipping.txt"), "agent_ids": str(cs)}
    call("POST", "/api/knowledge/files", "/api/knowledge/files", data=form, content_type="multipart/form-data")
    call("POST", "/api/knowledge/url", "/api/knowledge/url", {"url": "http://127.0.0.1/internal", "agent_ids": [cs]})
    call("GET", "/api/knowledge/files", "/api/knowledge/files")
    call("PATCH", "/api/knowledge/files/{fid}", f"/api/knowledge/files/{kt['id']}", {"agent_ids": [cs, new_agent["id"]]})
    call("POST", "/api/knowledge/files/{fid}/reindex", f"/api/knowledge/files/{kt['id']}/reindex")
    # whatsapp
    _, cr = call("POST", "/api/whatsapp/connections", "/api/whatsapp/connections",
                 {"name": "Support line", "provider": "sandbox", "phone_number": "+57 300 000 4821", "config": {}})
    conn = cr["connection"]
    call("PATCH", "/api/whatsapp/connections/{cid}", f"/api/whatsapp/connections/{conn['id']}", {"default_agent_id": cs, "default_mode": "draft"})
    call("POST", "/api/whatsapp/connections/{cid}/refresh", f"/api/whatsapp/connections/{conn['id']}/refresh")
    call("POST", "/api/whatsapp/connections/{cid}/simulate", f"/api/whatsapp/connections/{conn['id']}/simulate",
         {"text": "Can I return sale items?", "from": "573001119014", "name": "Maria López"})
    call("GET", "/api/whatsapp/connections", "/api/whatsapp/connections")
    # webhooks
    tok = conn["webhook_url"].rsplit("/", 1)[1]
    call("POST", "/webhooks/{provider}/{conn_id}/{token}", f"/webhooks/sandbox/{conn['id']}/{tok}",
         {"from": "573001119014", "name": "Maria López", "text": "And shipping to Bogota?", "id": "wamid-123"})
    _, mc = call("POST", "/api/whatsapp/connections", "/api/whatsapp/connections",
                 {"name": "Official line", "provider": "meta_cloud", "config": {"phone_number_id": "1234567890", "access_token": "EAAB…",
                                                                                  "app_secret": "app-secret", "verify_token": "my-verify-token"}}, record=False)
    mid_ = mc["connection"]["id"]
    call("GET", "/webhooks/meta/{conn_id}", f"/webhooks/meta/{mid_}?hub.mode=subscribe&hub.verify_token=my-verify-token&hub.challenge=1158201444")
    meta_body = json.dumps({"entry": [{"changes": [{"value": {"contacts": [{"wa_id": "573005550000", "profile": {"name": "Luis"}}],
                                                              "messages": [{"from": "573005550000", "id": "wamid.ABC", "type": "text", "text": {"body": "Hola"}}]}}]}]})
    sig = "sha256=" + hmac.new(b"app-secret", meta_body.encode(), hashlib.sha256).hexdigest()
    r = c.post(f"/webhooks/meta/{mid_}", data=meta_body, content_type="application/json", headers={"X-Hub-Signature-256": sig})
    ex[("POST", "/webhooks/meta/{conn_id}")] = {"status": r.status_code, "request_url": f"/webhooks/meta/{mid_}",
                                               "request": json.loads(meta_body), "response": r.get_json(),
                                               "headers": {"X-Hub-Signature-256": "sha256=<hmac of raw body>"}}
    # qr on an evolution number whose server is unreachable -> documents the 502 path; success shape is static
    _, ev = call("POST", "/api/whatsapp/connections", "/api/whatsapp/connections",
                 {"name": "QR line", "provider": "evolution", "config": {"server_url": "http://127.0.0.1:9", "api_key": "k"}}, record=False)
    call("GET", "/api/whatsapp/connections/{cid}/qr", f"/api/whatsapp/connections/{ev['connection']['id']}/qr", record=False)
    # inbox
    _, chats = call("GET", "/api/inbox/chats", "/api/inbox/chats?filter=all")
    chat_id = next(ch["id"] for ch in chats["chats"] if ch["wa_id"] == "573001119014")
    _, detail = call("GET", "/api/inbox/chats/{cid}", f"/api/inbox/chats/{chat_id}")
    draft = next(m for m in detail["messages"] if m["status"] == "draft")
    call("POST", "/api/inbox/messages/{mid}/approve", f"/api/inbox/messages/{draft['id']}/approve",
         {"text": "Hi Maria! Sale items can be returned within 14 days for store credit."})
    _, ask = call("POST", "/api/inbox/chats/{cid}/ask-agent", f"/api/inbox/chats/{chat_id}/ask-agent")
    call("POST", "/api/inbox/messages/{mid}/discard", f"/api/inbox/messages/{ask['id']}/discard")
    call("PATCH", "/api/inbox/chats/{cid}", f"/api/inbox/chats/{chat_id}", {"mode": "auto", "rules": {"business_hours_only": False}, "tags": ["Returning"]})
    call("POST", "/api/inbox/chats/{cid}/takeover", f"/api/inbox/chats/{chat_id}/takeover")
    call("POST", "/api/inbox/chats/{cid}/messages", f"/api/inbox/chats/{chat_id}/messages", {"text": "Hi, this is Ana from the team."})
    call("POST", "/api/inbox/chats/{cid}/resume", f"/api/inbox/chats/{chat_id}/resume")
    _, chats2 = call("GET", "/api/inbox/chats", "/api/inbox/chats", record=False)
    other = next((ch["id"] for ch in chats2["chats"] if ch["id"] != chat_id), None)
    if other:
        call("DELETE", "/api/inbox/chats/{cid}", f"/api/inbox/chats/{other}")
    # playground
    _, ps = call("POST", "/api/playground/sessions", "/api/playground/sessions", {"agent_id": cs})
    call("POST", "/api/playground/sessions/{sid}/messages", f"/api/playground/sessions/{ps['id']}/messages",
         {"text": "What is the return policy for sale items?", "agent_id": cs, "use_knowledge": True})
    call("GET", "/api/playground/sessions", "/api/playground/sessions")
    call("GET", "/api/playground/sessions/{sid}", f"/api/playground/sessions/{ps['id']}")
    # settings
    call("GET", "/api/settings/general", "/api/settings/general")
    call("PATCH", "/api/settings/general", "/api/settings/general", {"timezone": "America/Bogota", "away_message": "We're closed, back at 9:00."})
    call("PATCH", "/api/settings/llm", "/api/settings/llm", {"source": "byok", "provider": "openai", "model": "gpt-4o-mini", "fallback": True})
    call("PUT", "/api/settings/providers/{provider}", "/api/settings/providers/openai", {"api_key": "sk-proj-EXAMPLE1234", "base_url": ""})
    call("GET", "/api/settings/llm", "/api/settings/llm")
    call("DELETE", "/api/settings/providers/{provider}", "/api/settings/providers/openai")
    call("PATCH", "/api/settings/llm", "/api/settings/llm", {"source": "platform"}, record=False)
    for sec, patch in (("whatsapp", {"default_mode": "draft", "max_per_minute": 15}), ("agent-defaults", {"handoff_keywords": ["human", "manager"]}),
                       ("security", {"retention_days": 30})):
        call("GET", "/api/settings/{section}".replace("{section}", sec), f"/api/settings/{sec}")
        call("PATCH", "/api/settings/{section}".replace("{section}", sec), f"/api/settings/{sec}", patch)
    # team
    _, inv = call("POST", "/api/team/invites", "/api/team/invites", {"emails": "sam@example.com, lee@example.com", "role": "supervisor"})
    call("GET", "/api/team", "/api/team")
    token = inv["invites"][0]["link"].split("invite=")[1]
    other = app.test_client()
    other.post("/api/auth/register", json={"email": "sam@example.com", "password": "password123", "name": "Sam", "invite_token": token})
    _, team = call("GET", "/api/team", "/api/team", record=False)
    sam = next(m for m in team["members"] if m["email"] == "sam@example.com")
    call("PATCH", "/api/team/members/{uid}", f"/api/team/members/{sam['id']}", {"role": "viewer"})
    call("DELETE", "/api/team/members/{uid}", f"/api/team/members/{sam['id']}")
    pending = next(i for i in team["invites"])
    call("DELETE", "/api/team/invites/{iid}", f"/api/team/invites/{pending['id']}")
    call("POST", "/api/auth/password", "/api/auth/password", {"current": "correct-horse", "new": "correct-horse-2"})
    call("GET", "/api/usage", "/api/usage")
    call("GET", "/api/audit", "/api/audit")
    call("GET", "/api/export", "/api/export")
    call("GET", "/healthz", "/healthz")
    call("GET", "/", "/")
    # deletes on throw-away objects
    call("DELETE", "/api/playground/sessions/{sid}", f"/api/playground/sessions/{ps['id']}")
    call("DELETE", "/api/agents/{aid}", f"/api/agents/{new_agent['id']}")
    call("DELETE", "/api/knowledge/files/{fid}", f"/api/knowledge/files/{kt['id']}")
    call("DELETE", "/api/whatsapp/connections/{cid}", f"/api/whatsapp/connections/{ev['connection']['id']}")
    call("POST", "/api/auth/logout", "/api/auth/logout")
    # last: delete a separate workspace
    d = app.test_client()
    d.post("/api/auth/register", json={"email": "temp@example.com", "password": "password123", "workspace": "Temp"})
    tokd = d.get("/api/me").get_json()["csrf"]
    r = d.delete("/api/settings/workspace", json={"confirm": "DELETE"}, headers={"X-CSRF-Token": tokd})
    ex[("DELETE", "/api/settings/workspace")] = {"status": r.status_code, "request_url": "/api/settings/workspace", "request": {"confirm": "DELETE"},
                                                "response": r.get_json()}
    return app, ex


# ======================================================================================
# Checks
# ======================================================================================
def flask_path(p):
    return re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", p)


def check(app) -> list[str]:
    problems = []
    spec_keys = {(e["method"], e["path"]) for e in SPEC}
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        for m in rule.methods - {"HEAD", "OPTIONS"}:
            p = flask_path(rule.rule)
            if p == "/api/settings/{section}":
                continue  # documented per section (whatsapp, agent-defaults, security)
            if (m, p) not in spec_keys:
                problems.append(f"undocumented route: {m} {p}")
            view = inspect.unwrap(app.view_functions[rule.endpoint])
            entry = next((e for e in SPEC if (e["method"], e["path"]) == (m, p)), None)
            if not entry or entry.get("service_fields"):
                continue
            src = inspect.getsource(view)
            read = set(re.findall(r'\bd\.get\("(\w+)"', src)) | set(re.findall(r'\bd\["(\w+)"\]', src)) | \
                set(re.findall(r'body\(\)\.get\("(\w+)"', src)) | set(re.findall(r'"(\w+)" in d\b', src)) | \
                set(re.findall(r'request\.(?:form|files)\.getlist\("(\w+)"', src))
            q = set(re.findall(r'request\.args(?:\.get)?\(?\[?"([\w.]+)"', src))
            documented = {f["name"] for f in entry.get("body", [])}
            for k in read - documented - {"updated_at"}:
                problems.append(f"{m} {p}: handler reads body field '{k}' that the spec doesn't list")
            for k in q - {f["name"] for f in entry.get("query", [])}:
                problems.append(f"{m} {p}: handler reads query '{k}' that the spec doesn't list")
    for (m, p) in spec_keys:
        if p.startswith("/api/settings/") and p.split("/")[-1] in SECTION_DOC:
            continue
        probe = re.sub(r"\{(\w+)\}", lambda mm: "1" if mm.group(1) not in ("provider", "token") else "x", p)
        if p.startswith("/webhooks/{provider}"):
            probe = "/webhooks/sandbox/1/x"
        try:
            app.url_map.bind("localhost").match(probe, method=m)
        except Exception:
            problems.append(f"spec lists {m} {p} but no such route exists")
    return problems


# ======================================================================================
# Markdown + OpenAPI
# ======================================================================================
ROLE_NOTE = {"public": "none (public)", "webhook": "provider authentication (see below)", "any signed-in": "any signed-in user"}


def anchor(e):
    return re.sub(r"[^a-z0-9]+", "-", f"{e['method']} {e['path']}".lower()).strip("-")


def table(rows, head):
    if not rows:
        return []
    out = [f"| {' | '.join(head)} |", "|" + "---|" * len(head)]
    for f in rows:
        out.append(f"| `{f['name']}` | {f['type']} | {'yes' if f['required'] else 'no'} | {f['desc'] or '—'} |")
    return out + [""]


def write_backend_md(ex):
    L = ["# Backend API reference", "",
         "Every HTTP endpoint the Flask app serves. **Generated** by `python3 scripts/gen_api_docs.py` from the code: "
         "example responses are real output captured from a test database (mock model, sandbox WhatsApp). "
         "Don't edit this file by hand; change `SPEC` in the script and regenerate.", "",
         "Machine-readable version: [`openapi.json`](openapi.json) (OpenAPI 3.0: open it in Swagger UI, Postman or Insomnia).", "",
         "## Conventions", "",
         "| Topic | Rule |", "|---|---|",
         "| Base URL | Same origin as the web app: `https://<your domain>` in production (nginx forwards `/api` and `/webhooks` to Flask); `http://localhost:5173` in development (Vite proxy → Flask on :5001) |",
         "| Format | JSON request and response bodies (`Content-Type: application/json`), except file upload (multipart) and the Meta verification (text) |",
         "| Authentication | Session cookie set by `POST /api/auth/login` or `/register` (HttpOnly, SameSite=Lax, 14 days) |",
         "| CSRF | Every non-GET `/api` request except login/register must send header `X-CSRF-Token: <csrf from GET /api/me>`. Missing/wrong → `400 {\"error\":\"csrf_failed\"}` |",
         "| Roles | `viewer` < `supervisor` < `admin` < `owner`. Each endpoint lists the minimum. Too low → `403 {\"error\":\"forbidden\",\"required_role\":\"…\"}` |",
         "| Not signed in | `401 {\"error\":\"not_authenticated\"}` |",
         "| Tenancy | Everything is scoped to the caller's workspace; ids from another workspace answer `404` |",
         "| Errors | `{\"error\": \"human readable message\"}` with a 4xx/5xx status. Unknown routes: `404 {\"error\":\"not_found\"}` |",
         "| Timestamps | ISO-8601 UTC strings, e.g. `2026-11-19T02:24:49Z` |",
         "| IDs | Integers |", "",
         "### Quick start with curl", "", "```bash",
         "B=http://localhost:5001",
         "curl -c jar -H 'Content-Type: application/json' -d '{\"email\":\"you@example.com\",\"password\":\"your-password\"}' $B/api/auth/login",
         "TOKEN=$(curl -s -b jar $B/api/me | python3 -c 'import sys,json;print(json.load(sys.stdin)[\"csrf\"])')",
         "curl -b jar $B/api/agents",
         "curl -b jar -H \"X-CSRF-Token: $TOKEN\" -H 'Content-Type: application/json' -d '{\"name\":\"Receptionist\"}' $B/api/agents",
         "```", "", "## Endpoints", ""]
    for g in GROUP_ORDER:
        items = [e for e in SPEC if e["group"] == g]
        L.append(f"- **{g}**: " + " · ".join(f"[`{e['method']} {e['path']}`](#{anchor(e)})" for e in items))
    L.append("")
    for g in GROUP_ORDER:
        L += [f"## {g}", ""]
        for e in [e for e in SPEC if e["group"] == g]:
            L += [f"### `{e['method']} {e['path']}`", "", e["summary"], ""]
            csrf = e.get("csrf", e["method"] != "GET" and e["path"].startswith("/api"))
            L += [f"**Role:** {ROLE_NOTE.get(e['role'], e['role'])}" + (" · **CSRF header:** required" if csrf else ""), ""]
            if e.get("params"):
                L += ["**Path parameters**", ""] + table(e["params"], ["Name", "Type", "Required", "Description"])
            if e.get("query"):
                L += ["**Query parameters**", ""] + table(e["query"], ["Name", "Type", "Required", "Description"])
            if e.get("body"):
                L += [f"**Request body** ({e.get('content', 'application/json')})", ""] + table(e["body"], ["Field", "Type", "Required", "Description"])
            if e.get("body_note"):
                L += [f"**Request body:** {e['body_note']}", ""]
            L += [f"**Returns:** {e['returns']}", ""]
            sample = ex.get((e["method"], e["path"]))
            if sample:
                req = f"{e['method']} {sample['request_url']}"
                hdr = "".join(f"\n{k}: {v}" for k, v in sample.get("headers", {}).items())
                if sample.get("request") is not None:
                    L += ["Example request:", "", "```http", req + hdr + "\nContent-Type: application/json\n\n" +
                          json.dumps(sample["request"], indent=2, ensure_ascii=False), "```", ""]
                elif e.get("content") == "multipart/form-data":
                    L += ["Example request:", "", "```http", req + "\nContent-Type: multipart/form-data\n\nfiles=@shipping.txt\nagent_ids=1", "```", ""]
                else:
                    L += ["Example request:", "", "```http", req + hdr, "```", ""]
                body = sample["response"] if isinstance(sample["response"], str) else json.dumps(sample["response"], indent=2, ensure_ascii=False)
                L += [f"Example response `{sample['status']}`:", "", "```json" if not isinstance(sample["response"], str) else "```", body, "```", ""]
            elif e.get("static_example"):
                st, body = e["static_example"]
                L += [f"Example response `{st}` (illustrative: needs a live provider):", "", "```json", json.dumps(body, indent=2), "```", ""]
            if e.get("errors"):
                L += ["**Errors:** " + " · ".join(f"`{x.split(' ', 1)[0]}` {x.split(' ', 1)[1]}" for x in e["errors"]), ""]
            L += ["---", ""]
    (DOCS / "API_BACKEND.md").write_text("\n".join(L), encoding="utf-8")


def _schema(t):
    if t.startswith("array<"):
        inner = t[6:-1]
        return {"type": "array", "items": {"type": "string", "format": "binary"} if inner == "file" else _schema(inner)}
    return {"string": {"type": "string"}, "integer": {"type": "integer"}, "boolean": {"type": "boolean"},
            "number": {"type": "number"}, "object": {"type": "object"}}.get(t, {"type": "string"})


def write_openapi(ex):
    paths = {}
    for e in SPEC:
        op = {"tags": [e["group"]], "summary": e["summary"], "description": "Returns: " + e["returns"] + f"\n\nMinimum role: {e['role']}.",
              "operationId": anchor(e).replace("-", "_"), "parameters": [], "responses": {}}
        for f in e.get("params", []):
            op["parameters"].append({"name": f["name"], "in": "path", "required": True, "description": f["desc"], "schema": _schema(f["type"])})
        for f in e.get("query", []):
            op["parameters"].append({"name": f["name"], "in": "query", "required": f["required"], "description": f["desc"], "schema": _schema(f["type"])})
        if e.get("csrf", e["method"] != "GET" and e["path"].startswith("/api")):
            op["parameters"].append({"$ref": "#/components/parameters/CSRF"})
        if e.get("body"):
            ctype = e.get("content", "application/json")
            props = {f["name"]: {**_schema(f["type"]), "description": f["desc"]} for f in e["body"]}
            req = [f["name"] for f in e["body"] if f["required"]]
            schema = {"type": "object", "properties": props, **({"required": req} if req else {})}
            sample = ex.get((e["method"], e["path"]))
            content = {"schema": schema}
            if sample and sample.get("request") is not None:
                content["example"] = sample["request"]
            op["requestBody"] = {"required": bool(req), "content": {ctype: content}}
        sample = ex.get((e["method"], e["path"]))
        if sample:
            op["responses"][str(sample["status"])] = {"description": e["returns"],
                                                      "content": {"application/json": {"example": sample["response"]}}}
        elif e.get("static_example"):
            op["responses"][str(e["static_example"][0])] = {"description": e["returns"], "content": {"application/json": {"example": e["static_example"][1]}}}
        else:
            op["responses"]["200"] = {"description": e["returns"]}
        for err in e.get("errors", []):
            code, msg = err.split(" ", 1)
            op["responses"].setdefault(code, {"description": msg, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}})
        if e["role"] not in ("public", "webhook"):
            op["security"] = [{"session": []}]
        else:
            op["security"] = []
        paths.setdefault(e["path"], {})[e["method"].lower()] = op
    doc = {"openapi": "3.0.3",
           "info": {"title": "Agentry API", "version": "1.1", "description": "Generated by scripts/gen_api_docs.py. See docs/API_BACKEND.md for conventions."},
           "servers": [{"url": "http://localhost:5001", "description": "Flask dev server"}, {"url": "http://localhost:5173", "description": "Vite dev proxy"}],
           "tags": [{"name": g} for g in GROUP_ORDER],
           "paths": paths,
           "components": {"securitySchemes": {"session": {"type": "apiKey", "in": "cookie", "name": "session",
                                                          "description": "Set by POST /api/auth/login"}},
                          "parameters": {"CSRF": {"name": "X-CSRF-Token", "in": "header", "required": True, "schema": {"type": "string"},
                                                  "description": "Value of `csrf` from GET /api/me"}},
                          "schemas": {"Error": {"type": "object", "properties": {"error": {"type": "string"}}}}}}
    (DOCS / "openapi.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


# ======================================================================================
# Frontend reference
# ======================================================================================
def parse_router():
    src = (ROOT / "frontend/src/router.js").read_text(encoding="utf-8")
    rows = []
    for m in re.finditer(r'path: "([^"]*)", (?:name: "([^"]+)", )?(?:component: \(\) => import\("([^"]+)"\)|redirect)[^\n]*', src):
        path, name, comp = m.group(1), m.group(2) or "", m.group(3) or ""
        title = re.search(r'title: "([^"]+)"', m.group(0))
        rows.append((path, name, comp.replace("./", "src/"), title.group(1) if title else ""))
    return rows


def parse_component(path: Path):
    src = path.read_text(encoding="utf-8")
    props = re.search(r"defineProps\((\{.*?\})\)", src, re.S)
    emits = re.search(r"defineEmits\((\[.*?\])\)", src, re.S)
    slots = sorted(set(re.findall(r'<slot(?: name="(\w+)")?', src)))
    return (props.group(1).replace("\n", " ") if props else "—", emits.group(1) if emits else "—",
            ", ".join(s or "default" for s in slots) or "—")


def write_frontend_md():
    import gen_endpoint_map as gem
    tmp = Path(tempfile.mkdtemp())
    app = create_app(TestConfig, INSTANCE_DIR=tmp, DATABASE_PATH=tmp / "f.db", UPLOAD_DIR=tmp / "u", LOG_LEVEL="ERROR")
    calls = gem.frontend_calls(app.url_map.bind("localhost"))
    L = ["# Frontend API reference (Vue app)", "",
         "The JavaScript interfaces inside `frontend/src`: how the app talks to the backend, shared state and helpers, "
         "reusable components, routes, and exactly which backend endpoints each screen calls. "
         "Sections 6 and 7 are **generated** by `python3 scripts/gen_api_docs.py`; the rest documents the code it sits next to.", "",
         "For the HTTP endpoints themselves (fields, responses, errors) see [API_BACKEND.md](API_BACKEND.md).", "",
         "## 1. `src/api.js`: the HTTP client", "",
         "The **only** module that calls `fetch`. Every request is same-origin (cookie session) and paths omit the `/api` prefix.", "",
         "| Export | Signature | What it does |", "|---|---|---|",
         "| `api` | `api(path, { method = \"GET\", json, form, query }) → Promise<object>` | Core call. `json` → JSON body; `form` → `FormData` (uploads); `query` → `?a=1&b=2` (empty values dropped). Adds `X-CSRF-Token` on non-GET. Resolves with the parsed JSON body. |",
         "| `get` | `get(path, query?)` | `api(path, { query })` |",
         "| `post` | `post(path, json = {})` | `api(path, { method: \"POST\", json })` |",
         "| `patch` | `patch(path, json)` | PATCH with JSON |",
         "| `put` | `put(path, json)` | PUT with JSON |",
         "| `del` | `del(path, json?)` | DELETE (optional JSON body, e.g. workspace delete confirmation) |",
         "| `ApiError` | `class ApiError extends Error { status, data }` | Thrown for every non-2xx: `message` = backend `error` text (or `Request failed (status)`), `status` = HTTP status (0 = network down), `data` = parsed body |",
         "| `apiStatus` | reactive `{ offline, detail }` | `offline` turns true when the API can't be reached: fetch failed, or a non-JSON answer came from the Vite proxy / nginx / AirPlay on :5000. `detail` says what to check. `AppShell` shows it as a banner with Retry |",
         "| `setCsrf` | `setCsrf(token)` | Stores the CSRF token (called by `loadSession`) |",
         "| `setUnauthorizedHandler` | `setUnauthorizedHandler(fn)` | Called on any 401 outside `/auth/*`; `router.js` uses it to redirect to `/login?next=…` |", "",
         "```js", "import { get, post, ApiError } from \"@/api.js\";",
         "const { agents } = await get(\"/agents\");",
         "try { await post(\"/inbox/messages/12/approve\", { text: \"Edited reply\" }); }",
         "catch (e) { if (e instanceof ApiError && e.status === 404) toast(\"Draft already sent\", true); }", "```", "",
         "## 2. `src/session.js`: who is signed in", "",
         "| Export | Type | Description |", "|---|---|---|",
         "| `session` | reactive `{ loaded, user, workspace, setup }` | `user` = `{id, name, email, role, workspace_id}` from `GET /api/me`; `null` when signed out. `setup` = `{model_ready, real_whatsapp, test_tools}`: drives the sidebar's Finish setup card and whether Sandbox/Simulate show |",
         "| `refreshSetup()` | `async` | Re-reads `setup` from `GET /api/me` (the sidebar calls it on every status refresh) |",
         "| `loadSession()` | `async → user \\| null` | Calls `GET /api/me`, stores user/workspace, sets the CSRF token. Run by the router guard on first navigation and after login |",
         "| `logout()` | `async` | `POST /api/auth/logout`, clears `session` |",
         "| `can(role)` | `(\"viewer\" \\| \"supervisor\" \\| \"admin\" \\| \"owner\") → boolean` | True if the signed-in user has at least that role. Used to hide/disable UI; the API enforces roles regardless |", "",
         "## 3. `src/utils.js`: helpers and shared state", "",
         "| Export | Signature | Description |", "|---|---|---|",
         "| `ago` | `ago(iso) → string` | \"just now\", \"5 min ago\", \"3 h ago\", weekday, or date |",
         "| `clock` | `clock(iso) → \"14:05\"` | Local time |",
         "| `dateOnly` | `dateOnly(iso) → string` | Local date, `—` for empty |",
         "| `initials` | `initials(name) → \"ML\"` | Up to 2 letters for avatars |",
         "| `colorFor` | `colorFor(seed) → hex` | Stable colour per name/phone |",
         "| `fileSize` | `fileSize(bytes) → \"1.2 MB\"` | |",
         "| `copy` | `async copy(text)` | Clipboard + toast |",
         "| `toasts` / `toast` / `fail` | `toast(message, isError?)`, `fail(error)` | Toast queue rendered by `App.vue`; `fail` shows an error's message |",
         "| `applyTheme` / `savedTheme` / `currentTheme` | `applyTheme(\"system\" \\| \"light\" \\| \"dark\")` | Theme stored in `localStorage[\"agentry-theme\"]`, applied as `<html data-theme>` |",
         "| `signals` | reactive `{ numbers, inbox, setup }` | Tiny event bus: increment to make the sidebar reload (`signals.numbers++` after changing WhatsApp numbers, `signals.inbox++` after inbox actions, `signals.setup++` after model settings/keys change) |", "",
         "## 4. `src/composables/useSettingsForm.js`", "",
         "`useSettingsForm(loadFn, saveFn) → { form, dirty, saving, save, discard, ready, reload }`", "",
         "| Return | Description |", "|---|---|",
         "| `form` | reactive object filled with what `loadFn()` returns; bind inputs to it |",
         "| `dirty` | true when `form` differs from the last loaded/saved state → shows `<SaveBar>` |",
         "| `save()` | calls `saveFn(form)`, then marks clean and toasts \"Saved\" |",
         "| `discard()` | restores the last loaded/saved state |",
         "| `ready` / `reload()` | loaded flag / load again |", "",
         "Also warns before leaving the page (route change or tab close) with unsaved edits.", "",
         "```js", "const { form, dirty, saving, save, discard, ready } = useSettingsForm(",
         "  () => get(\"/settings/whatsapp\"),", "  (f) => patch(\"/settings/whatsapp\", f),", ");", "```", "",
         "## 5. Components (`src/components/`)", "",
         "| Component | Props | Events | Slots | Purpose |", "|---|---|---|---|---|"]
    purpose = {"AppShell": "Page frame: sidebar (nav, Finish setup card, number status, user, theme, sign-out), API-offline banner + `<RouterView>`. Pages may teleport extra sidebar content to `#side-extra`",
               "SettingsLayout": "Settings sub-menu + title/lead from route meta + `<RouterView>`",
               "AppIcon": "Inline stroke icon by name (see the `paths` map in the file)",
               "ModelPicker": "Model dropdown filled from `GET /settings/providers/<p>/models`, with “Other (type a name)…” for any model id; use with `v-model`",
               "BrandMark": "The AI Wonder Lab logo mark (ring + breathing mint core), shared with the mother project",
               "ToggleSwitch": "Accessible on/off switch (`role=switch`), use with `v-model`",
               "SegControl": "Segmented buttons (radio group or tabs), use with `v-model`",
               "ChipsInput": "Editable list of chips (Enter adds, × removes), use with `v-model`",
               "AppDialog": "Native `<dialog>` modal, open with `v-model:open`",
               "SettingsGroup": "Titled card section on settings pages", "SettingsRow": "Label + control row inside a SettingsGroup",
               "SaveBar": "Sticky \"unsaved changes\" bar (only shown to admins)"}
    for f in sorted((ROOT / "frontend/src/components").glob("*.vue")):
        p, e, s = parse_component(f)
        L.append(f"| `{f.stem}` | `{p.strip()}` | `{e}` | {s} | {purpose.get(f.stem, '')} |".replace("|`—`|", "| — |"))
    L += ["", "## 6. Routes (`src/router.js`) *(generated)*", "",
          "All routes except `/login` and `/register` require a session; the guard redirects to `/login?next=<path>`.", "",
          "| Path | Name | View | Title |", "|---|---|---|---|"]
    in_settings = False
    for path, name, comp, title in parse_router():
        if path.startswith("/"):
            full = path
        elif name.startswith("settings-") or (in_settings and not name):
            full = "/settings" + (f"/{path}" if path else "")
        else:
            full = "/" + path
        if not path and not name and not comp:          # the settings index redirect
            in_settings = True
            full = "/settings"
        note = {"/settings": "redirect → `/settings/models`", "/:pathMatch(.*)*": "redirect → `/` (unknown URLs)"}.get(full)
        L.append(f"| `{full}` | {name or '—'} | {note or ('`' + comp + '`')} | {title} |")
    L += ["", "## 7. What each screen calls *(generated)*", "",
          "Every backend call in the Vue code, the function it's made from, and the endpoint's reference entry. "
          "`make test` fails if any of these doesn't match a real route.", ""]
    by_screen = {}
    for c in calls:
        by_screen.setdefault(c["screen"], []).append(c)
    order = ["Login / Register", "Session (every page)", "Sidebar (every page)", "Playground", "WhatsApp", "Inbox", "Knowledge"] + \
        sorted(s for s in by_screen if s.startswith("Settings"))
    for scr in [s for s in order if s in by_screen]:
        L += [f"### {scr}", "", f"`{by_screen[scr][0]['file']}`", "", "| Function | Request | Reference |", "|---|---|---|"]
        seen = set()
        for c in by_screen[scr]:
            key = (c["action"], c["method"], c["path"])
            if key in seen:
                continue
            seen.add(key)
            tmpl = next((e for e in SPEC if e["method"] == c["method"] and re.fullmatch(
                re.sub(r"\\\{\w+\\\}", r"[^/]+", re.escape(e["path"])), re.sub(r"<[^>]+>", "1", c["path"]).split("?")[0])), None)
            ref = f"[`{tmpl['method']} {tmpl['path']}`](API_BACKEND.md#{anchor(tmpl)})" if tmpl else "—"
            L.append(f"| `{c['action']}` | `{c['method']} {c['path'].replace('<', '&lt;').replace('>', '&gt;')}` | {ref} |")
        L.append("")
    L += ["## 8. Conventions", "",
          "- Call the backend only through `api.js`; never `fetch` directly.",
          "- Hide controls the user can't use with `can(role)`, but treat a `403` as possible anyway.",
          "- Show errors with `fail(e)`; success with `toast(\"…\")`.",
          "- After changing numbers or chats, bump `signals.numbers` / `signals.inbox`.",
          "- No `v-html` with data. Colours only via CSS variables in `styles/app.css` (both themes).",
          "- New screen: add a route in `router.js`, a link in `AppShell.vue` (or `SettingsLayout.vue`), then run `python3 scripts/gen_api_docs.py`.", ""]
    (DOCS / "API_FRONTEND.md").write_text("\n".join(L), encoding="utf-8")


def main():
    tmp = Path(tempfile.mkdtemp())
    app = create_app(TestConfig, INSTANCE_DIR=tmp, DATABASE_PATH=tmp / "c.db", UPLOAD_DIR=tmp / "u", LOG_LEVEL="ERROR")
    problems = check(app)
    if "--check" in sys.argv:
        print("\n".join(problems) or "OK: every route is documented and every request field is described")
        sys.exit(1 if problems else 0)
    if problems:
        print("Fix the spec first:\n" + "\n".join(problems))
        sys.exit(1)
    _, ex = capture()
    missing = [f"{e['method']} {e['path']}" for e in SPEC if (e["method"], e["path"]) not in ex and not e.get("static_example")]
    write_backend_md(ex)
    write_openapi(ex)
    write_frontend_md()
    print(f"wrote docs/API_BACKEND.md, docs/openapi.json, docs/API_FRONTEND.md — {len(SPEC)} endpoints, "
          f"{len(ex)} real examples" + (f"; no example for: {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
