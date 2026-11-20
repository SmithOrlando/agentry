"""Pure-function tests: adapters, retrieval, extraction, LLM fallback."""
import hashlib
import hmac

from app.knowledge.extract import ExtractionError, extract
from app.knowledge.retrieval import chunk_sections, tokenize
from app.llm.providers import Anthropic, Gemini, LLMError, LLMResult, OpenAICompatible
from app.whatsapp.adapters import ConnectionUpdate, EvolutionAdapter, MetaCloudAdapter


def test_evolution_parses_text_and_skips_own_messages():
    a = EvolutionAdapter({"server_url": "x", "api_key": "k", "instance": "i"})
    payload = {"event": "messages.upsert", "instance": "i", "data": {
        "key": {"remoteJid": "573001112233@s.whatsapp.net", "fromMe": False, "id": "ABC"},
        "pushName": "Maria", "message": {"conversation": "Hola"}}}
    [m] = a.parse_webhook(payload)
    assert (m.wa_id, m.name, m.text, m.provider_message_id, m.is_group) == ("573001112233", "Maria", "Hola", "ABC", False)
    payload["data"]["key"]["fromMe"] = True
    assert a.parse_webhook(payload) == []


def test_evolution_extended_text_and_connection_update():
    a = EvolutionAdapter({"server_url": "x", "api_key": "k", "instance": "i"})
    [m] = a.parse_webhook({"event": "MESSAGES_UPSERT", "data": {"key": {"remoteJid": "1@s.whatsapp.net", "id": "z"},
                                                               "message": {"extendedTextMessage": {"text": "link"}}}})
    assert m.text == "link"
    [u] = a.parse_webhook({"event": "connection.update", "data": {"state": "open"}})
    assert isinstance(u, ConnectionUpdate) and u.status == "connected"


def test_meta_signature_and_parse():
    a = MetaCloudAdapter({"app_secret": "s3cret"})
    body = b'{"entry":[]}'
    good = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert a.verify_signature(body, good) and not a.verify_signature(body, "sha256=bad")
    payload = {"entry": [{"changes": [{"value": {"contacts": [{"wa_id": "57300", "profile": {"name": "Ana"}}],
                                                 "messages": [{"from": "57300", "id": "wamid.1", "type": "text",
                                                               "text": {"body": "hola"}}]}}]}]}
    [m] = a.parse_webhook(payload)
    assert (m.wa_id, m.name, m.text) == ("57300", "Ana", "hola")


def test_tokenize_handles_spanish_and_chinese():
    assert "envío" in tokenize("¿Hacen envío a Medellín?")
    assert "退货" in tokenize("可以退货吗")


def test_chunking_respects_size():
    text = "\n".join(f"Paragraph {i} " + "word " * 40 for i in range(30))
    chunks = chunk_sections([("p.1", text)], size=400, overlap=50)
    assert len(chunks) > 5 and all(len(c[1]) <= 460 for c in chunks)


def test_extract_text_and_empty(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("# Hours\nWe open at 9.")
    assert extract(f, "md")[0][1].startswith("# Hours")
    e = tmp_path / "e.txt"
    e.write_text("   ")
    try:
        extract(e, "txt")
        assert False
    except ExtractionError:
        pass


def test_provider_request_shapes(monkeypatch):
    seen = {}

    class R:
        status_code = 200

        def __init__(self, data): self.data = data
        def json(self): return self.data

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, body=json)
        if "anthropic" in url:
            return R({"content": [{"type": "text", "text": "hi"}], "usage": {"input_tokens": 3, "output_tokens": 1}})
        if "googleapis" in url:
            return R({"candidates": [{"content": {"parts": [{"text": "hi"}]}}]})
        return R({"choices": [{"message": {"content": "hi"}}], "usage": {}})

    monkeypatch.setattr("app.llm.providers.requests.post", fake_post)
    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
    assert Anthropic("k").chat(msgs, "m").text == "hi"
    assert seen["body"]["system"] == "S" and seen["headers"]["x-api-key"] == "k"
    assert Gemini("k").chat(msgs, "g").text == "hi"
    assert seen["url"].endswith("/models/g:generateContent") and "systemInstruction" in seen["body"]
    assert OpenAICompatible("deepseek", "k").chat(msgs, "d").text == "hi"
    assert seen["url"] == "https://api.deepseek.com/v1/chat/completions"


def test_router_falls_back_to_platform(app, client, monkeypatch):
    client.put("/api/settings/providers/openai", json={"api_key": "sk-x"})
    client.patch("/api/settings/llm", json={"source": "byok", "provider": "openai", "model": "gpt-x", "fallback": True})

    def boom(*a, **k):
        raise LLMError("quota")
    monkeypatch.setattr(OpenAICompatible, "chat", boom)
    sid = client.post("/api/playground/sessions", json={}).get_json()["id"]
    # Platform default is the placeholder model: no silent "(mock)" answer, the real error is shown.
    r = client.post(f"/api/playground/sessions/{sid}/messages", json={"text": "hello"})
    assert r.status_code == 502 and "quota" in r.get_json()["error"]
    # Platform default is a real model: fall back to it.
    app.config.update(PLATFORM_LLM_PROVIDER="anthropic", PLATFORM_LLM_MODEL="claude-x", PLATFORM_LLM_API_KEY="k")
    monkeypatch.setattr(Anthropic, "chat", lambda self, *a, **k: LLMResult("hi", "anthropic", "claude-x", 1, 1))
    r = client.post(f"/api/playground/sessions/{sid}/messages", json={"text": "hello"})
    assert r.status_code == 200 and r.get_json()["meta"]["model"] == "Platform default"


def test_setup_status_and_first_key_switches_workspace(client):
    assert client.get("/api/me").get_json()["setup"] == {"model_ready": False, "real_whatsapp": False, "test_tools": True}
    r = client.put("/api/settings/providers/deepseek", json={"api_key": "sk-deep"}).get_json()
    assert r["switched"] and r["settings"]["source"] == "byok" and r["settings"]["model"] == "deepseek-chat"
    assert client.get("/api/me").get_json()["setup"]["model_ready"] is True
    # A second key doesn't change the chosen model.
    assert client.put("/api/settings/providers/openai", json={"api_key": "sk-open"}).get_json()["switched"] is False
    assert client.get("/api/settings/llm").get_json()["settings"]["provider"] == "deepseek"


def test_extract_docx_xlsx_and_scanned_pdf(tmp_path):
    import docx
    import openpyxl
    from pypdf import PdfWriter
    d = docx.Document()
    d.add_heading("Shipping", 1)
    d.add_paragraph("Delivery takes 3 days.")
    d.save(tmp_path / "f.docx")
    assert extract(tmp_path / "f.docx", "docx") == [("Shipping", "Delivery takes 3 days.")]
    wb = openpyxl.Workbook()
    wb.active.append(["Product", "Price"])
    wb.active.append(["Cold brew kit", 54000])
    wb.save(tmp_path / "p.xlsx")
    assert "Product: Cold brew kit; Price: 54000" in extract(tmp_path / "p.xlsx", "xlsx")[0][1]
    w = PdfWriter()
    w.add_blank_page(200, 200)  # a page with no text layer behaves like a scan
    with open(tmp_path / "s.pdf", "wb") as fh:
        w.write(fh)
    try:
        extract(tmp_path / "s.pdf", "pdf")
        assert False, "expected ExtractionError"
    except ExtractionError as exc:
        assert "Scanned PDF" in str(exc)


def test_evolution_ignores_replayed_old_messages():
    import time as _t
    a = EvolutionAdapter({"server_url": "http://evo", "api_key": "k", "instance": "i"})
    def msg(mid, age):
        return {"key": {"remoteJid": "573001112233@s.whatsapp.net", "fromMe": False, "id": mid},
                "pushName": "Ana", "message": {"conversation": "hola"}, "messageTimestamp": int(_t.time()) - age}
    out = a.parse_webhook({"event": "messages.upsert", "data": [msg("new", 5), msg("old", 3600)]})
    assert [m.provider_message_id for m in out] == ["new"]
