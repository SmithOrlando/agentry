# Handover: start here

Welcome. This page gets you from zero to confidently changing the system in about a day.

## Day 1 checklist
- [ ] Python 3.9+ (3.11+ recommended) and Node 20+ installed.
- [ ] Read README.md, then ARCHITECTURE.md (with `architecture.png` and `reply-pipeline.png` open).
- [ ] `make install && make test`: 35 backend tests plus frontend static checks, no network needed. Then `make check` (Vue production build).
- [ ] Put `ENABLE_TEST_TOOLS=true` in `.env` (local only), `make dev` (API :5001 + Vue :5173), open http://localhost:5173 and create a workspace. Add a **Sandbox** number on the WhatsApp page.
- [ ] Read `frontend/README.md` and `frontend/src/router.js` + `api.js`: that's the whole frontend skeleton.
- [ ] Walk every screen. On the Sandbox number, use **Simulate** to send "I want a human" and watch the chat go to **Needs you** in the Inbox. Then send "STOP" from another number.
- [ ] Switch a chat to **Draft first**, simulate a message, edit and **Approve & send** the draft.
- [ ] Upload a PDF in **Knowledge**, ask about it in the **Playground**, and check the source chip.
- [ ] Read `services/conversations.py::respond`. It's the heart of the product, about 70 lines.
- [ ] Skim CODE_MAP.md so you know where everything lives, and API_BACKEND.md / API_FRONTEND.md for the API (which screen calls which endpoint is in API_FRONTEND.md §7).
- [ ] Get production access: the `.env` values (especially `ENCRYPTION_KEY`), the server, Evolution's admin key, the Meta app, backups.

## The five things most likely to bite you
1. **`ENCRYPTION_KEY` must never change or get lost.** Every stored API key and WhatsApp credential depends on it.
2. **One gunicorn worker.** More workers = lost background jobs and SQLite lock errors. Scale with threads.
3. **Evolution API upgrades can change webhook payloads.** Pin the image version, and re-test with a real phone after upgrading.
4. **`PUBLIC_BASE_URL` must be the public HTTPS URL**, or providers can't deliver messages (webhook URLs are built from it).
   Frontend and API must stay on **one origin** (nginx in prod, the Vite proxy in dev), because cookie auth has no CORS.
5. **There is no AI model by default.** A fresh deploy without `PLATFORM_LLM_*` can't reply until a workspace adds its own key
   (Settings › Models); the app says so. `ENABLE_TEST_TOOLS` (Sandbox, Simulate, the "(mock)" placeholder model) must stay off in production.

## Ownership map
| Area | Where | Tests |
|---|---|---|
| Reply logic | `services/conversations.py`, `services/agents.py` | `tests/test_conversations.py` |
| Model calls | `llm/` | `tests/test_units.py` (`provider_request_shapes`, `router_falls_back`) |
| WhatsApp | `whatsapp/adapters.py`, `webhooks.py`, `services/connections.py` | `test_units.py` (parsers, signature), `test_conversations.py` (Evolution setup flow) |
| Knowledge | `knowledge/`, `services/knowledge.py` | `test_units.py` (extract, chunk, tokenize) |
| Auth & tenancy | `security.py`, `api/auth.py` | `tests/test_auth_and_permissions.py` |
| UI (Vue) | `frontend/src/` | `frontend/scripts/check.py` (static), `npm run build`, `scripts/screenshot_pages.py` (visual, dark + light) |

## What is deliberately *not* built yet
See MAINTENANCE.md › Known limitations and Roadmap. Nothing in the UI pretends to work when it doesn't:
unbuilt features (2FA, payments, email invites) were left out or labelled.

## Original design
The approved UI design (dark and light, 11 screens) is the canvas artifact "Agent Builder Platform – UI Design".
The CSS tokens in `frontend/src/styles/app.css` match it.
