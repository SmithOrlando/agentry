# Configuration

All settings are environment variables (a `.env` file is loaded by `wsgi.py`). Defaults are for
local development. Source of truth: `app/config.py`.

## Must set in production
| Variable | Why |
|---|---|
| `SECRET_KEY` | Signs session cookies. Long random string. Changing it logs everyone out. |
| `ENCRYPTION_KEY` | Fernet key that encrypts API keys and WhatsApp credentials. Generate: `python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`. **Back it up. Losing it makes stored keys unreadable** (users would re-enter them). If unset, a key is generated into `INSTANCE_DIR/encryption.key` (OK for dev, risky in containers without a volume). |
| `PUBLIC_BASE_URL` | Public https URL of the site (the nginx `web` container); used to build webhook URLs given to WhatsApp providers. |
| `FRONTEND_URL` | Where people open the Vue app; used in invite links. Same as `PUBLIC_BASE_URL` behind nginx. |
| `SESSION_COOKIE_SECURE=true` | Cookies only over HTTPS. |
| `PLATFORM_LLM_*` | The hidden default model (below). |

## All variables
| Variable | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | `dev-insecure-change-me` | see above |
| `INSTANCE_DIR` | `./instance` | Runtime data folder |
| `DATABASE_PATH` | `INSTANCE_DIR/agentry.db` | SQLite file |
| `UPLOAD_DIR` | `INSTANCE_DIR/uploads` | Knowledge files, one subfolder per workspace |
| `MAX_UPLOAD_MB` | `20` | Request size limit (413 above it) |
| `PUBLIC_BASE_URL` | `http://localhost:5001` | see above |
| `FRONTEND_URL` | `http://localhost:5173` | see above (Vite dev server by default) |
| `ENCRYPTION_KEY` | generated file | see above |
| `ALLOW_REGISTRATION` | `true` | `false` = only invites (use `flask create-owner` for the first user) |
| `SESSION_COOKIE_SECURE` | `false` | |
| `LOG_LEVEL` | `INFO` | |
| `PLATFORM_LLM_PROVIDER` | empty (none) | `openai`, `anthropic`, `gemini`, `deepseek`, `qwen`, `openai_compatible`. Empty = no hidden default: every workspace adds its own key |
| `PLATFORM_LLM_MODEL` | empty | Model id for that provider |
| `PLATFORM_LLM_API_KEY` | — | Key for that provider |
| `PLATFORM_LLM_BASE_URL` | provider default | Needed for `openai_compatible`; optional otherwise (proxies) |
| `LLM_TIMEOUT_SECONDS` | `60` | Per model call |
| `ENABLE_TEST_TOOLS` | `false` | Developers only: Sandbox numbers, the Simulate button and the placeholder `mock` model. **Never on a public server** |
| `META_GRAPH_VERSION` | `v24.0` | Graph API version for Cloud API sends. Meta retires versions about 2 years after release: bump it when they deprecate |
| `WHATSAPP_HTTP_TIMEOUT` | `20` | Per provider call |
| `REPLY_DELAYS_ENABLED` | `true` | Human-like random wait before auto replies (`false` in dev/tests) |
| `WORKER_THREADS` | `4` | Background job threads (replies + indexing in parallel) |
| `WORKER_MODE` | `thread` | `thread` or `sync` (inline; tests) |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `900` / `120` | Characters per knowledge chunk. Run `flask reindex` after changing |
| `RETRIEVAL_TOP_K` | `4` | Chunks put in each prompt |
| `ALLOW_PRIVATE_URL_FETCH` | `false` | Allow "Add a web page" to fetch internal IPs (SSRF guard off). Keep false |

## Settings that live in the database (per workspace, edited in the UI)
Defaults are in `app/services/settings.py`: model source/provider/model/temperature/max tokens/
fallback; WhatsApp defaults and sending limits; opt-out and handoff keywords; never-talk-about
topics; reply signature; business hours; away message; retention days.

## Frontend
The Vue app has no runtime configuration: it always calls `/api` on its own origin.
For development, `AGENTRY_API` (default `http://localhost:5001`) tells the Vite dev proxy where Flask runs.
