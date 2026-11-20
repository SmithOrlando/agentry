# Security model

| Area | Implementation | File |
|---|---|---|
| Passwords | PBKDF2-SHA256, 600k iterations (`hash_password`); works on every Python build, unlike scrypt | `security.py`, `api/auth.py` |
| Sessions | Flask signed cookie, HttpOnly, SameSite=Lax, Secure via env, 14-day lifetime | `__init__.py`, `config.py` |
| CSRF | Per-session token required in `X-CSRF-Token` for all mutating `/api` calls | `security.py::check_csrf` |
| Authorization | `@role_required` on every API route; viewer < supervisor < admin < owner | `security.py`, `api/*` |
| Tenant isolation | Every query filters on `g.workspace_id`; child rows looked up via a join to their workspace | `api/*`, `services/*` |
| Secrets at rest | Provider API keys and WhatsApp credentials Fernet-encrypted; API returns only `last4` | `security.py`, `api/settings.py`, `services/connections.py` |
| Platform model | Provider/model/key only in env; responses relabelled "platform/default" | `llm/router.py` |
| Webhooks | Unguessable per-connection token in the URL (constant-time compare, 404 on mismatch); Meta HMAC-SHA256 signature; payloads deduped | `webhooks.py` |
| SSRF | "Add web page" blocks private, loopback, link-local and reserved IPs; no redirects followed | `knowledge/extract.py::fetch_url_text` |
| Uploads | Extension allow-list, `secure_filename` + random prefix, size limit, stored outside `static/` | `services/knowledge.py` |
| XSS | Vue escapes all `{{ }}` / bound text; no `v-html` with data (only static SVG icons in `AppIcon.vue`) | `frontend/src/` |
| Origin | Browser, API and webhooks share one origin through nginx, so there is no CORS and no tokens in localStorage | `frontend/nginx.conf` |
| Headers | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin` on API responses and on the SPA | `__init__.py`, `frontend/nginx.conf` |
| Prompt injection | Customer text and documents can try to steer the agent. Mitigations: sources wrapped in `<source>` tags, rules in the system prompt, **Draft first** mode, handoff keywords. Agents have no tools, so the worst case is a wrong text reply | `services/agents.py` |
| Audit | Settings, keys, team, agents and knowledge changes go to `audit_log` | `services/settings.py::audit` |

## Known gaps (prioritised)
1. **No login rate limiting / lockout.** Add Flask-Limiter or a proxy rule on `/api/auth/login`.
2. **No 2FA / SSO.** Placeholders were removed from the UI rather than faked.
3. **No Content-Security-Policy header.** Easy to add in `nginx.conf` now (the only inline script is the theme pre-paint snippet in `index.html`; move it to a file or hash it), plus Google Fonts origins.
4. **Invites are links, not emails.** Anyone holding the link can join with that email address until it's accepted or revoked.
5. **Evolution webhooks are token-in-URL**, not signed (Evolution doesn't sign). Treat webhook URLs as secrets; they appear only to admins.
6. **SQLite file is not encrypted.** Use disk encryption on the host.
