# Code map

```
agentry/
├── frontend/                   Vue 3 + Vite single-page app (see frontend/README.md)
│   ├── src/main.js, App.vue    bootstrap, toasts
│   ├── src/router.js           routes + auth guard + 401 handler
│   ├── src/api.js              the ONLY fetch wrapper (cookie, CSRF header, ApiError)
│   ├── src/session.js          signed-in user, can(role)
│   ├── src/utils.js            formatting, toasts, theme, copy(), signals
│   ├── src/composables/useSettingsForm.js   settings load/dirty/save/discard
│   ├── src/components/         AppShell, SettingsLayout, AppIcon, ToggleSwitch, SegControl, ChipsInput,
│   │                           AppDialog, SettingsGroup, SettingsRow, SaveBar
│   ├── src/views/              AuthView, PlaygroundView, WhatsAppView, InboxView, KnowledgeView
│   ├── src/views/settings/     General, Models, Agents, WhatsApp, Team, Billing, Security
│   ├── src/styles/app.css      design tokens (dark + light) + component classes
│   ├── scripts/check.py        static checks that run without npm
│   ├── vite.config.js          dev proxy /api → :5001
│   ├── nginx.conf, Dockerfile  production: build → nginx (SPA + reverse proxy)
├── wsgi.py                     API entry point (loads .env, create_app())
├── app/                        Flask JSON API — serves no HTML
│   ├── __init__.py             create_app(): config, migrate, hooks, blueprints, worker, CLI (purge, reindex, create-owner)
│   ├── config.py               every env var + defaults; TestConfig
│   ├── db.py                   get_db(), query/insert/update helpers, migrate()
│   ├── security.py             encrypt/decrypt (Fernet), load_user, login_required, role_required, CSRF
│   ├── worker.py               enqueue() → thread pool | inline
│   ├── webhooks.py             /webhooks/... inbound from WhatsApp providers
│   ├── migrations/001_initial.sql   full schema; add 002_*.sql for changes
│   ├── api/                    one module per screen: auth, playground, agents, knowledge, whatsapp, inbox, settings
│   ├── services/               business logic: conversations ★, agents, knowledge, connections, settings
│   ├── llm/                    providers.py (OpenAI-shape, Anthropic, Gemini, Mock), router.py (selection + fallback)
│   ├── knowledge/              extract.py (files/URL → text), retrieval.py (chunking + BM25)
│   └── whatsapp/adapters.py    Evolution, MetaCloud, Generic, Sandbox
├── tests/                      pytest: auth/permissions, conversations, units
├── docker-compose.yml          web + api (+ optional Evolution profile); see docs/DEPLOY_VPS.md
├── scripts/init-env.sh         creates .env with fresh secrets;  scripts/backup.sh  database backup (Docker)
├── .github/workflows/ci.yml    tests, API-doc check, Vue build, Docker build + health check
├── scripts/gen_api_docs.py     generates docs/API_BACKEND.md, openapi.json, API_FRONTEND.md (SPEC = endpoint descriptions)
├── scripts/gen_endpoint_map.py checks every Vue API call matches a Flask route (used by tests + gen_api_docs)
├── scripts/screenshot_pages.py Playwright: capture all pages in both themes
├── docs/                       you are here
├── Dockerfile (API), docker-compose.yml (web + api + Evolution), Makefile, requirements*.txt, .env.example
```

**Where do I change…**

| …this? | File |
|---|---|
| What the agent is told (rules, tone, source format) | `services/agents.py::build_messages` |
| Order of checks before replying | `services/conversations.py::respond` |
| Starter agents for new workspaces | `services/agents.py::TEMPLATES` |
| A setting's default | `services/settings.py` (`*_DEFAULTS`) |
| Colours / theme | `frontend/src/styles/app.css` token blocks (top of file) |
| Supported upload types | `knowledge/extract.py::SUPPORTED` (+ `accept=` in `frontend/src/views/KnowledgeView.vue`) |
| A screen's layout or behaviour | `frontend/src/views/<Screen>View.vue` |
| A new page / route | `frontend/src/router.js` (+ link in `components/AppShell.vue` or `SettingsLayout.vue`) |
