# Agentry frontend (Vue 3 + Vite)

```bash
npm install
npm run dev        # http://localhost:5173 — proxies /api to Flask on :5001 (start it with `make api`)
npm run build      # production bundle in dist/ (served by nginx, see Dockerfile + nginx.conf)
```
Point the dev proxy at another API with `AGENTRY_API=http://host:port npm run dev`.

## Structure
```
src/
  main.js                 createApp + router + global CSS
  App.vue                 <RouterView/> + toasts
  router.js               all routes, auth guard (redirects to /login), 401 handler
  api.js                  fetch wrapper: same-origin cookie, X-CSRF-Token on writes, ApiError
  session.js              signed-in user/workspace (reactive), can(role), loadSession(), logout()
  utils.js                formatting, toasts, theme, copy(), signals (tiny event bus)
  styles/app.css          design tokens (dark + light) and component classes
  composables/useSettingsForm.js   load → edit → "unsaved changes" bar → save/discard
  components/             AppShell (sidebar), SettingsLayout, AppIcon, ToggleSwitch, SegControl,
                          ChipsInput, AppDialog, SettingsGroup, SettingsRow, SaveBar
  views/                  AuthView, PlaygroundView, WhatsAppView, InboxView, KnowledgeView
  views/settings/         General, Models, Agents, WhatsApp, Team, Billing, Security
```

## Conventions
- Talk to the backend **only** through `api.js` (`get/post/patch/put/del`). Paths omit the `/api` prefix.
- Never use `v-html` with data (the only `v-html` is static SVG in `AppIcon.vue`). Vue escapes `{{ }}` for you.
- Colours only via CSS variables from `styles/app.css`, so both themes keep working.
- Role-gated UI uses `can("supervisor" | "admin" | "owner")`. The API enforces roles anyway; the UI just hides what would fail.
- Settings pages use `useSettingsForm(load, save)` and render `<SaveBar>`.
- After changing WhatsApp numbers or chats, bump `signals.numbers` / `signals.inbox` so the sidebar refreshes.

## Checks
`npm run build` is the real compile check. Without npm, `python3 scripts/check.py` parses every script,
checks template tag balance, imports, components and undefined template names.
