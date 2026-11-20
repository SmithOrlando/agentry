from urllib.parse import urlparse

from app.whatsapp.adapters import SandboxAdapter


def sim(client, conn, text, frm="5730011"):
    return client.post(f"/api/whatsapp/connections/{conn['id']}/simulate", json={"text": text, "from": frm, "name": "Ana"})


def messages(client, chat_id=1):
    return client.get(f"/api/inbox/chats/{chat_id}").get_json()["messages"]


def test_auto_mode_sends_answer_with_sources(setup_chat):
    client, _, configure = setup_chat
    conn = configure("auto")
    sim(client, conn, "can I return sale items?")
    out = [m for m in messages(client) if m["direction"] == "out"]
    assert out and out[0]["status"] == "sent"
    assert "14 days" in out[0]["text"]            # mock LLM echoes the retrieved source
    assert out[0]["sources"][0]["file"] == "FAQ"
    assert SandboxAdapter.sent and SandboxAdapter.sent[-1][0] == "5730011"


def test_draft_mode_waits_for_approval(setup_chat):
    client, _, configure = setup_chat
    conn = configure("draft")
    sim(client, conn, "return policy?")
    draft = next(m for m in messages(client) if m["status"] == "draft")
    assert not SandboxAdapter.sent
    r = client.post(f"/api/inbox/messages/{draft['id']}/approve", json={"text": "Edited reply"})
    assert r.status_code == 200 and r.get_json()["message"]["status"] == "sent"
    assert SandboxAdapter.sent[-1][1] == "Edited reply"


def test_handoff_keyword_pauses_agent(setup_chat):
    client, _, configure = setup_chat
    conn = configure("auto")
    sim(client, conn, "I want a human please")
    chat = client.get("/api/inbox/chats/1").get_json()["chat"]
    assert chat["handoff_active"] == 1 and not SandboxAdapter.sent
    sim(client, conn, "hello?")
    assert not SandboxAdapter.sent                 # still paused
    client.post("/api/inbox/chats/1/resume")
    sim(client, conn, "return policy?")
    assert SandboxAdapter.sent


def test_opt_out_stops_all_messages(setup_chat):
    client, _, configure = setup_chat
    conn = configure("auto")
    sim(client, conn, "STOP")
    sim(client, conn, "return policy?")
    assert not SandboxAdapter.sent
    assert client.get("/api/inbox/chats/1").get_json()["chat"]["opted_out"] == 1


def test_duplicate_provider_message_is_ignored(app, setup_chat):
    client, _, configure = setup_chat
    conn = configure("draft")
    payload = {"from": "5730011", "text": "hi", "id": "dup-1"}
    url = urlparse(conn["webhook_url"]).path
    client.c.post(url, json=payload)
    client.c.post(url, json=payload)
    assert len([m for m in messages(client) if m["direction"] == "in"]) == 1


def test_webhook_rejects_wrong_token(setup_chat):
    client, _, configure = setup_chat
    conn = configure("auto")
    assert client.c.post(f"/webhooks/sandbox/{conn['id']}/wrong", json={"from": "1", "text": "x"}).status_code == 404


def test_human_reply_takes_over(setup_chat):
    client, _, configure = setup_chat
    conn = configure("draft")
    sim(client, conn, "hello")
    client.post("/api/inbox/chats/1/messages", json={"text": "Hi, it's Sam here"})
    chat = client.get("/api/inbox/chats/1").get_json()["chat"]
    assert chat["handoff_active"] == 1
    assert SandboxAdapter.sent[-1][1] == "Hi, it's Sam here"


def test_model_failure_leaves_a_note_not_a_crash(setup_chat):
    client, _, configure = setup_chat
    conn = configure("auto")
    sim(client, conn, "[[FAIL]] please")
    notes = [m for m in messages(client) if m["direction"] == "system"]
    assert any("could not reply" in n["text"] for n in notes)


def test_evolution_connection_setup_calls(client, monkeypatch):
    calls = []

    class R:
        status_code = 200
        text = ""

        def __init__(self, data): self.data = data
        def json(self): return self.data

    def fake_request(method, url, timeout, headers=None, json=None):
        calls.append((method, url.replace("https://evo.test", ""), json, headers.get("apikey")))
        if "/instance/connect/" in url:
            return R({"base64": "iVBORw0KGgo=", "pairingCode": "ABCD"})
        if "/message/sendText/" in url:
            return R({"key": {"id": "EVO-1"}})
        return R({})
    monkeypatch.setattr("app.whatsapp.adapters.requests.request", fake_request)

    r = client.post("/api/whatsapp/connections", json={"name": "Support", "provider": "evolution",
                                                       "config": {"server_url": "https://evo.test", "api_key": "K"}})
    conn = r.get_json()["connection"]
    assert r.status_code == 201 and r.get_json()["connection"]["status"] == "pending"
    paths = [c[1] for c in calls]
    assert paths[0] == "/instance/create" and paths[1].startswith("/webhook/set/") and paths[2].startswith("/instance/connect/")
    hook = calls[1][2]["webhook"]
    assert hook["url"] == conn["webhook_url"] and "MESSAGES_UPSERT" in hook["events"]
    assert all(c[3] == "K" for c in calls)
    assert client.get(f"/api/whatsapp/connections/{conn['id']}/qr").get_json()["qr"].startswith("data:image/png;base64,")

    # inbound via the real webhook path, then an approved draft goes out through sendText
    agents = {a["name"]: a["id"] for a in client.get("/api/agents").get_json()["agents"]}
    client.patch(f"/api/whatsapp/connections/{conn['id']}", json={"default_agent_id": agents["Sales"], "default_mode": "draft"})
    url = urlparse(conn["webhook_url"]).path
    client.c.post(url, json={"event": "messages.upsert", "data": {"key": {"remoteJid": "573001@s.whatsapp.net", "fromMe": False,
                                                                           "id": "M1"}, "pushName": "Ana", "message": {"conversation": "precio?"}}})
    draft = next(m for m in messages(client) if m["status"] == "draft")
    client.post(f"/api/inbox/messages/{draft['id']}/approve", json={})
    send = [c for c in calls if "/message/sendText/" in c[1]][-1]
    assert send[2]["number"] == "573001"


def test_unread_count_and_delete_chat(setup_chat):
    client, _, configure = setup_chat
    conn = configure("off")
    sim(client, conn, "hello", frm="5730099")
    counts = client.get("/api/inbox/chats").get_json()["counts"]
    assert counts["unread"] == 1
    cid = client.get("/api/inbox/chats").get_json()["chats"][0]["id"]
    client.get(f"/api/inbox/chats/{cid}")                       # opening marks it read
    assert client.get("/api/inbox/chats").get_json()["counts"]["unread"] == 0
    assert client.delete(f"/api/inbox/chats/{cid}").get_json() == {"ok": True}
    assert client.get("/api/inbox/chats").get_json()["chats"] == []
    assert client.get(f"/api/inbox/chats/{cid}").status_code == 404


def test_connected_number_shows_linked_account(setup_chat):
    from app.services import connections as csvc
    from app.whatsapp.adapters import EvolutionAdapter
    client, _, configure = setup_chat
    conn = configure("off")
    ev = EvolutionAdapter({"server_url": "x", "api_key": "k", "instance": "i"}).parse_webhook(
        {"event": "connection.update", "data": {"state": "open", "wuid": "212723688997@s.whatsapp.net",
                                                 "profileName": "Roland", "statusReason": 200}})[0]
    assert (ev.status, ev.phone, ev.account, ev.detail) == ("connected", "212723688997", "Roland", "")
    with client.c.application.app_context():
        csvc.set_status(conn["id"], ev.status, ev.detail, ev.phone, ev.account, ev.picture)
    n = next(c for c in client.get("/api/whatsapp/connections").get_json()["connections"] if c["id"] == conn["id"])
    assert (n["phone_number"], n["account_name"]) == ("+212723688997", "Roland")
