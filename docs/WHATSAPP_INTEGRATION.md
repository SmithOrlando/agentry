# WhatsApp integration

Four connection types, one interface (`app/whatsapp/adapters.py`):

| Type | Use for | Inbound auth | Outbound |
|---|---|---|---|
| **Evolution API v2** | Fast setup by QR code (WhatsApp Web protocol, unofficial) | secret token in webhook URL | `POST /message/sendText/{instance}` |
| **Meta Cloud API** | Official, business-critical, high volume | `X-Hub-Signature-256` HMAC with app secret | `POST graph.facebook.com/{ver}/{phone_number_id}/messages` |
| **Generic gateway** | WAHA, Z-API, Twilio via a small bridge | secret token in webhook URL | `POST send_url {to, text}` |
| **Sandbox** | Developers only (`ENABLE_TEST_TOOLS=true`) | secret token | nothing sent (logged) |

> ⚠️ Evolution links a phone like WhatsApp Web. WhatsApp may rate-limit or ban numbers that send
> automated messages this way. Keep the sending limits on, and use the Cloud API for important numbers.

## Evolution API
**Setup:** run Evolution (see `docker-compose.yml`; it needs Postgres + Redis), then in
**WhatsApp › Add a connection › Evolution API** enter the server URL and its global API key
(`AUTHENTICATION_API_KEY`). Agentry then:
1. `POST /instance/create` `{instanceName: "agentry-<ws>-<name>-<rand>", qrcode: true, integration: "WHATSAPP-BAILEYS"}` (an "already exists" error is tolerated)
2. `POST /webhook/set/{instance}` `{webhook: {enabled, url: <our webhook>, webhookByEvents: false, webhookBase64: false, events: [MESSAGES_UPSERT, CONNECTION_UPDATE, QRCODE_UPDATED]}}`
3. `GET /instance/connect/{instance}` returns the QR (base64), shown in the UI. The page polls `GET /instance/connectionState/{instance}` every 5 s until `state: open`.

All calls send header `apikey: <key>`.

**Inbound** `messages.upsert`: we read `data.key.remoteJid` (sender; `@g.us` = group),
`data.key.fromMe` (skipped), `data.key.id` (dedupe), `data.pushName`, and the text from
`message.conversation`, `message.extendedTextMessage.text` or an image caption. Media without a caption is ignored in v1.
`connection.update` sets the number's status (`open`→connected; a drop after being connected → **expired**, shown with a Reconnect button).

**Webhook volume:** disable `MESSAGES_SET`, `CONTACTS_SET` and `CHATS_SET` on the Evolution server: they fire thousands of events on first sync and we ignore them.

**Version note:** this was written against Evolution API v2 (`evoapicloud/evolution-api`). Its env
var names and payloads have changed between minor releases. If parsing breaks after an upgrade,
capture a real payload (log it in `webhooks.token_webhook`) and adjust `EvolutionAdapter.parse_webhook`,
then add it as a test case in `tests/test_units.py`.

## Meta WhatsApp Cloud API
1. In Meta for Developers create an app with the WhatsApp product, add a phone number and create a **permanent System User token** with `whatsapp_business_messaging`.
2. In Agentry choose **WhatsApp Cloud API** and enter: phone number ID, access token, **app secret** (App settings › Basic), and any random **verify token**.
3. Open the number's **Details** (WhatsApp page), copy the webhook URL (`/webhooks/meta/<id>`), and paste it into Meta › WhatsApp › Configuration with the same verify token. Subscribe to the `messages` field. Meta then calls GET with `hub.challenge` (we echo it and mark the number connected).
4. Every POST is verified with `X-Hub-Signature-256` (HMAC-SHA256 of the raw body, app secret). Invalid → 401.

**24-hour rule:** Cloud API only allows free-form replies within 24 h of the customer's last message.
Agents only *reply*, so this holds. Proactive messages (templates) are **not implemented** (see MAINTENANCE.md › Roadmap).

## Generic gateway contract
Inbound: POST `{"from": "573001112233", "name": "Ana", "text": "hola", "id": "unique-msg-id"}` to the webhook URL.
Outbound: we POST `{"to": "573001112233", "text": "…"}` to your `send_url` with `Authorization: Bearer <token>` if set, and expect `{"id": "…"}`.

## Testing without a phone
With `ENABLE_TEST_TOOLS=true` (never in production), create a **Sandbox** number, then **Simulate** (UI) or `POST /api/whatsapp/connections/<id>/simulate`.
This runs the exact same pipeline as a real message.

## Removing a number
**WhatsApp › Remove** deletes the number and its chats in Agentry. For Evolution it also logs the phone out and deletes
the instance on the Evolution server. If Evolution can't be reached, the number is still removed from Agentry; then delete the
instance in Evolution yourself.

## Troubleshooting
See OPERATIONS.md › "No replies on WhatsApp".
