"""WhatsApp provider adapters.

Each adapter wraps one way of talking to WhatsApp and normalises it:

    send_text(to, text) -> provider_message_id
    parse_webhook(payload) -> list[Inbound | ConnectionUpdate]
    setup(webhook_url)   -> dict   (create instance / register webhook; may return a QR)
    qr()                 -> dict   ({"qr": data-url or None, "pairing_code": ...})
    state()              -> str    (connected | pending | disconnected)

Adding a provider: subclass Adapter, add it to ADAPTERS and to the CHECK
constraint on wa_connections.provider via a migration.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)



# Inbound messages older than this (e.g. history replayed when a number is linked) are ignored.
MAX_MESSAGE_AGE_SECONDS = 300

class WhatsAppError(Exception):
    pass


@dataclass
class Inbound:
    wa_id: str              # sender phone, digits only
    name: str
    text: str
    provider_message_id: str
    is_group: bool = False


@dataclass
class ConnectionUpdate:
    status: str             # connected | disconnected | pending
    detail: str = ""


def digits(jid_or_phone: str) -> str:
    return "".join(ch for ch in (jid_or_phone or "").split("@")[0] if ch.isdigit())


class Adapter:
    provider = "base"

    def __init__(self, config: dict, timeout: int = 20):
        self.config = config
        self.timeout = timeout

    def _req(self, method, url, **kw):
        try:
            resp = requests.request(method, url, timeout=self.timeout, **kw)
        except requests.RequestException as exc:
            raise WhatsAppError(f"cannot reach {self.provider}: {exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise WhatsAppError(f"{self.provider} HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            return resp.json()
        except ValueError:
            return {}

    def setup(self, webhook_url: str) -> dict:
        return {}

    def qr(self) -> dict:
        return {"qr": None}

    def state(self) -> str:
        return "connected"

    def send_text(self, to: str, text: str) -> str:
        raise NotImplementedError

    def parse_webhook(self, payload: dict) -> list:
        raise NotImplementedError


class EvolutionAdapter(Adapter):
    """Evolution API v2 (Baileys / QR-code linking).

    config: {"server_url", "api_key", "instance"}
    """
    provider = "evolution"

    def _h(self):
        return {"apikey": self.config["api_key"], "Content-Type": "application/json"}

    def _u(self, path):
        return f"{self.config['server_url'].rstrip('/')}{path}"

    def setup(self, webhook_url):
        inst = self.config["instance"]
        try:
            self._req("POST", self._u("/instance/create"), headers=self._h(),
                      json={"instanceName": inst, "qrcode": True, "integration": "WHATSAPP-BAILEYS"})
        except WhatsAppError as exc:
            if "already" not in str(exc).lower() and "403" not in str(exc):
                raise
        self._req("POST", self._u(f"/webhook/set/{inst}"), headers=self._h(), json={"webhook": {
            "enabled": True, "url": webhook_url, "webhookByEvents": False, "webhookBase64": False,
            "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE", "QRCODE_UPDATED"]}})
        return self.qr()

    def qr(self):
        data = self._req("GET", self._u(f"/instance/connect/{self.config['instance']}"), headers=self._h())
        b64 = data.get("base64") or (data.get("qrcode") or {}).get("base64")
        if b64 and not b64.startswith("data:"):
            b64 = "data:image/png;base64," + b64
        return {"qr": b64, "pairing_code": data.get("pairingCode")}

    def state(self):
        data = self._req("GET", self._u(f"/instance/connectionState/{self.config['instance']}"), headers=self._h())
        st = ((data.get("instance") or {}).get("state") or data.get("state") or "").lower()
        return {"open": "connected", "connecting": "pending"}.get(st, "disconnected")

    def send_text(self, to, text):
        data = self._req("POST", self._u(f"/message/sendText/{self.config['instance']}"), headers=self._h(),
                         json={"number": digits(to), "text": text})
        return ((data.get("key") or {}).get("id")) or data.get("id") or ""

    def parse_webhook(self, payload):
        event = str(payload.get("event", "")).lower().replace("_", ".")
        data = payload.get("data") or {}
        if event == "messages.upsert":
            items = data if isinstance(data, list) else (data.get("messages") or [data])
            out = []
            for m in items:
                key = m.get("key") or {}
                if key.get("fromMe"):
                    continue
                # Linking a number makes WhatsApp replay recent and offline messages. Only answer fresh ones,
                # so a reconnect never triggers a burst of replies to old conversations.
                ts = m.get("messageTimestamp")
                try:
                    ts = int(ts.get("low", 0) if isinstance(ts, dict) else ts) if ts else 0
                except (TypeError, ValueError):
                    ts = 0
                if ts and time.time() - ts > MAX_MESSAGE_AGE_SECONDS:
                    continue
                msg = m.get("message") or {}
                text = (msg.get("conversation") or (msg.get("extendedTextMessage") or {}).get("text")
                        or (msg.get("imageMessage") or {}).get("caption") or "")
                if not text:
                    continue  # media without caption: not handled in v1
                jid = key.get("remoteJid", "")
                out.append(Inbound(digits(key.get("participant") or jid) if jid.endswith("@g.us") else digits(jid),
                                   m.get("pushName", ""), text, key.get("id", ""), jid.endswith("@g.us")))
            return out
        if event == "connection.update":
            st = str(data.get("state", "")).lower()
            return [ConnectionUpdate({"open": "connected", "connecting": "pending"}.get(st, "disconnected"),
                                     data.get("statusReason", "") and f"reason {data.get('statusReason')}")]
        if event == "qrcode.updated":
            return [ConnectionUpdate("pending", "new QR code available")]
        return []


class MetaCloudAdapter(Adapter):
    """WhatsApp Cloud API (official).

    config: {"phone_number_id", "access_token", "app_secret", "verify_token", "graph_version"}
    """
    provider = "meta_cloud"

    def send_text(self, to, text):
        ver = self.config.get("graph_version", "v24.0")
        data = self._req("POST", f"https://graph.facebook.com/{ver}/{self.config['phone_number_id']}/messages",
                         headers={"Authorization": f"Bearer {self.config['access_token']}"},
                         json={"messaging_product": "whatsapp", "recipient_type": "individual",
                               "to": digits(to), "type": "text", "text": {"preview_url": False, "body": text}})
        return ((data.get("messages") or [{}])[0]).get("id", "")

    def verify_signature(self, raw_body: bytes, header: str) -> bool:
        secret = self.config.get("app_secret", "")
        if not secret:
            return False
        expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, header or "")

    def parse_webhook(self, payload):
        out = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value") or {}
                names = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in value.get("contacts", [])}
                for m in value.get("messages", []):
                    if m.get("type") != "text":
                        continue
                    out.append(Inbound(digits(m.get("from", "")), names.get(m.get("from"), ""),
                                       (m.get("text") or {}).get("body", ""), m.get("id", "")))
        return out


class GenericAdapter(Adapter):
    """Any gateway (WAHA, Z-API, Twilio via a small bridge…).

    Inbound JSON: {"from": "...", "name": "...", "text": "...", "id": "..."}
    Outbound: POST {send_url} with {"to", "text"} and optional bearer token.
    config: {"send_url", "token"}
    """
    provider = "generic"

    def send_text(self, to, text):
        headers = {"Authorization": f"Bearer {self.config['token']}"} if self.config.get("token") else {}
        data = self._req("POST", self.config["send_url"], headers=headers, json={"to": digits(to), "text": text})
        return str(data.get("id", ""))

    def parse_webhook(self, payload):
        if not payload.get("text"):
            return []
        return [Inbound(digits(payload.get("from", "")), payload.get("name", ""), payload["text"],
                        str(payload.get("id", "")))]


class SandboxAdapter(Adapter):
    """Local development: sends nowhere, logs instead. Use the Simulate button
    (or POST /api/whatsapp/connections/<id>/simulate) to inject messages."""
    provider = "sandbox"
    sent: list = []  # visible to tests

    def send_text(self, to, text):
        log.info("[sandbox] -> %s: %s", to, text)
        SandboxAdapter.sent.append((to, text))
        return f"sandbox-{len(SandboxAdapter.sent)}"

    def parse_webhook(self, payload):
        return GenericAdapter(self.config).parse_webhook(payload)


ADAPTERS = {"evolution": EvolutionAdapter, "meta_cloud": MetaCloudAdapter,
            "generic": GenericAdapter, "sandbox": SandboxAdapter}
