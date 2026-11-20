# Data model

The schema is in `app/migrations/001_initial.sql` (that file is authoritative). Conventions:
integer ids, ISO-8601 UTC text timestamps (`utcnow()`), JSON stored as TEXT, every tenant table has
`workspace_id` with `ON DELETE CASCADE`, so deleting a workspace removes everything it owns.

```
workspaces 1─* users            1─* invites
           1─* agents  *─* knowledge_files (agent_files)   knowledge_files 1─* chunks
           1─* provider_keys
           1─* wa_connections 1─* chats *─1 contacts
                                  chats 1─* messages
           1─* playground_sessions 1─* playground_messages
           1─* usage_events, audit_log
```

| Table | Purpose | Notes |
|---|---|---|
| `workspaces` | Tenant | JSON columns `llm_settings`, `whatsapp_settings`, `agent_defaults`, `security_settings`, `business_hours`; defaults merged in code (`services/settings.py`), so adding a setting needs no migration |
| `users` | Login | `email` globally unique, `role` CHECK owner/admin/supervisor/viewer, werkzeug password hash |
| `invites` | Pending team invites | `token` in the link; `accepted_at` set on join |
| `agents` | AI agents | `instructions` (system prompt), `model_override` JSON `{provider, model}` or NULL, `active` |
| `provider_keys` | BYOK API keys | `api_key_enc` Fernet ciphertext, `last4` for display; one per (workspace, provider) |
| `knowledge_files` | Uploaded files / URL / Q&A | `status` pending→indexing→ready/failed, `error` is shown in the UI |
| `agent_files` | Which agent may use which file | Retrieval only searches files linked to the chat's agent |
| `chunks` | Searchable text pieces | `locator` is the citation shown to users ("p.2", sheet name) |
| `wa_connections` | WhatsApp numbers | `provider` CHECK evolution/meta_cloud/generic/sandbox; `config_enc` = Fernet(JSON credentials); `webhook_token` = secret URL segment; per-number `default_agent_id`/`default_mode` |
| `contacts` | Customers | `wa_id` digits-only phone, unique per workspace; `opted_out` |
| `chats` | Contact × number | `agent_id`, `mode` auto/draft/off, `handoff_active` ("Needs you"), `rules` JSON, `unread_count`, preview |
| `messages` | Everything in a chat | `direction` in/out/system; `author` customer/agent/human/system; `status` received/draft/queued/sent/failed/discarded/note; partial unique index on `(chat_id, provider_message_id)` dedupes provider retries |
| `playground_*` | Playground history | Per user; never sent anywhere |
| `usage_events` | Metering | `agent_reply`, `platform_tokens`, `byok_tokens`; summed per month in `/api/usage` |
| `audit_log` | Who changed what | Written by `settings.audit()` from API handlers |
| `schema_migrations` | Applied migration files | Managed by `db.migrate()` |

## Message status lifecycle
```
inbound:  received
outbound: draft ──approve──▶ sent | failed
          draft ──discard──▶ discarded (hidden in UI, kept for audit)
          (auto) ───────────▶ sent | failed
system:   note
```

## Changing the schema
Add `app/migrations/002_<what>.sql`. It runs automatically at the next boot, once, and files are
applied in name order. `executescript` does not wrap a file in one transaction, so start a
multi-statement migration with `BEGIN;` and end it with `COMMIT;`. Never edit an applied migration. SQLite can't drop CHECK constraints in place: to widen
one (e.g. a new provider), create the new table, copy, drop, rename (see MAINTENANCE.md).
