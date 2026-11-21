# Backend API reference

Every HTTP endpoint the Flask app serves. **Generated** by `python3 scripts/gen_api_docs.py` from the code: example responses are real output captured from a test database (mock model, sandbox WhatsApp). Don't edit this file by hand; change `SPEC` in the script and regenerate.

Machine-readable version: [`openapi.json`](openapi.json) (OpenAPI 3.0: open it in Swagger UI, Postman or Insomnia).

## Conventions

| Topic | Rule |
|---|---|
| Base URL | Same origin as the web app: `https://<your domain>` in production (nginx forwards `/api` and `/webhooks` to Flask); `http://localhost:5173` in development (Vite proxy → Flask on :5001) |
| Format | JSON request and response bodies (`Content-Type: application/json`), except file upload (multipart) and the Meta verification (text) |
| Authentication | Session cookie set by `POST /api/auth/login` or `/register` (HttpOnly, SameSite=Lax, 14 days) |
| CSRF | Every non-GET `/api` request except login/register must send header `X-CSRF-Token: <csrf from GET /api/me>`. Missing/wrong → `400 {"error":"csrf_failed"}` |
| Roles | `viewer` < `supervisor` < `admin` < `owner`. Each endpoint lists the minimum. Too low → `403 {"error":"forbidden","required_role":"…"}` |
| Not signed in | `401 {"error":"not_authenticated"}` |
| Tenancy | Everything is scoped to the caller's workspace; ids from another workspace answer `404` |
| Errors | `{"error": "human readable message"}` with a 4xx/5xx status. Unknown routes: `404 {"error":"not_found"}` |
| Timestamps | ISO-8601 UTC strings, e.g. `2026-11-19T02:24:49Z` |
| IDs | Integers |

### Quick start with curl

```bash
B=http://localhost:5001
curl -c jar -H 'Content-Type: application/json' -d '{"email":"you@example.com","password":"your-password"}' $B/api/auth/login
TOKEN=$(curl -s -b jar $B/api/me | python3 -c 'import sys,json;print(json.load(sys.stdin)["csrf"])')
curl -b jar $B/api/agents
curl -b jar -H "X-CSRF-Token: $TOKEN" -H 'Content-Type: application/json' -d '{"name":"Receptionist"}' $B/api/agents
```

## Endpoints

- **Auth**: [`POST /api/auth/register`](#post-api-auth-register) · [`POST /api/auth/login`](#post-api-auth-login) · [`POST /api/auth/logout`](#post-api-auth-logout) · [`POST /api/auth/password`](#post-api-auth-password) · [`GET /api/me`](#get-api-me)
- **Playground**: [`GET /api/playground/sessions`](#get-api-playground-sessions) · [`POST /api/playground/sessions`](#post-api-playground-sessions) · [`GET /api/playground/sessions/{sid}`](#get-api-playground-sessions-sid) · [`DELETE /api/playground/sessions/{sid}`](#delete-api-playground-sessions-sid) · [`POST /api/playground/sessions/{sid}/messages`](#post-api-playground-sessions-sid-messages)
- **Agents**: [`GET /api/agents`](#get-api-agents) · [`POST /api/agents`](#post-api-agents) · [`PATCH /api/agents/{aid}`](#patch-api-agents-aid) · [`DELETE /api/agents/{aid}`](#delete-api-agents-aid)
- **Knowledge**: [`GET /api/knowledge/files`](#get-api-knowledge-files) · [`POST /api/knowledge/files`](#post-api-knowledge-files) · [`POST /api/knowledge/text`](#post-api-knowledge-text) · [`POST /api/knowledge/url`](#post-api-knowledge-url) · [`PATCH /api/knowledge/files/{fid}`](#patch-api-knowledge-files-fid) · [`POST /api/knowledge/files/{fid}/reindex`](#post-api-knowledge-files-fid-reindex) · [`DELETE /api/knowledge/files/{fid}`](#delete-api-knowledge-files-fid)
- **WhatsApp numbers**: [`GET /api/whatsapp/connections`](#get-api-whatsapp-connections) · [`POST /api/whatsapp/connections`](#post-api-whatsapp-connections) · [`PATCH /api/whatsapp/connections/{cid}`](#patch-api-whatsapp-connections-cid) · [`DELETE /api/whatsapp/connections/{cid}`](#delete-api-whatsapp-connections-cid) · [`GET /api/whatsapp/connections/{cid}/qr`](#get-api-whatsapp-connections-cid-qr) · [`POST /api/whatsapp/connections/{cid}/refresh`](#post-api-whatsapp-connections-cid-refresh) · [`POST /api/whatsapp/connections/{cid}/simulate`](#post-api-whatsapp-connections-cid-simulate)
- **Inbox**: [`GET /api/inbox/chats`](#get-api-inbox-chats) · [`GET /api/inbox/chats/{cid}`](#get-api-inbox-chats-cid) · [`PATCH /api/inbox/chats/{cid}`](#patch-api-inbox-chats-cid) · [`DELETE /api/inbox/chats/{cid}`](#delete-api-inbox-chats-cid) · [`POST /api/inbox/chats/{cid}/messages`](#post-api-inbox-chats-cid-messages) · [`POST /api/inbox/chats/{cid}/takeover`](#post-api-inbox-chats-cid-takeover) · [`POST /api/inbox/chats/{cid}/resume`](#post-api-inbox-chats-cid-resume) · [`POST /api/inbox/chats/{cid}/ask-agent`](#post-api-inbox-chats-cid-ask-agent) · [`POST /api/inbox/messages/{mid}/approve`](#post-api-inbox-messages-mid-approve) · [`POST /api/inbox/messages/{mid}/discard`](#post-api-inbox-messages-mid-discard)
- **Settings**: [`GET /api/settings/general`](#get-api-settings-general) · [`PATCH /api/settings/general`](#patch-api-settings-general) · [`DELETE /api/settings/workspace`](#delete-api-settings-workspace) · [`GET /api/settings/llm`](#get-api-settings-llm) · [`PATCH /api/settings/llm`](#patch-api-settings-llm) · [`PUT /api/settings/providers/{provider}`](#put-api-settings-providers-provider) · [`DELETE /api/settings/providers/{provider}`](#delete-api-settings-providers-provider) · [`GET /api/settings/providers/{provider}/models`](#get-api-settings-providers-provider-models) · [`POST /api/settings/providers/{provider}/test`](#post-api-settings-providers-provider-test) · [`GET /api/settings/whatsapp`](#get-api-settings-whatsapp) · [`PATCH /api/settings/whatsapp`](#patch-api-settings-whatsapp) · [`GET /api/settings/agent-defaults`](#get-api-settings-agent-defaults) · [`PATCH /api/settings/agent-defaults`](#patch-api-settings-agent-defaults) · [`GET /api/settings/security`](#get-api-settings-security) · [`PATCH /api/settings/security`](#patch-api-settings-security)
- **Team**: [`GET /api/team`](#get-api-team) · [`POST /api/team/invites`](#post-api-team-invites) · [`DELETE /api/team/invites/{iid}`](#delete-api-team-invites-iid) · [`PATCH /api/team/members/{uid}`](#patch-api-team-members-uid) · [`DELETE /api/team/members/{uid}`](#delete-api-team-members-uid)
- **Usage & audit**: [`GET /api/usage`](#get-api-usage) · [`GET /api/audit`](#get-api-audit) · [`GET /api/export`](#get-api-export)
- **Webhooks**: [`POST /webhooks/{provider}/{conn_id}/{token}`](#post-webhooks-provider-conn-id-token) · [`GET /webhooks/meta/{conn_id}`](#get-webhooks-meta-conn-id) · [`POST /webhooks/meta/{conn_id}`](#post-webhooks-meta-conn-id)
- **Service**: [`GET /healthz`](#get-healthz) · [`GET /`](#get)

## Auth

### `POST /api/auth/register`

Create a workspace and its owner (or join a workspace with an invite).

**Role:** none (public)

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `email` | string | yes | Login email (unique across the system) |
| `password` | string | yes | At least 8 characters |
| `name` | string | no | Display name (defaults to the part of the email before @) |
| `workspace` | string | no | Business name for the new workspace (ignored with an invite) |
| `invite_token` | string | no | Token from an invite link; joins that workspace with the invited role |

**Returns:** `{ok: true}` and a session cookie. New workspaces get four starter agents.

Example request:

```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "owner@example.com",
  "password": "correct-horse",
  "name": "Ana Owner",
  "workspace": "Andes Coffee Co."
}
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `400` invalid email/short password, or invalid/used invite · `403` registration closed (`ALLOW_REGISTRATION=false`) · `409` email already registered

---

### `POST /api/auth/login`

Sign in. Sets the session cookie.

**Role:** none (public)

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `email` | string | yes | Login email |
| `password` | string | yes | Password |

**Returns:** `{ok: true}` and a session cookie. Call `GET /api/me` next for the CSRF token.

Example request:

```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "owner@example.com",
  "password": "correct-horse"
}
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `401` wrong email or password

---

### `POST /api/auth/logout`

Sign out (clears the session).

**Role:** none (public) · **CSRF header:** required

**Returns:** `{ok: true}`

Example request:

```http
POST /api/auth/logout
```

Example response `200`:

```json
{
  "ok": true
}
```

---

### `POST /api/auth/password`

Change your own password.

**Role:** any signed-in user · **CSRF header:** required

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `current` | string | yes | Current password |
| `new` | string | yes | New password, at least 8 characters |

**Returns:** `{ok: true}`

Example request:

```http
POST /api/auth/password
Content-Type: application/json

{
  "current": "correct-horse",
  "new": "correct-horse-2"
}
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `400` new password too short · `403` current password wrong

---

### `GET /api/me`

Who is signed in, their workspace, and the CSRF token for write requests.

**Role:** any signed-in user

**Returns:** `user` {id, workspace_id, email, name, role}, `workspace` {id, name}, `csrf` (send as `X-CSRF-Token`), `setup` {model_ready: false while replies come from the placeholder model, real_whatsapp: false until a real (non-sandbox) number exists, test_tools: whether Sandbox/Simulate are enabled} (drives the sidebar's Finish setup card).

Example request:

```http
GET /api/me
```

Example response `200`:

```json
{
  "csrf": "gBGP2rEX0iBHXAd7s4Yo6uZngFil2G8XuLsVX97EXBE",
  "setup": {
    "model_ready": false,
    "real_whatsapp": false,
    "test_tools": true
  },
  "user": {
    "email": "owner@example.com",
    "id": 1,
    "name": "Ana Owner",
    "role": "owner",
    "workspace_id": 1
  },
  "workspace": {
    "id": 1,
    "name": "Andes Coffee Co."
  }
}
```

---

## Playground

### `GET /api/playground/sessions`

Your recent Playground chats (max 30, newest first).

**Role:** supervisor

**Returns:** `sessions[]` {id, title, agent_id, updated_at}

Example request:

```http
GET /api/playground/sessions
```

Example response `200`:

```json
{
  "sessions": [
    {
      "agent_id": 1,
      "id": 1,
      "title": "What is the return policy for sale items?",
      "updated_at": "2026-11-21T03:48:53Z"
    }
  ]
}
```

---

### `POST /api/playground/sessions`

Start a new Playground chat.

**Role:** supervisor · **CSRF header:** required

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `agent_id` | integer | no | Agent to talk to (can change per message) |

**Returns:** `{id}` of the new session (201).

Example request:

```http
POST /api/playground/sessions
Content-Type: application/json

{
  "agent_id": 1
}
```

Example response `201`:

```json
{
  "id": 1
}
```

---

### `GET /api/playground/sessions/{sid}`

One Playground chat with all its messages.

**Role:** supervisor

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `sid` | integer | yes | Session id |

**Returns:** `session` and `messages[]` {id, role: user|assistant, text, sources[{file, locator}], meta{model, agent}, created_at}

Example request:

```http
GET /api/playground/sessions/1
```

Example response `200`:

```json
{
  "messages": [
    {
      "created_at": "2026-11-21T03:48:53Z",
      "id": 1,
      "meta": {},
      "role": "user",
      "sources": [],
      "text": "What is the return policy for sale items?"
    },
    {
      "created_at": "2026-11-21T03:48:53Z",
      "id": 2,
      "meta": {
        "agent": "Customer Service",
        "model": "Platform default"
      },
      "role": "assistant",
      "sources": [
        {
          "file": "Returns FAQ",
          "locator": "text"
        }
      ],
      "text": "Sale items can be returned within 14 days for store credit."
    }
  ],
  "session": {
    "agent_id": 1,
    "created_at": "2026-11-21T03:48:53Z",
    "id": 1,
    "title": "What is the return policy for sale items?",
    "updated_at": "2026-11-21T03:48:53Z",
    "user_id": 1,
    "workspace_id": 1
  }
}
```

**Errors:** `404` not your session

---

### `DELETE /api/playground/sessions/{sid}`

Delete a Playground chat.

**Role:** supervisor · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `sid` | integer | yes | Session id |

**Returns:** `{ok: true}`

Example request:

```http
DELETE /api/playground/sessions/1
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `404` not your session

---

### `POST /api/playground/sessions/{sid}/messages`

Send a message to the agent and get its answer (synchronous; waits for the model). With no AI model set up it answers 502 with "No AI model is set up yet…".

**Role:** supervisor · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `sid` | integer | yes | Session id |

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `text` | string | yes | Your message |
| `agent_id` | integer | no | Agent to answer (default: the session's) |
| `use_knowledge` | boolean | no | Search the agent's knowledge files (default true) |

**Returns:** `{id, role: "assistant", text, sources[{file, locator}], meta{model, agent}}`. `meta.model` is "Platform default" when the hidden model answered.

Example request:

```http
POST /api/playground/sessions/1/messages
Content-Type: application/json

{
  "text": "What is the return policy for sale items?",
  "agent_id": 1,
  "use_knowledge": true
}
```

Example response `200`:

```json
{
  "id": 2,
  "meta": {
    "agent": "Customer Service",
    "model": "Platform default"
  },
  "role": "assistant",
  "sources": [
    {
      "file": "Returns FAQ",
      "locator": "text"
    }
  ],
  "text": "Sale items can be returned within 14 days for store credit."
}
```

**Errors:** `400` empty message · `404` not your session · `502` every configured model failed (message lists why)

---

## Agents

### `GET /api/agents`

All agents in the workspace, plus available templates.

**Role:** viewer

**Returns:** `agents[]` {id, name, description, color, instructions, model_override{provider, model}|null, active, file_count, chat_count, active_model}, `templates[]` (names)

Example request:

```http
GET /api/agents
```

Example response `200`:

```json
{
  "agents": [
    {
      "active": 1,
      "active_model": "Platform default",
      "chat_count": 0,
      "color": "#1F6FEB",
      "created_at": "2026-11-21T03:48:53Z",
      "description": "Orders, returns, FAQs",
      "file_count": 0,
      "id": 1,
      "instructions": "You are the customer service agent for {business}. Be warm and brief: two or three sentences. Help customers with orders, returns and que…",
      "model_override": null,
      "name": "Customer Service",
      "updated_at": "2026-11-21T03:48:53Z",
      "workspace_id": 1
    },
    {
      "active": 1,
      "active_model": "Platform default",
      "chat_count": 0,
      "color": "#E8590C",
      "created_at": "2026-11-21T03:48:53Z",
      "description": "Tasks, deadlines, follow-ups",
      "file_count": 0,
      "id": 2,
      "instructions": "You coordinate projects for {business}. Confirm dates, owners and next steps clearly. Never promise a date that is not in the sources.",
      "model_override": null,
      "name": "Project Manager",
      "updated_at": "2026-11-21T03:48:53Z",
      "workspace_id": 1
    },
    "… 2 more"
  ],
  "templates": [
    "Customer Service",
    "Project Manager",
    "… 2 more"
  ]
}
```

---

### `POST /api/agents`

Create an agent (optionally from a template).

**Role:** admin · **CSRF header:** required

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Unique in the workspace (or give `template` and it's used as the name) |
| `template` | string | no | `Customer Service` · `Project Manager` · `Marketing` · `Sales`: fills missing fields |
| `description` | string | no | Short description |
| `color` | string | no | Hex colour, e.g. `#1F6FEB` |
| `instructions` | string | no | System prompt; `{business}` becomes the workspace name |
| `active` | boolean | no | Default true |
| `model_override` | object | no | `{provider, model}` to use a specific model, or null |

**Returns:** `{id}` (201)

Example request:

```http
POST /api/agents
Content-Type: application/json

{
  "name": "Receptionist",
  "description": "Hours and location",
  "color": "#0EA5E9",
  "instructions": "Greet customers of {business} and share opening hours."
}
```

Example response `201`:

```json
{
  "id": 5
}
```

**Errors:** `400` name missing · `409` name already used

---

### `PATCH /api/agents/{aid}`

Update an agent. Send only the fields to change.

**Role:** admin · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `aid` | integer | yes | Agent id |

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | no | New name (unique) |
| `description` | string | no | — |
| `color` | string | no | — |
| `instructions` | string | no | — |
| `active` | boolean | no | false = paused (never replies) |
| `model_override` | object | no | `{provider, model}` or null to use the workspace model |

**Returns:** `{ok: true}`

Example request:

```http
PATCH /api/agents/1
Content-Type: application/json

{
  "instructions": "You are the customer service agent for {business}. Be brief.",
  "model_override": null
}
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `404` unknown agent · `409` name already used

---

### `DELETE /api/agents/{aid}`

Delete an agent. Its chats become unassigned.

**Role:** admin · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `aid` | integer | yes | Agent id |

**Returns:** `{ok: true}`

Example request:

```http
DELETE /api/agents/5
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `404` unknown agent

---

## Knowledge

### `GET /api/knowledge/files`

All knowledge sources with indexing status.

**Role:** viewer

**Returns:** `files[]` {id, filename, kind, source_url, size_bytes, status: pending|indexing|ready|failed, error, chunk_count, agents[{id,name}], created_at, updated_at}, `total_chunks`

Example request:

```http
GET /api/knowledge/files
```

Example response `200`:

```json
{
  "files": [
    {
      "agents": [
        {
          "id": 1,
          "name": "Customer Service"
        }
      ],
      "chunk_count": 0,
      "created_at": "2026-11-21T03:48:53Z",
      "error": "That address is not allowed",
      "filename": "http://127.0.0.1/internal",
      "id": 3,
      "kind": "url",
      "size_bytes": 0,
      "source_url": "http://127.0.0.1/internal",
      "status": "failed",
      "updated_at": "2026-11-21T03:48:53Z"
    },
    {
      "agents": [
        {
          "id": 1,
          "name": "Customer Service"
        }
      ],
      "chunk_count": 1,
      "created_at": "2026-11-21T03:48:53Z",
      "error": null,
      "filename": "shipping.txt",
      "id": 2,
      "kind": "txt",
      "size_bytes": 43,
      "source_url": null,
      "status": "ready",
      "updated_at": "2026-11-21T03:48:53Z"
    },
    "… 1 more"
  ],
  "total_chunks": 2
}
```

---

### `POST /api/knowledge/files`

Upload one or more files. Indexing runs in the background: poll the list until `status` is `ready`.

**Role:** supervisor · **CSRF header:** required

**Request body** (multipart/form-data)

| Field | Type | Required | Description |
|---|---|---|---|
| `files` | array<file> | yes | PDF, DOCX, XLSX, CSV, TXT or MD (max `MAX_UPLOAD_MB` each request) |
| `agent_ids` | array<integer> | no | Agents allowed to use these files (repeat the field) |

**Returns:** `{created: [file ids], errors: [{file, error}]}`: 201 if at least one file was accepted

Example request:

```http
POST /api/knowledge/files
Content-Type: multipart/form-data

files=@shipping.txt
agent_ids=1
```

Example response `201`:

```json
{
  "created": [
    2
  ],
  "errors": []
}
```

**Errors:** `400` no files, or every file unsupported · `413` request too large

---

### `POST /api/knowledge/text`

Add pasted text / Q&A as a knowledge source.

**Role:** supervisor · **CSRF header:** required

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `text` | string | yes | The content |
| `title` | string | no | Shown in the file list (default "Quick Q&A") |
| `agent_ids` | array<integer> | no | Agents allowed to use it |

**Returns:** `{id}` (201)

Example request:

```http
POST /api/knowledge/text
Content-Type: application/json

{
  "title": "Returns FAQ",
  "text": "Sale items can be returned within 14 days for store credit.",
  "agent_ids": [
    1
  ]
}
```

Example response `201`:

```json
{
  "id": 1
}
```

**Errors:** `400` empty text

---

### `POST /api/knowledge/url`

Add one public web page. It's fetched in the background (private/internal addresses are refused).

**Role:** supervisor · **CSRF header:** required

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string | yes | Full http(s) URL |
| `agent_ids` | array<integer> | no | Agents allowed to use it |

**Returns:** `{id}` (201). If the fetch fails the file shows `status: failed` with the reason.

Example request:

```http
POST /api/knowledge/url
Content-Type: application/json

{
  "url": "http://127.0.0.1/internal",
  "agent_ids": [
    1
  ]
}
```

Example response `201`:

```json
{
  "id": 3
}
```

**Errors:** `400` not an http(s) URL

---

### `PATCH /api/knowledge/files/{fid}`

Change which agents may use a file.

**Role:** supervisor · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `fid` | integer | yes | File id |

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `agent_ids` | array<integer> | no | Full new list (replaces the old one) |

**Returns:** `{ok: true}`

Example request:

```http
PATCH /api/knowledge/files/1
Content-Type: application/json

{
  "agent_ids": [
    1,
    5
  ]
}
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `404` unknown file

---

### `POST /api/knowledge/files/{fid}/reindex`

Extract and index the file again.

**Role:** supervisor · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `fid` | integer | yes | File id |

**Returns:** `{ok: true}`; status goes back to `pending`

Example request:

```http
POST /api/knowledge/files/1/reindex
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `404` unknown file

---

### `DELETE /api/knowledge/files/{fid}`

Delete a file, its chunks and agent links.

**Role:** supervisor · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `fid` | integer | yes | File id |

**Returns:** `{ok: true}`

Example request:

```http
DELETE /api/knowledge/files/1
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `404` unknown file

---

## WhatsApp numbers

### `GET /api/whatsapp/connections`

All connected numbers (no secrets).

**Role:** viewer

**Returns:** `connections[]` {id, name, provider, phone_number, account_name, profile_picture, status: pending|connected|disconnected|expired|error, status_detail, default_agent_id, default_mode, webhook_url, last_event_at, last_message_at, created_at}

Example request:

```http
GET /api/whatsapp/connections
```

Example response `200`:

```json
{
  "connections": [
    {
      "account_name": "",
      "created_at": "2026-11-21T03:48:53Z",
      "default_agent_id": 1,
      "default_mode": "draft",
      "id": 1,
      "last_event_at": "2026-11-21T03:48:53Z",
      "last_message_at": "2026-11-21T03:48:53Z",
      "name": "Support line",
      "phone_number": "+57 300 000 4821",
      "profile_picture": "",
      "provider": "sandbox",
      "status": "connected",
      "status_detail": "",
      "webhook_url": "https://agents.example.com/webhooks/sandbox/1/xoE_JEQ4r3WHKNoSFvMFGrl_EkHUrFT-"
    }
  ]
}
```

---

### `POST /api/whatsapp/connections`

Add a number. For Evolution API this also creates the instance, registers our webhook and returns the first QR code.

**Role:** admin · **CSRF header:** required

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | no | Label, e.g. "Support line" |
| `provider` | string | yes | `evolution` · `meta_cloud` · `generic` (· `sandbox` with test tools) |
| `phone_number` | string | no | Display only |
| `config` | object | yes | Credentials (stored encrypted). evolution: `{server_url, api_key}` · meta_cloud: `{phone_number_id, access_token, app_secret, verify_token}` · generic: `{send_url, token?}` · sandbox: `{}` |

**Returns:** `connection` (201). Evolution adds `qr` (data URL) and `pairing_code` when the server answered; if it didn't, `status` is `error` with the reason in `status_detail`.

Example request:

```http
POST /api/whatsapp/connections
Content-Type: application/json

{
  "name": "Support line",
  "provider": "sandbox",
  "phone_number": "+57 300 000 4821",
  "config": {}
}
```

Example response `201`:

```json
{
  "connection": {
    "account_name": "",
    "created_at": "2026-11-21T03:48:53Z",
    "default_agent_id": null,
    "default_mode": null,
    "id": 1,
    "last_event_at": null,
    "name": "Support line",
    "phone_number": "+57 300 000 4821",
    "profile_picture": "",
    "provider": "sandbox",
    "status": "connected",
    "status_detail": "",
    "webhook_url": "https://agents.example.com/webhooks/sandbox/1/xoE_JEQ4r3WHKNoSFvMFGrl_EkHUrFT-"
  }
}
```

**Errors:** `400` unknown provider or missing config keys

---

### `PATCH /api/whatsapp/connections/{cid}`

Rename a number or set its defaults for new chats.

**Role:** admin · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `cid` | integer | yes | Connection id |

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | no | — |
| `phone_number` | string | no | — |
| `default_agent_id` | integer | no | Agent for new chats on this number (null = workspace default) |
| `default_mode` | string | no | `auto` · `draft` · `off` · null |

**Returns:** `connection`

Example request:

```http
PATCH /api/whatsapp/connections/1
Content-Type: application/json

{
  "default_agent_id": 1,
  "default_mode": "draft"
}
```

Example response `200`:

```json
{
  "connection": {
    "account_name": "",
    "created_at": "2026-11-21T03:48:53Z",
    "default_agent_id": 1,
    "default_mode": "draft",
    "id": 1,
    "last_event_at": null,
    "name": "Support line",
    "phone_number": "+57 300 000 4821",
    "profile_picture": "",
    "provider": "sandbox",
    "status": "connected",
    "status_detail": "",
    "webhook_url": "https://agents.example.com/webhooks/sandbox/1/xoE_JEQ4r3WHKNoSFvMFGrl_EkHUrFT-"
  }
}
```

**Errors:** `404` unknown connection

---

### `DELETE /api/whatsapp/connections/{cid}`

Remove a number and all its chats. For Evolution it also logs the phone out and deletes the instance on the Evolution server (best effort).

**Role:** admin · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `cid` | integer | yes | Connection id |

**Returns:** `{ok: true}`

Example request:

```http
DELETE /api/whatsapp/connections/3
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `404` unknown connection

---

### `GET /api/whatsapp/connections/{cid}/qr`

Current QR code to link an Evolution number.

**Role:** admin

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `cid` | integer | yes | Connection id |

**Returns:** `{qr: "data:image/png;base64,…" | null, pairing_code}`; `qr` is null when already linked

Example response `200` (illustrative: needs a live provider):

```json
{
  "qr": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA\u2026",
  "pairing_code": "WZYEH1YY"
}
```

**Errors:** `400` not an Evolution connection · `404` unknown connection · `502` Evolution server unreachable / error

---

### `POST /api/whatsapp/connections/{cid}/refresh`

Ask the provider for the live status and store it.

**Role:** viewer · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `cid` | integer | yes | Connection id |

**Returns:** `connection` with updated `status`

Example request:

```http
POST /api/whatsapp/connections/1/refresh
```

Example response `200`:

```json
{
  "connection": {
    "account_name": "",
    "created_at": "2026-11-21T03:48:53Z",
    "default_agent_id": 1,
    "default_mode": "draft",
    "id": 1,
    "last_event_at": null,
    "name": "Support line",
    "phone_number": "+57 300 000 4821",
    "profile_picture": "",
    "provider": "sandbox",
    "status": "connected",
    "status_detail": "",
    "webhook_url": "https://agents.example.com/webhooks/sandbox/1/xoE_JEQ4r3WHKNoSFvMFGrl_EkHUrFT-"
  }
}
```

**Errors:** `404` unknown connection

---

### `POST /api/whatsapp/connections/{cid}/simulate`

**Test tools only** (`ENABLE_TEST_TOOLS=true`; answers 404 otherwise). Inject a customer message as if it came from WhatsApp. Runs the full reply pipeline (testing without a phone).

**Role:** admin · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `cid` | integer | yes | Connection id |

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `text` | string | yes | Customer message |
| `from` | string | no | Customer phone, digits (default 10000000000) |
| `name` | string | no | Customer name (default "Test customer") |

**Returns:** `{message_id}` (201); null if ignored (e.g. duplicate).

Example request:

```http
POST /api/whatsapp/connections/1/simulate
Content-Type: application/json

{
  "text": "Can I return sale items?",
  "from": "573001119014",
  "name": "Maria López"
}
```

Example response `201`:

```json
{
  "message_id": 1
}
```

**Errors:** `400` text missing · `404` unknown connection

---

## Inbox

### `GET /api/inbox/chats`

Chat list for the Inbox (max 200, most recent first).

**Role:** viewer

**Query parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `filter` | string | no | `all` (default) · `drafts` · `needs_you` · `unassigned` |
| `q` | string | no | Search name, phone or last message |
| `connection_id` | integer | no | Only this number |

**Returns:** `chats[]` {id, mode, agent_id, agent_name, agent_color, handoff_active, unread_count, drafts, last_message_at, last_message_preview, connection_id, connection_name, contact_name, wa_id}, `counts` {all_, drafts, needs_you, unread (chats with unread messages)}

Example request:

```http
GET /api/inbox/chats?filter=all
```

Example response `200`:

```json
{
  "chats": [
    {
      "agent_color": null,
      "agent_id": null,
      "agent_name": null,
      "connection_id": 2,
      "connection_name": "Official line",
      "contact_name": "Luis",
      "drafts": 0,
      "handoff_active": 0,
      "id": 2,
      "last_message_at": "2026-11-21T03:48:53Z",
      "last_message_preview": "Hola",
      "mode": "draft",
      "unread_count": 1,
      "wa_id": "573005550000"
    },
    {
      "agent_color": "#1F6FEB",
      "agent_id": 1,
      "agent_name": "Customer Service",
      "connection_id": 1,
      "connection_name": "Support line",
      "contact_name": "Maria López",
      "drafts": 2,
      "handoff_active": 0,
      "id": 1,
      "last_message_at": "2026-11-21T03:48:53Z",
      "last_message_preview": "And shipping to Bogota?",
      "mode": "draft",
      "unread_count": 2,
      "wa_id": "573001119014"
    }
  ],
  "counts": {
    "all_": 2,
    "drafts": 1,
    "needs_you": 0,
    "unread": 2
  }
}
```

---

### `GET /api/inbox/chats/{cid}`

One chat: details, messages and stats. Marks it read.

**Role:** viewer

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `cid` | integer | yes | Chat id |

**Query parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `mark_read` | string | no | `0` to leave unread_count unchanged (default `1`) |

**Returns:** `chat` {…, rules{handoff, business_hours_only, match_language}, tags[], opted_out, contact_since}, `messages[]` {id, direction: in|out|system, author: customer|agent|human|system, text, status: received|draft|sent|failed|note, sources[], error, agent_name, user_name, created_at}, `stats` {agent_replies, drafts_approved, first_message}

Example request:

```http
GET /api/inbox/chats/1
```

Example response `200`:

```json
{
  "chat": {
    "agent_id": 1,
    "connection_id": 1,
    "connection_name": "Support line",
    "contact_id": 1,
    "contact_name": "Maria López",
    "contact_since": "2026-11-21T03:48:53Z",
    "created_at": "2026-11-21T03:48:53Z",
    "handoff_active": 0,
    "id": 1,
    "last_away_sent_at": null,
    "last_message_at": "2026-11-21T03:48:53Z",
    "last_message_preview": "And shipping to Bogota?",
    "mode": "draft",
    "opted_out": 0,
    "rules": {
      "business_hours_only": false,
      "handoff": true,
      "match_language": true
    },
    "tags": [],
    "unread_count": 2,
    "wa_id": "573001119014",
    "workspace_id": 1
  },
  "messages": [
    {
      "agent_name": null,
      "author": "customer",
      "created_at": "2026-11-21T03:48:53Z",
      "direction": "in",
      "error": null,
      "id": 1,
      "sources": [],
      "status": "received",
      "text": "Can I return sale items?",
      "user_name": null
    },
    {
      "agent_name": "Customer Service",
      "author": "agent",
      "created_at": "2026-11-21T03:48:53Z",
      "direction": "out",
      "error": null,
      "id": 2,
      "sources": [
        {
          "file": "Returns FAQ",
          "locator": "text"
        }
      ],
      "status": "draft",
      "text": "Sale items can be returned within 14 days for store credit.",
      "user_name": null
    },
    "… 2 more"
  ],
  "stats": {
    "agent_replies": 0,
    "drafts_approved": 0,
    "first_message": "2026-11-21T03:48:53Z"
  }
}
```

**Errors:** `404` unknown chat

---

### `PATCH /api/inbox/chats/{cid}`

Change a chat's agent, reply mode, rules or tags.

**Role:** supervisor · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `cid` | integer | yes | Chat id |

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `agent_id` | integer | no | Agent id, or null for none |
| `mode` | string | no | `auto` · `draft` · `off` |
| `rules` | object | no | Any of `{handoff, business_hours_only, match_language}` (booleans); merged |
| `tags` | array<string> | no | Replace the contact's tags (max 20) |
| `apply_to_connection` | boolean | no | Also make agent/mode the number's defaults and apply them to all its chats |

**Returns:** `{ok: true}`

Example request:

```http
PATCH /api/inbox/chats/1
Content-Type: application/json

{
  "mode": "auto",
  "rules": {
    "business_hours_only": false
  },
  "tags": [
    "Returning"
  ]
}
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `400` unknown agent · `404` unknown chat

---

### `DELETE /api/inbox/chats/{cid}`

Delete a chat and all its messages. The contact is removed too when it has no other chats.

**Role:** supervisor · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `cid` | integer | yes | Chat id |

**Returns:** `{ok: true}`

Example request:

```http
DELETE /api/inbox/chats/2
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `404` unknown chat

---

### `POST /api/inbox/chats/{cid}/messages`

Send a message as yourself. Pauses the agent (sets handoff).

**Role:** supervisor · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `cid` | integer | yes | Chat id |

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `text` | string | yes | Message |

**Returns:** `{id}` (201): message status is `sent` or `failed`

Example request:

```http
POST /api/inbox/chats/1/messages
Content-Type: application/json

{
  "text": "Hi, this is Ana from the team."
}
```

Example response `201`:

```json
{
  "id": 8
}
```

**Errors:** `400` empty · `404` unknown chat

---

### `POST /api/inbox/chats/{cid}/takeover`

Pause the agent on this chat ("Needs you").

**Role:** supervisor · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `cid` | integer | yes | Chat id |

**Returns:** `{ok: true}`

Example request:

```http
POST /api/inbox/chats/1/takeover
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `404` unknown chat

---

### `POST /api/inbox/chats/{cid}/resume`

Let the agent reply again.

**Role:** supervisor · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `cid` | integer | yes | Chat id |

**Returns:** `{ok: true}`

Example request:

```http
POST /api/inbox/chats/1/resume
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `404` unknown chat

---

### `POST /api/inbox/chats/{cid}/ask-agent`

Have the agent draft a reply to the latest customer message now.

**Role:** supervisor · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `cid` | integer | yes | Chat id |

**Returns:** `{id}` of the new draft (201)

Example request:

```http
POST /api/inbox/chats/1/ask-agent
```

Example response `201`:

```json
{
  "id": 6
}
```

**Errors:** `404` no agent assigned / no customer message · `502` model error

---

### `POST /api/inbox/messages/{mid}/approve`

Send a draft (optionally edited).

**Role:** supervisor · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `mid` | integer | yes | Draft message id |

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `text` | string | no | Edited text (default: the draft as is) |

**Returns:** `message`: status `sent` or `failed`

Example request:

```http
POST /api/inbox/messages/2/approve
Content-Type: application/json

{
  "text": "Hi Maria! Sale items can be returned within 14 days for store credit."
}
```

Example response `200`:

```json
{
  "message": {
    "agent_id": 1,
    "author": "agent",
    "chat_id": 1,
    "created_at": "2026-11-21T03:48:53Z",
    "direction": "out",
    "error": null,
    "id": 2,
    "provider_message_id": "sandbox-1",
    "sources": "[{\"file\": \"Returns FAQ\", \"locator\": \"text\"}]",
    "status": "sent",
    "text": "Hi Maria! Sale items can be returned within 14 days for store credit.",
    "user_id": 1
  }
}
```

**Errors:** `404` not a draft

---

### `POST /api/inbox/messages/{mid}/discard`

Throw a draft away.

**Role:** supervisor · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `mid` | integer | yes | Draft message id |

**Returns:** `{ok: true}`

Example request:

```http
POST /api/inbox/messages/6/discard
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `404` not a draft

---

## Settings

### `GET /api/settings/general`

Workspace name, language, time zone, hours, away message.

**Role:** viewer

**Returns:** `{name, default_language, timezone, away_message, business_hours}`. business_hours: `{mon: ["09:00","18:00"], …, sun: null}` (null = closed)

Example request:

```http
GET /api/settings/general
```

Example response `200`:

```json
{
  "away_message": "Thanks for your message! We're closed right now and will reply when we open.",
  "business_hours": {
    "fri": [
      "09:00",
      "18:00"
    ],
    "mon": [
      "09:00",
      "18:00"
    ],
    "sat": null,
    "sun": null,
    "thu": [
      "09:00",
      "18:00"
    ],
    "tue": [
      "09:00",
      "18:00"
    ],
    "wed": [
      "09:00",
      "18:00"
    ]
  },
  "default_language": "English",
  "name": "Andes Coffee Co.",
  "timezone": "UTC"
}
```

---

### `PATCH /api/settings/general`

Update general settings. Send only what changes.

**Role:** admin · **CSRF header:** required

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | no | Workspace name |
| `default_language` | string | no | e.g. `English`, `Español` |
| `timezone` | string | no | IANA name, e.g. `America/Bogota` |
| `away_message` | string | no | Sent outside business hours |
| `business_hours` | object | no | Per day `[open, close]` (HH:MM) or null |

**Returns:** The full general settings after saving

Example request:

```http
PATCH /api/settings/general
Content-Type: application/json

{
  "timezone": "America/Bogota",
  "away_message": "We're closed, back at 9:00."
}
```

Example response `200`:

```json
{
  "away_message": "We're closed, back at 9:00.",
  "business_hours": {
    "fri": [
      "09:00",
      "18:00"
    ],
    "mon": [
      "09:00",
      "18:00"
    ],
    "sat": null,
    "sun": null,
    "thu": [
      "09:00",
      "18:00"
    ],
    "tue": [
      "09:00",
      "18:00"
    ],
    "wed": [
      "09:00",
      "18:00"
    ]
  },
  "default_language": "English",
  "name": "Andes Coffee Co.",
  "timezone": "America/Bogota"
}
```

---

### `DELETE /api/settings/workspace`

Permanently delete the workspace and everything in it.

**Role:** owner · **CSRF header:** required

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `confirm` | string | yes | Must be exactly `DELETE` |

**Returns:** `{ok: true}`

Example request:

```http
DELETE /api/settings/workspace
Content-Type: application/json

{
  "confirm": "DELETE"
}
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `400` confirm missing

---

### `GET /api/settings/llm`

Model settings and which providers have keys.

**Role:** viewer

**Returns:** `settings` (see PATCH), `providers[]` {id, label, connected, last4, base_url, verified_at}, `active_model` ("Platform default" or "provider · model"). Keys are never returned.

Example request:

```http
GET /api/settings/llm
```

Example response `200`:

```json
{
  "active_model": "openai · gpt-4o-mini",
  "providers": [
    {
      "base_url": "",
      "connected": true,
      "id": "openai",
      "label": "OpenAI",
      "last4": "1234",
      "verified_at": null
    },
    {
      "base_url": "",
      "connected": false,
      "id": "anthropic",
      "label": "Anthropic",
      "last4": null,
      "verified_at": null
    },
    "… 4 more"
  ],
  "settings": {
    "fallback": true,
    "max_tokens": 500,
    "model": "gpt-4o-mini",
    "provider": "openai",
    "source": "byok",
    "temperature": 0.4
  }
}
```

---

### `PATCH /api/settings/llm`

Change the workspace model settings.

**Role:** admin · **CSRF header:** required

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `source` | string | no | `platform` (hidden default model) or `byok` (workspace's own key) |
| `provider` | string | no | `openai` · `anthropic` · `gemini` · `deepseek` · `qwen` · `openai_compatible` (used when source = byok) |
| `model` | string | no | Model id at that provider, e.g. `gpt-4o-mini` |
| `temperature` | number | no | 0–1 (clamped) |
| `max_tokens` | integer | no | 50–4000 (clamped) |
| `fallback` | boolean | no | Fall back to the platform default when the workspace key fails |

**Returns:** `settings` after saving

Example request:

```http
PATCH /api/settings/llm
Content-Type: application/json

{
  "source": "byok",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "fallback": true
}
```

Example response `200`:

```json
{
  "settings": {
    "fallback": true,
    "max_tokens": 500,
    "model": "gpt-4o-mini",
    "provider": "openai",
    "source": "byok",
    "temperature": 0.4
  }
}
```

**Errors:** `400` invalid source

---

### `PUT /api/settings/providers/{provider}`

Save (or replace) an API key for a provider. Stored encrypted.

**Role:** admin · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `provider` | string | yes | `openai` · `anthropic` · `gemini` · `deepseek` · `qwen` · `openai_compatible` |

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `api_key` | string | no | Required the first time; blank keeps the stored key |
| `base_url` | string | no | Proxy / Azure / self-hosted endpoint (required for openai_compatible) |

**Returns:** `{ok: true, switched}`. If the workspace had no real model yet, it is switched to this key automatically (source `byok`, a starter model such as `gpt-4o-mini`, or the first model the key lists if that one isn't available) and the response includes `switched: true` and the new `settings`.

Example request:

```http
PUT /api/settings/providers/openai
Content-Type: application/json

{
  "api_key": "sk-proj-EXAMPLE1234",
  "base_url": ""
}
```

Example response `200`:

```json
{
  "ok": true,
  "switched": false
}
```

**Errors:** `400` key required · `404` unknown provider

---

### `DELETE /api/settings/providers/{provider}`

Remove a provider's key.

**Role:** admin · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `provider` | string | yes | Provider id |

**Returns:** `{ok: true}`

Example request:

```http
DELETE /api/settings/providers/openai
```

Example response `200`:

```json
{
  "ok": true
}
```

---

### `GET /api/settings/providers/{provider}/models`

Models the saved key can use (for the model pickers). Cached for 10 minutes.

**Role:** admin

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `provider` | string | yes | Provider id |

**Query parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `fresh` | string | no | `1` to skip the cache |

**Returns:** `{models: [ids]}`

Example response `200` (illustrative: needs a live provider):

```json
{
  "models": [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3-flash-preview",
    "\u2026"
  ]
}
```

**Errors:** `502` no key saved, or the provider rejected it (message included)

---

### `POST /api/settings/providers/{provider}/test`

Check the saved key by listing the provider's models.

**Role:** admin · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `provider` | string | yes | Provider id |

**Returns:** `{ok: true, models: [ids]}`; also marks the key verified. If this provider is the workspace model and no model name is set, the first listed model is selected and returned as `model_selected`.

Example response `200` (illustrative: needs a live provider):

```json
{
  "ok": true,
  "models": [
    "gpt-4o",
    "gpt-4o-mini",
    "\u2026"
  ]
}
```

**Errors:** `502` no key saved, or the provider rejected it (message included)

---

### `GET /api/settings/whatsapp`

Read: whatsapp behaviour defaults and sending limits.

**Role:** viewer

**Returns:** All keys with current values

Example request:

```http
GET /api/settings/whatsapp
```

Example response `200`:

```json
{
  "default_agent_id": null,
  "default_mode": "draft",
  "delay_max": 8,
  "delay_min": 3,
  "ignore_groups": true,
  "max_per_minute": 20,
  "optout_keywords": [
    "STOP",
    "BAJA",
    "… 1 more"
  ]
}
```

---

### `PATCH /api/settings/whatsapp`

Update: whatsapp behaviour defaults and sending limits. Send only the keys to change; unknown keys are ignored.

**Role:** admin · **CSRF header:** required

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `default_agent_id` | integer | no | Agent for new chats when the number has no default (null = none) |
| `default_mode` | string | no | `auto` | `draft` | `off` for new chats |
| `ignore_groups` | boolean | no | Ignore WhatsApp group chats |
| `max_per_minute` | integer | no | Max automatic sends per minute per number; extra replies become drafts |
| `delay_min` | integer | no | Minimum random delay before an automatic reply (seconds) |
| `delay_max` | integer | no | Maximum random delay (seconds) |
| `optout_keywords` | array<string> | no | Exact messages that opt a customer out (case-insensitive) |

**Returns:** All keys after saving

Example request:

```http
PATCH /api/settings/whatsapp
Content-Type: application/json

{
  "default_mode": "draft",
  "max_per_minute": 15
}
```

Example response `200`:

```json
{
  "default_agent_id": null,
  "default_mode": "draft",
  "delay_max": 8,
  "delay_min": 3,
  "ignore_groups": true,
  "max_per_minute": 15,
  "optout_keywords": [
    "STOP",
    "BAJA",
    "… 1 more"
  ]
}
```

---

### `GET /api/settings/agent-defaults`

Read: rules every agent follows.

**Role:** viewer

**Returns:** All keys with current values

Example request:

```http
GET /api/settings/agent-defaults
```

Example response `200`:

```json
{
  "general_knowledge": true,
  "handoff_keywords": [
    "human",
    "agent",
    "… 3 more"
  ],
  "never_topics": [
    "legal advice",
    "medical advice",
    "… 1 more"
  ],
  "sign_replies": false
}
```

---

### `PATCH /api/settings/agent-defaults`

Update: rules every agent follows. Send only the keys to change; unknown keys are ignored.

**Role:** admin · **CSRF header:** required

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `handoff_keywords` | array<string> | no | Words that send the chat to a human |
| `never_topics` | array<string> | no | Topics agents must decline (and hand off on WhatsApp) |
| `sign_replies` | boolean | no | Append the agent's name to WhatsApp replies |
| `general_knowledge` | boolean | no | Answer general questions from general knowledge (default true); false = only questions about the business |

**Returns:** All keys after saving

Example request:

```http
PATCH /api/settings/agent-defaults
Content-Type: application/json

{
  "handoff_keywords": [
    "human",
    "manager"
  ]
}
```

Example response `200`:

```json
{
  "general_knowledge": true,
  "handoff_keywords": [
    "human",
    "manager"
  ],
  "never_topics": [
    "legal advice",
    "medical advice",
    "… 1 more"
  ],
  "sign_replies": false
}
```

---

### `GET /api/settings/security`

Read: data retention.

**Role:** viewer

**Returns:** All keys with current values

Example request:

```http
GET /api/settings/security
```

Example response `200`:

```json
{
  "retention_days": 90
}
```

---

### `PATCH /api/settings/security`

Update: data retention. Send only the keys to change; unknown keys are ignored.

**Role:** admin · **CSRF header:** required

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `retention_days` | integer | no | Delete messages older than this many days (0 = keep forever). Applied by `flask purge` |

**Returns:** All keys after saving

Example request:

```http
PATCH /api/settings/security
Content-Type: application/json

{
  "retention_days": 30
}
```

Example response `200`:

```json
{
  "retention_days": 30
}
```

---

## Team

### `GET /api/team`

Members and pending invites.

**Role:** viewer

**Returns:** `members[]` {id, name, email, role, last_active_at}, `invites[]` {id, email, role, created_at}, `me` (your user id)

Example request:

```http
GET /api/team
```

Example response `200`:

```json
{
  "invites": [
    {
      "created_at": "2026-11-21T03:48:53Z",
      "email": "lee@example.com",
      "id": 2,
      "role": "supervisor"
    },
    {
      "created_at": "2026-11-21T03:48:53Z",
      "email": "sam@example.com",
      "id": 1,
      "role": "supervisor"
    }
  ],
  "me": 1,
  "members": [
    {
      "email": "owner@example.com",
      "id": 1,
      "last_active_at": "2026-11-21T03:48:53Z",
      "name": "Ana Owner",
      "role": "owner"
    }
  ]
}
```

---

### `POST /api/team/invites`

Create invite links (no email is sent; share the link).

**Role:** admin · **CSRF header:** required

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `emails` | string | yes | One or more addresses, comma or semicolon separated |
| `role` | string | no | `admin` · `supervisor` (default) · `viewer` |

**Returns:** `invites[]` {email, link} (201)

Example request:

```http
POST /api/team/invites
Content-Type: application/json

{
  "emails": "sam@example.com, lee@example.com",
  "role": "supervisor"
}
```

Example response `201`:

```json
{
  "invites": [
    {
      "email": "sam@example.com",
      "link": "https://agents.example.com/register?invite=fZwSRM7kxLxRywhlffKm-Pi9Jq3Px7wP"
    },
    {
      "email": "lee@example.com",
      "link": "https://agents.example.com/register?invite=t_z1QcQn353qTMmPbwVzqZooy6tpBBN7"
    }
  ]
}
```

**Errors:** `400` no valid email / invalid role

---

### `DELETE /api/team/invites/{iid}`

Revoke a pending invite.

**Role:** admin · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `iid` | integer | yes | Invite id |

**Returns:** `{ok: true}`

Example request:

```http
DELETE /api/team/invites/2
```

Example response `200`:

```json
{
  "ok": true
}
```

---

### `PATCH /api/team/members/{uid}`

Change a member's role.

**Role:** admin · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `uid` | integer | yes | User id |

**Request body** (application/json)

| Field | Type | Required | Description |
|---|---|---|---|
| `role` | string | yes | `admin` · `supervisor` · `viewer` |

**Returns:** `{ok: true}`

Example request:

```http
PATCH /api/team/members/2
Content-Type: application/json

{
  "role": "viewer"
}
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `400` invalid member or role · `403` the owner's role can't change

---

### `DELETE /api/team/members/{uid}`

Remove a member.

**Role:** admin · **CSRF header:** required

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `uid` | integer | yes | User id |

**Returns:** `{ok: true}`

Example request:

```http
DELETE /api/team/members/2
```

Example response `200`:

```json
{
  "ok": true
}
```

**Errors:** `403` owner or yourself

---

## Usage & audit

### `GET /api/usage`

This month's usage.

**Role:** viewer

**Returns:** `{period_start, agent_replies, platform_tokens, byok_tokens, storage_bytes, numbers}`

Example request:

```http
GET /api/usage
```

Example response `200`:

```json
{
  "agent_replies": 2,
  "byok_tokens": 0,
  "numbers": 3,
  "period_start": "2026-11-01T00:00:00Z",
  "platform_tokens": 1065,
  "storage_bytes": 102
}
```

---

### `GET /api/audit`

Last 100 audit entries (who changed what).

**Role:** admin

**Returns:** `entries[]` {action, target, created_at, user_name}

Example request:

```http
GET /api/audit
```

Example response `200`:

```json
{
  "entries": [
    {
      "action": "changed password",
      "created_at": "2026-11-21T03:48:53Z",
      "target": "",
      "user_name": "Ana Owner"
    },
    {
      "action": "removed member",
      "created_at": "2026-11-21T03:48:53Z",
      "target": "sam@example.com",
      "user_name": "Ana Owner"
    },
    "… 19 more"
  ]
}
```

---

### `GET /api/export`

Download everything the workspace owns as JSON (no secrets).

**Role:** admin

**Returns:** JSON file (`Content-Disposition: attachment`) with workspace, agents, knowledge_files, contacts, chats[messages]

Example request:

```http
GET /api/export
```

Example response `200`:

```json
{
  "agents": [
    {
      "active": 1,
      "description": "Orders, returns, FAQs",
      "instructions": "You are the customer service agent for {business}. Be brief.",
      "name": "Customer Service"
    },
    {
      "active": 1,
      "description": "Promos, campaigns, new leads",
      "instructions": "You handle marketing conversations for {business}. Be upbeat and concise, describe current promotions only from the sources, and ask inte…",
      "name": "Marketing"
    },
    "… 3 more"
  ],
  "chats": [
    {
      "agent_id": 1,
      "created_at": "2026-11-21T03:48:53Z",
      "id": 1,
      "messages": [
        {
          "author": "customer",
          "created_at": "2026-11-21T03:48:53Z",
          "direction": "in",
          "status": "received",
          "text": "Can I return sale items?"
        },
        {
          "author": "agent",
          "created_at": "2026-11-21T03:48:53Z",
          "direction": "out",
          "status": "sent",
          "text": "Hi Maria! Sale items can be returned within 14 days for store credit."
        },
        "… 6 more"
      ],
      "mode": "auto",
      "name": "Maria López",
      "wa_id": "573001119014"
    }
  ],
  "contacts": [
    {
      "created_at": "2026-11-21T03:48:53Z",
      "name": "Maria López",
      "opted_out": 0,
      "tags": "[\"Returning\"]",
      "wa_id": "573001119014"
    }
  ],
  "exported_at": "2026-11-21T03:48:53Z",
  "knowledge_files": [
    {
      "chunk_count": 1,
      "created_at": "2026-11-21T03:48:53Z",
      "filename": "Returns FAQ",
      "kind": "qa",
      "status": "ready"
    },
    {
      "chunk_count": 1,
      "created_at": "2026-11-21T03:48:53Z",
      "filename": "shipping.txt",
      "kind": "txt",
      "status": "ready"
    },
    "… 1 more"
  ],
  "workspace": {
    "default_language": "English",
    "name": "Andes Coffee Co.",
    "timezone": "America/Bogota"
  }
}
```

---

## Webhooks

### `POST /webhooks/{provider}/{conn_id}/{token}`

Inbound events from Evolution API, a generic gateway or the sandbox. The URL (with its secret token) is shown in the number's details.

**Role:** provider authentication (see below)

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `provider` | string | yes | `evolution` · `generic` · `sandbox` |
| `conn_id` | integer | yes | Connection id |
| `token` | string | yes | Secret per-connection token |

**Request body:** Evolution v2: `{event: "messages.upsert" | "connection.update" | "qrcode.updated", instance, data}`. Generic/sandbox: `{from, name, text, id}`.

**Returns:** `{ok: true, handled: n}`. Always 200 once authenticated (errors are logged) so providers don't retry-storm. Duplicate message ids are ignored.

Example request:

```http
POST /webhooks/sandbox/1/xoE_JEQ4r3WHKNoSFvMFGrl_EkHUrFT-
Content-Type: application/json

{
  "from": "573001119014",
  "name": "Maria López",
  "text": "And shipping to Bogota?",
  "id": "wamid-123"
}
```

Example response `200`:

```json
{
  "handled": 1,
  "ok": true
}
```

**Errors:** `404` unknown connection or wrong token

---

### `GET /webhooks/meta/{conn_id}`

Meta's webhook verification handshake.

**Role:** provider authentication (see below)

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `conn_id` | integer | yes | Connection id |

**Query parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `hub.mode` | string | yes | `subscribe` |
| `hub.verify_token` | string | yes | Must equal the connection's verify token |
| `hub.challenge` | string | yes | Echoed back as plain text |

**Returns:** The `hub.challenge` value (text/plain); marks the number connected

Example request:

```http
GET /webhooks/meta/2?hub.mode=subscribe&hub.verify_token=my-verify-token&hub.challenge=1158201444
```

Example response `200`:

```
1158201444
```

**Errors:** `403` wrong token · `404` unknown connection

---

### `POST /webhooks/meta/{conn_id}`

Inbound messages from the WhatsApp Cloud API. Requires a valid `X-Hub-Signature-256` (HMAC-SHA256 of the raw body with the app secret).

**Role:** provider authentication (see below)

**Path parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `conn_id` | integer | yes | Connection id |

**Request body:** Meta's standard payload: `entry[].changes[].value.messages[]` (text messages are handled).

**Returns:** `{ok: true, handled: n}`

Example request:

```http
POST /webhooks/meta/2
X-Hub-Signature-256: sha256=<hmac of raw body>
Content-Type: application/json

{
  "entry": [
    {
      "changes": [
        {
          "value": {
            "contacts": [
              {
                "wa_id": "573005550000",
                "profile": {
                  "name": "Luis"
                }
              }
            ],
            "messages": [
              {
                "from": "573005550000",
                "id": "wamid.ABC",
                "type": "text",
                "text": {
                  "body": "Hola"
                }
              }
            ]
          }
        }
      ]
    }
  ]
}
```

Example response `200`:

```json
{
  "handled": 1,
  "ok": true
}
```

**Errors:** `401` bad signature · `404` unknown connection

---

## Service

### `GET /healthz`

Health check (does a database round-trip).

**Role:** none (public)

**Returns:** `{status: "ok"}`

Example request:

```http
GET /healthz
```

Example response `200`:

```json
{
  "status": "ok"
}
```

---

### `GET /`

Service info.

**Role:** none (public)

**Returns:** `{service, docs, health}`

Example request:

```http
GET /
```

Example response `200`:

```json
{
  "docs": "see docs/API.md",
  "health": "/healthz",
  "service": "agentry-api"
}
```

---
