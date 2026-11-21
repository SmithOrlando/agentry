# Frontend API reference (Vue app)

The JavaScript interfaces inside `frontend/src`: how the app talks to the backend, shared state and helpers, reusable components, routes, and exactly which backend endpoints each screen calls. Sections 6 and 7 are **generated** by `python3 scripts/gen_api_docs.py`; the rest documents the code it sits next to.

For the HTTP endpoints themselves (fields, responses, errors) see [API_BACKEND.md](API_BACKEND.md).

## 1. `src/api.js`: the HTTP client

The **only** module that calls `fetch`. Every request is same-origin (cookie session) and paths omit the `/api` prefix.

| Export | Signature | What it does |
|---|---|---|
| `api` | `api(path, { method = "GET", json, form, query }) → Promise<object>` | Core call. `json` → JSON body; `form` → `FormData` (uploads); `query` → `?a=1&b=2` (empty values dropped). Adds `X-CSRF-Token` on non-GET. Resolves with the parsed JSON body. |
| `get` | `get(path, query?)` | `api(path, { query })` |
| `post` | `post(path, json = {})` | `api(path, { method: "POST", json })` |
| `patch` | `patch(path, json)` | PATCH with JSON |
| `put` | `put(path, json)` | PUT with JSON |
| `del` | `del(path, json?)` | DELETE (optional JSON body, e.g. workspace delete confirmation) |
| `ApiError` | `class ApiError extends Error { status, data }` | Thrown for every non-2xx: `message` = backend `error` text (or `Request failed (status)`), `status` = HTTP status (0 = network down), `data` = parsed body |
| `apiStatus` | reactive `{ offline, detail }` | `offline` turns true when the API can't be reached: fetch failed, or a non-JSON answer came from the Vite proxy / nginx / AirPlay on :5000. `detail` says what to check. `AppShell` shows it as a banner with Retry |
| `setCsrf` | `setCsrf(token)` | Stores the CSRF token (called by `loadSession`) |
| `setUnauthorizedHandler` | `setUnauthorizedHandler(fn)` | Called on any 401 outside `/auth/*`; `router.js` uses it to redirect to `/login?next=…` |

```js
import { get, post, ApiError } from "@/api.js";
const { agents } = await get("/agents");
try { await post("/inbox/messages/12/approve", { text: "Edited reply" }); }
catch (e) { if (e instanceof ApiError && e.status === 404) toast("Draft already sent", true); }
```

## 2. `src/session.js`: who is signed in

| Export | Type | Description |
|---|---|---|
| `session` | reactive `{ loaded, user, workspace, setup }` | `user` = `{id, name, email, role, workspace_id}` from `GET /api/me`; `null` when signed out. `setup` = `{model_ready, real_whatsapp, test_tools}`: drives the sidebar's Finish setup card and whether Sandbox/Simulate show |
| `refreshSetup()` | `async` | Re-reads `setup` from `GET /api/me` (the sidebar calls it on every status refresh) |
| `loadSession()` | `async → user \| null` | Calls `GET /api/me`, stores user/workspace, sets the CSRF token. Run by the router guard on first navigation and after login |
| `logout()` | `async` | `POST /api/auth/logout`, clears `session` |
| `can(role)` | `("viewer" \| "supervisor" \| "admin" \| "owner") → boolean` | True if the signed-in user has at least that role. Used to hide/disable UI; the API enforces roles regardless |

## 3. `src/utils.js`: helpers and shared state

| Export | Signature | Description |
|---|---|---|
| `ago` | `ago(iso) → string` | "just now", "5 min ago", "3 h ago", weekday, or date |
| `clock` | `clock(iso) → "14:05"` | Local time |
| `dateOnly` | `dateOnly(iso) → string` | Local date, `—` for empty |
| `initials` | `initials(name) → "ML"` | Up to 2 letters for avatars |
| `colorFor` | `colorFor(seed) → hex` | Stable colour per name/phone |
| `fileSize` | `fileSize(bytes) → "1.2 MB"` | |
| `copy` | `async copy(text)` | Clipboard + toast |
| `toasts` / `toast` / `fail` | `toast(message, isError?)`, `fail(error)` | Toast queue rendered by `App.vue`; `fail` shows an error's message |
| `applyTheme` / `savedTheme` / `currentTheme` | `applyTheme("system" \| "light" \| "dark")` | Theme stored in `localStorage["agentry-theme"]`, applied as `<html data-theme>` |
| `signals` | reactive `{ numbers, inbox, setup }` | Tiny event bus: increment to make the sidebar reload (`signals.numbers++` after changing WhatsApp numbers, `signals.inbox++` after inbox actions, `signals.setup++` after model settings/keys change) |

## 4. `src/composables/useSettingsForm.js`

`useSettingsForm(loadFn, saveFn) → { form, dirty, saving, save, discard, ready, reload }`

| Return | Description |
|---|---|
| `form` | reactive object filled with what `loadFn()` returns; bind inputs to it |
| `dirty` | true when `form` differs from the last loaded/saved state → shows `<SaveBar>` |
| `save()` | calls `saveFn(form)`, then marks clean and toasts "Saved" |
| `discard()` | restores the last loaded/saved state |
| `ready` / `reload()` | loaded flag / load again |

Also warns before leaving the page (route change or tab close) with unsaved edits.

```js
const { form, dirty, saving, save, discard, ready } = useSettingsForm(
  () => get("/settings/whatsapp"),
  (f) => patch("/settings/whatsapp", f),
);
```

## 5. Components (`src/components/`)

| Component | Props | Events | Slots | Purpose |
|---|---|---|---|---|
| `AppDialog` | `{ open: Boolean, title: String }` | `["update:open"]` | default, actions | Native `<dialog>` modal, open with `v-model:open` |
| `AppIcon` | `{ name: { type: String, required: true }, size: { type: [Number, String], default: null } }` | `—` | — | Inline stroke icon by name (see the `paths` map in the file) |
| `AppShell` | `—` | `—` | — | Page frame: sidebar (nav, Finish setup card, number status, user, theme, sign-out), API-offline banner + `<RouterView>`. Pages may teleport extra sidebar content to `#side-extra` |
| `BrandMark` | `{ size: { type: [Number, String], default: 26 } }` | `—` | — | The AI Wonder Lab logo mark (ring + breathing mint core), shared with the mother project |
| `ChipsInput` | `{ modelValue: { type: Array, required: true }, label: { type: String, default: "list" }, disabled: Boolean }` | `["update:modelValue"]` | — | Editable list of chips (Enter adds, × removes), use with `v-model` |
| `ModelPicker` | `{   modelValue: { type: String, default: "" },   models: { type: Array, default: () => [] },   // from GET /settings/providers/<p>/models   loading: Boolean,   disabled: Boolean,   label: { type: String, default: "Model" }, }` | `["update:modelValue"]` | — | Model dropdown filled from `GET /settings/providers/<p>/models`, with “Other (type a name)…” for any model id; use with `v-model` |
| `SaveBar` | `{ dirty: Boolean, saving: Boolean }` | `["save", "discard"]` | — | Sticky "unsaved changes" bar (only shown to admins) |
| `SegControl` | `{ modelValue: [String, Number], options: { type: Array, required: true }, label: String, tabs: Boolean, disabled: Boolean }` | `["update:modelValue"]` | — | Segmented buttons (radio group or tabs), use with `v-model` |
| `SettingsGroup` | `{ title: { type: String, required: true }, desc: String }` | `—` | default, action | Titled card section on settings pages |
| `SettingsLayout` | `—` | `—` | — | Settings sub-menu + title/lead from route meta + `<RouterView>` |
| `SettingsRow` | `{ title: { type: String, required: true }, desc: String, stack: Boolean }` | `—` | default | Label + control row inside a SettingsGroup |
| `ToggleSwitch` | `{ modelValue: Boolean, label: { type: String, required: true }, disabled: Boolean }` | `["update:modelValue"]` | — | Accessible on/off switch (`role=switch`), use with `v-model` |

## 6. Routes (`src/router.js`) *(generated)*

All routes except `/login` and `/register` require a session; the guard redirects to `/login?next=<path>`.

| Path | Name | View | Title |
|---|---|---|---|
| `/login` | login | `src/views/AuthView.vue` |  |
| `/register` | register | `src/views/AuthView.vue` |  |
| `/` | playground | `src/views/PlaygroundView.vue` | Playground |
| `/whatsapp` | whatsapp | `src/views/WhatsAppView.vue` | WhatsApp |
| `/inbox/:chatId?` | inbox | `src/views/InboxView.vue` | Inbox |
| `/knowledge` | knowledge | `src/views/KnowledgeView.vue` | Knowledge |
| `/settings` | — | redirect → `/settings/models` |  |
| `/settings/general` | settings-general | `src/views/settings/GeneralSettings.vue` | General |
| `/settings/models` | settings-models | `src/views/settings/ModelsSettings.vue` | Models & API keys |
| `/settings/agents` | settings-agents | `src/views/settings/AgentsSettings.vue` | Agents |
| `/settings/whatsapp` | settings-whatsapp | `src/views/settings/WhatsAppSettings.vue` | WhatsApp |
| `/settings/team` | settings-team | `src/views/settings/TeamSettings.vue` | Team |
| `/settings/billing` | settings-billing | `src/views/settings/BillingSettings.vue` | Billing & usage |
| `/settings/security` | settings-security | `src/views/settings/SecuritySettings.vue` | Security |
| `/:pathMatch(.*)*` | — | redirect → `/` (unknown URLs) |  |

## 7. What each screen calls *(generated)*

Every backend call in the Vue code, the function it's made from, and the endpoint's reference entry. `make test` fails if any of these doesn't match a real route.

### Login / Register

`frontend/src/views/AuthView.vue`

| Function | Request | Reference |
|---|---|---|
| `submit` | `POST /api/auth/login` | [`POST /api/auth/login`](API_BACKEND.md#post-api-auth-login) |
| `submit` | `POST /api/auth/register` | [`POST /api/auth/register`](API_BACKEND.md#post-api-auth-register) |

### Session (every page)

`frontend/src/session.js`

| Function | Request | Reference |
|---|---|---|
| `loadSession` | `GET /api/me` | [`GET /api/me`](API_BACKEND.md#get-api-me) |
| `refreshSetup` | `GET /api/me` | [`GET /api/me`](API_BACKEND.md#get-api-me) |
| `logout` | `POST /api/auth/logout` | [`POST /api/auth/logout`](API_BACKEND.md#post-api-auth-logout) |

### Sidebar (every page)

`frontend/src/components/AppShell.vue`

| Function | Request | Reference |
|---|---|---|
| `loadStatus` | `GET /api/whatsapp/connections` | [`GET /api/whatsapp/connections`](API_BACKEND.md#get-api-whatsapp-connections) |
| `loadStatus` | `GET /api/inbox/chats` | [`GET /api/inbox/chats`](API_BACKEND.md#get-api-inbox-chats) |

### Playground

`frontend/src/views/PlaygroundView.vue`

| Function | Request | Reference |
|---|---|---|
| `loadSessions` | `GET /api/playground/sessions` | [`GET /api/playground/sessions`](API_BACKEND.md#get-api-playground-sessions) |
| `open` | `GET /api/playground/sessions/&lt;id&gt;` | [`GET /api/playground/sessions/{sid}`](API_BACKEND.md#get-api-playground-sessions-sid) |
| `send` | `POST /api/playground/sessions` | [`POST /api/playground/sessions`](API_BACKEND.md#post-api-playground-sessions) |
| `send` | `POST /api/playground/sessions/&lt;id&gt;/messages` | [`POST /api/playground/sessions/{sid}/messages`](API_BACKEND.md#post-api-playground-sessions-sid-messages) |
| `on page load` | `GET /api/agents` | [`GET /api/agents`](API_BACKEND.md#get-api-agents) |

### WhatsApp

`frontend/src/views/WhatsAppView.vue`

| Function | Request | Reference |
|---|---|---|
| `load` | `GET /api/whatsapp/connections` | [`GET /api/whatsapp/connections`](API_BACKEND.md#get-api-whatsapp-connections) |
| `refresh` | `POST /api/whatsapp/connections/&lt;id&gt;/refresh` | [`POST /api/whatsapp/connections/{cid}/refresh`](API_BACKEND.md#post-api-whatsapp-connections-cid-refresh) |
| `api_create` | `POST /api/whatsapp/connections` | [`POST /api/whatsapp/connections`](API_BACKEND.md#post-api-whatsapp-connections) |
| `drawQR` | `GET /api/whatsapp/connections/&lt;id&gt;/qr` | [`GET /api/whatsapp/connections/{cid}/qr`](API_BACKEND.md#get-api-whatsapp-connections-cid-qr) |
| `auto-refresh (polling)` | `POST /api/whatsapp/connections/&lt;id&gt;/refresh` | [`POST /api/whatsapp/connections/{cid}/refresh`](API_BACKEND.md#post-api-whatsapp-connections-cid-refresh) |
| `simulate` | `POST /api/whatsapp/connections/&lt;id&gt;/simulate` | [`POST /api/whatsapp/connections/{cid}/simulate`](API_BACKEND.md#post-api-whatsapp-connections-cid-simulate) |
| `remove` | `DELETE /api/whatsapp/connections/&lt;id&gt;` | [`DELETE /api/whatsapp/connections/{cid}`](API_BACKEND.md#delete-api-whatsapp-connections-cid) |

### Inbox

`frontend/src/views/InboxView.vue`

| Function | Request | Reference |
|---|---|---|
| `loadChats` | `GET /api/inbox/chats` | [`GET /api/inbox/chats`](API_BACKEND.md#get-api-inbox-chats) |
| `loadDetail` | `GET /api/inbox/chats/&lt;id&gt;` | [`GET /api/inbox/chats/{cid}`](API_BACKEND.md#get-api-inbox-chats-cid) |
| `patchChat` | `PATCH /api/inbox/chats/&lt;id&gt;` | [`PATCH /api/inbox/chats/{cid}`](API_BACKEND.md#patch-api-inbox-chats-cid) |
| `deleteChat` | `DELETE /api/inbox/chats/&lt;id&gt;` | [`DELETE /api/inbox/chats/{cid}`](API_BACKEND.md#delete-api-inbox-chats-cid) |
| `action` | `POST /api/inbox/chats/&lt;id&gt;/takeover` | [`POST /api/inbox/chats/{cid}/takeover`](API_BACKEND.md#post-api-inbox-chats-cid-takeover) |
| `action` | `POST /api/inbox/chats/&lt;id&gt;/resume` | [`POST /api/inbox/chats/{cid}/resume`](API_BACKEND.md#post-api-inbox-chats-cid-resume) |
| `approve` | `POST /api/inbox/messages/&lt;id&gt;/approve` | [`POST /api/inbox/messages/{mid}/approve`](API_BACKEND.md#post-api-inbox-messages-mid-approve) |
| `discard` | `POST /api/inbox/messages/&lt;id&gt;/discard` | [`POST /api/inbox/messages/{mid}/discard`](API_BACKEND.md#post-api-inbox-messages-mid-discard) |
| `sendReply` | `POST /api/inbox/chats/&lt;id&gt;/messages` | [`POST /api/inbox/chats/{cid}/messages`](API_BACKEND.md#post-api-inbox-chats-cid-messages) |
| `askAgent` | `POST /api/inbox/chats/&lt;id&gt;/ask-agent` | [`POST /api/inbox/chats/{cid}/ask-agent`](API_BACKEND.md#post-api-inbox-chats-cid-ask-agent) |
| `on page load` | `GET /api/agents` | [`GET /api/agents`](API_BACKEND.md#get-api-agents) |
| `on page load` | `GET /api/whatsapp/connections` | [`GET /api/whatsapp/connections`](API_BACKEND.md#get-api-whatsapp-connections) |
| `auto-refresh (polling)` | `GET /api/inbox/chats/&lt;id&gt;` | [`GET /api/inbox/chats/{cid}`](API_BACKEND.md#get-api-inbox-chats-cid) |

### Knowledge

`frontend/src/views/KnowledgeView.vue`

| Function | Request | Reference |
|---|---|---|
| `load` | `GET /api/knowledge/files` | [`GET /api/knowledge/files`](API_BACKEND.md#get-api-knowledge-files) |
| `addUrl` | `POST /api/knowledge/url` | [`POST /api/knowledge/url`](API_BACKEND.md#post-api-knowledge-url) |
| `addQa` | `POST /api/knowledge/text` | [`POST /api/knowledge/text`](API_BACKEND.md#post-api-knowledge-text) |
| `saveAssign` | `PATCH /api/knowledge/files/&lt;id&gt;` | [`PATCH /api/knowledge/files/{fid}`](API_BACKEND.md#patch-api-knowledge-files-fid) |
| `reindex` | `POST /api/knowledge/files/&lt;id&gt;/reindex` | [`POST /api/knowledge/files/{fid}/reindex`](API_BACKEND.md#post-api-knowledge-files-fid-reindex) |
| `removeFile` | `DELETE /api/knowledge/files/&lt;id&gt;` | [`DELETE /api/knowledge/files/{fid}`](API_BACKEND.md#delete-api-knowledge-files-fid) |
| `saveInstructions` | `PATCH /api/agents/&lt;id&gt;` | [`PATCH /api/agents/{aid}`](API_BACKEND.md#patch-api-agents-aid) |
| `on page load` | `GET /api/agents` | [`GET /api/agents`](API_BACKEND.md#get-api-agents) |
| `upload` | `POST /api/knowledge/files` | [`POST /api/knowledge/files`](API_BACKEND.md#post-api-knowledge-files) |

### Settings › Agents

`frontend/src/views/settings/AgentsSettings.vue`

| Function | Request | Reference |
|---|---|---|
| `useSettingsForm (load / save)` | `GET /api/settings/agent-defaults` | [`GET /api/settings/agent-defaults`](API_BACKEND.md#get-api-settings-agent-defaults) |
| `useSettingsForm (load / save)` | `PATCH /api/settings/agent-defaults` | [`PATCH /api/settings/agent-defaults`](API_BACKEND.md#patch-api-settings-agent-defaults) |
| `loadAgents` | `GET /api/agents` | [`GET /api/agents`](API_BACKEND.md#get-api-agents) |
| `saveAgent` | `PATCH /api/agents/&lt;id&gt;` | [`PATCH /api/agents/{aid}`](API_BACKEND.md#patch-api-agents-aid) |
| `saveAgent` | `POST /api/agents` | [`POST /api/agents`](API_BACKEND.md#post-api-agents) |
| `removeAgent` | `DELETE /api/agents/&lt;id&gt;` | [`DELETE /api/agents/{aid}`](API_BACKEND.md#delete-api-agents-aid) |

### Settings › Billing & usage

`frontend/src/views/settings/BillingSettings.vue`

| Function | Request | Reference |
|---|---|---|
| `on page load` | `GET /api/usage` | [`GET /api/usage`](API_BACKEND.md#get-api-usage) |

### Settings › General

`frontend/src/views/settings/GeneralSettings.vue`

| Function | Request | Reference |
|---|---|---|
| `useSettingsForm (load / save)` | `GET /api/settings/general` | [`GET /api/settings/general`](API_BACKEND.md#get-api-settings-general) |
| `useSettingsForm (load / save)` | `PATCH /api/settings/general` | [`PATCH /api/settings/general`](API_BACKEND.md#patch-api-settings-general) |
| `deleteWorkspace` | `DELETE /api/settings/workspace` | [`DELETE /api/settings/workspace`](API_BACKEND.md#delete-api-settings-workspace) |

### Settings › Models & API keys

`frontend/src/views/settings/ModelsSettings.vue`

| Function | Request | Reference |
|---|---|---|
| `loadModels` | `GET /api/settings/providers/&lt;id&gt;/models` | [`GET /api/settings/providers/{provider}/models`](API_BACKEND.md#get-api-settings-providers-provider-models) |
| `useSettingsForm (load / save)` | `GET /api/settings/llm` | [`GET /api/settings/llm`](API_BACKEND.md#get-api-settings-llm) |
| `useSettingsForm (load / save)` | `GET /api/agents` | [`GET /api/agents`](API_BACKEND.md#get-api-agents) |
| `useSettingsForm (load / save)` | `PATCH /api/settings/llm` | [`PATCH /api/settings/llm`](API_BACKEND.md#patch-api-settings-llm) |
| `useSettingsForm (load / save)` | `PATCH /api/agents/&lt;id&gt;` | [`PATCH /api/agents/{aid}`](API_BACKEND.md#patch-api-agents-aid) |
| `refreshProviders` | `GET /api/settings/llm` | [`GET /api/settings/llm`](API_BACKEND.md#get-api-settings-llm) |
| `saveKey` | `PUT /api/settings/providers/&lt;id&gt;` | [`PUT /api/settings/providers/{provider}`](API_BACKEND.md#put-api-settings-providers-provider) |
| `test` | `POST /api/settings/providers/&lt;id&gt;/test` | [`POST /api/settings/providers/{provider}/test`](API_BACKEND.md#post-api-settings-providers-provider-test) |
| `removeKey` | `DELETE /api/settings/providers/&lt;id&gt;` | [`DELETE /api/settings/providers/{provider}`](API_BACKEND.md#delete-api-settings-providers-provider) |

### Settings › Security

`frontend/src/views/settings/SecuritySettings.vue`

| Function | Request | Reference |
|---|---|---|
| `useSettingsForm (load / save)` | `GET /api/settings/security` | [`GET /api/settings/security`](API_BACKEND.md#get-api-settings-security) |
| `useSettingsForm (load / save)` | `PATCH /api/settings/security` | [`PATCH /api/settings/security`](API_BACKEND.md#patch-api-settings-security) |
| `changePassword` | `POST /api/auth/password` | [`POST /api/auth/password`](API_BACKEND.md#post-api-auth-password) |
| `on page load` | `GET /api/audit` | [`GET /api/audit`](API_BACKEND.md#get-api-audit) |
| `download link` | `GET /api/export` | [`GET /api/export`](API_BACKEND.md#get-api-export) |

### Settings › Team

`frontend/src/views/settings/TeamSettings.vue`

| Function | Request | Reference |
|---|---|---|
| `load` | `GET /api/team` | [`GET /api/team`](API_BACKEND.md#get-api-team) |
| `invite` | `POST /api/team/invites` | [`POST /api/team/invites`](API_BACKEND.md#post-api-team-invites) |
| `setRole` | `PATCH /api/team/members/&lt;id&gt;` | [`PATCH /api/team/members/{uid}`](API_BACKEND.md#patch-api-team-members-uid) |
| `removeMember` | `DELETE /api/team/members/&lt;id&gt;` | [`DELETE /api/team/members/{uid}`](API_BACKEND.md#delete-api-team-members-uid) |
| `revoke` | `DELETE /api/team/invites/&lt;id&gt;` | [`DELETE /api/team/invites/{iid}`](API_BACKEND.md#delete-api-team-invites-iid) |

### Settings › WhatsApp

`frontend/src/views/settings/WhatsAppSettings.vue`

| Function | Request | Reference |
|---|---|---|
| `useSettingsForm (load / save)` | `GET /api/settings/whatsapp` | [`GET /api/settings/whatsapp`](API_BACKEND.md#get-api-settings-whatsapp) |
| `useSettingsForm (load / save)` | `PATCH /api/settings/whatsapp` | [`PATCH /api/settings/whatsapp`](API_BACKEND.md#patch-api-settings-whatsapp) |
| `on page load` | `GET /api/agents` | [`GET /api/agents`](API_BACKEND.md#get-api-agents) |
| `on page load` | `GET /api/whatsapp/connections` | [`GET /api/whatsapp/connections`](API_BACKEND.md#get-api-whatsapp-connections) |

## 8. Conventions

- Call the backend only through `api.js`; never `fetch` directly.
- Hide controls the user can't use with `can(role)`, but treat a `403` as possible anyway.
- Show errors with `fail(e)`; success with `toast("…")`.
- After changing numbers or chats, bump `signals.numbers` / `signals.inbox`.
- No `v-html` with data. Colours only via CSS variables in `styles/app.css` (both themes).
- New screen: add a route in `router.js`, a link in `AppShell.vue` (or `SettingsLayout.vue`), then run `python3 scripts/gen_api_docs.py`.
