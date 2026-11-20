# Maintenance & extension guide

## Conventions
- **Layers:** `api/*` validates input, checks the role and scopes to the workspace, then calls `services/*`. Services never touch `request`. Adapters and providers never touch the DB.
- **SQL:** parameterised only (`?`), via the `db.py` helpers. Column names are never built from user input (the `update()` keys come from code-side allow-lists).
- **Errors:** providers raise `LLMError`, adapters raise `WhatsAppError`, extractors raise `ExtractionError`. Each has a human-readable message the UI can show. Unexpected exceptions are logged with `logger.exception` and turned into a short message.
- **Background work:** only through `worker.enqueue()`. Jobs must be idempotent (safe to run twice).
- **Frontend (Vue):** see `frontend/README.md`. API calls only via `api.js`, no `v-html` with data, colours only as CSS variables, `can(role)` for role-gated UI, `useSettingsForm` for settings pages.
- **Tests:** `make test` must stay green and offline. New behaviour in the pipeline needs a test in `tests/test_conversations.py`.

## How to…

### Add a database change
Create `app/migrations/002_short_name.sql`; it applies at next boot. Never edit an applied file.

**Widening a CHECK constraint (SQLite):**
```sql
BEGIN;
CREATE TABLE provider_keys_new ( …same columns, new CHECK list… );
INSERT INTO provider_keys_new SELECT * FROM provider_keys;
DROP TABLE provider_keys;
ALTER TABLE provider_keys_new RENAME TO provider_keys;
COMMIT;
```

### Add a setting
Add the key with its default to the right `*_DEFAULTS` dict in `services/settings.py`, then add the
control to the matching `frontend/src/views/settings/*.vue` (bound to `form.<key>`; `useSettingsForm` saves it). No migration needed.

### Add an LLM provider → see LLM_PROVIDERS.md › Adding a provider.

### Add a WhatsApp transport
Subclass `Adapter` in `whatsapp/adapters.py` (`send_text`, `parse_webhook`, optionally `setup/qr/state`),
add it to `ADAPTERS` and `connections.REQUIRED`, widen the `wa_connections.provider` CHECK, add it to
`PROVIDERS` and `FIELDS` in `frontend/src/views/WhatsAppView.vue`, and add a parse test.

### After changing routes or screens
Update the endpoint's entry in `SPEC` in `scripts/gen_api_docs.py`, then run `make api-docs` to regenerate docs/API_BACKEND.md, docs/openapi.json and docs/API_FRONTEND.md. `make test` fails if a route is undocumented, a handler reads a field the spec doesn't list (`tests/test_api_docs.py`), or a screen calls an endpoint that doesn't exist (`tests/test_endpoint_map.py`).

### Add a screen
Create `frontend/src/views/XView.vue`, add a route in `router.js` (under the `/` shell route so it gets
the sidebar), add a `RouterLink` in `components/AppShell.vue`, and add the API endpoints it needs in
`app/api/`. Run `python3 frontend/scripts/check.py` and `npm run build`.

### Host the frontend on a different domain than the API
Today they share one origin. To split them: enable CORS with credentials on the API (allow-list the
frontend origin), set `SESSION_COOKIE_SAMESITE=None` + `Secure`, and keep CSRF as is. Or switch to
token auth. Prefer keeping one origin.

### Change how agents talk
`services/agents.py::build_messages`. Keep `HANDOFF_TOKEN` handling intact. Test in the Playground
(channel "playground") and via a Sandbox number (channel "whatsapp", needs `ENABLE_TEST_TOOLS=true` locally); they use slightly different rules.

## Scaling path (do these in order, only when needed)
| Symptom | Step |
|---|---|
| Replies slow under load | Raise `WORKER_THREADS` and gunicorn `--threads` |
| Need >1 app server / zero-downtime deploys, or "database is locked" | **Move to Postgres:** the SQL is portable except `INSERT OR IGNORE` / `INSERT OR REPLACE` (in `conversations._upsert_*` and `api/settings.team_invite`; use `ON CONFLICT DO NOTHING / DO UPDATE`), `PRAGMA`s in `db._connect`, and the partial unique index (Postgres supports it). Swap `db._connect` for psycopg and change `?` to `%s` in one place by wrapping `query/execute`. |
| Jobs lost on restart / multiple processes | **Replace `worker.py`** with RQ or Celery + Redis, keeping `enqueue(fn, *args)` |
| Inbox polling load | Server-Sent Events from a `/api/inbox/stream` endpoint consumed by `InboxView.vue` (replace the 5 s `setInterval`), or websockets |
| Retrieval misses paraphrased questions | **Embeddings:** add an `embedding` column (pgvector), embed chunks in `index_file`, keep `retrieval.search()`'s signature, and blend BM25 + vector scores |

## Known limitations (v1)
- Text messages only: incoming media without a caption is ignored, and the agent never sends media.
- No proactive/template messages (Cloud API templates, broadcasts).
- No OCR for scanned PDFs; website source is a single page, not a crawl.
- Business hours use one schedule per workspace (no holidays).
- Billing page shows usage only; no payment provider.
- No email sending (invites are copy-paste links).
- Login has no rate limit, 2FA or SSO (SECURITY.md).

## Suggested roadmap
1. Login rate limiting + 2FA (security)
2. Postgres + RQ (unlocks horizontal scaling)
3. Cloud API message templates + 24 h window awareness
4. Media in/out (images, voice notes → transcription)
5. Embedding retrieval + OCR
6. Agent tools (order lookup in the customer's systems) with per-tool permissions
7. Real-time inbox (SSE) and notifications for "Needs you"
8. Stripe billing on top of `usage_events`
