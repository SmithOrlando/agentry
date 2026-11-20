from conftest import Client


def test_register_creates_workspace_with_starter_agents(client):
    agents = client.get("/api/agents").get_json()["agents"]
    assert {a["name"] for a in agents} == {"Customer Service", "Project Manager", "Marketing", "Sales"}


def test_api_requires_login(app):
    assert app.test_client().get("/api/agents").status_code == 401


def test_mutations_require_csrf(client):
    r = client.c.post("/api/agents", json={"name": "X"})  # no header
    assert r.status_code == 400 and r.get_json()["error"] == "csrf_failed"


def test_workspaces_are_isolated(app):
    a = Client(app).register("a@x.co", "A")
    b = Client(app).register("b@x.co", "B")
    a_agent = a.get("/api/agents").get_json()["agents"][0]["id"]
    assert b.patch(f"/api/agents/{a_agent}", json={"name": "hijack"}).status_code == 404
    assert b.delete(f"/api/agents/{a_agent}").status_code == 404


def test_viewer_cannot_change_settings(app, client):
    link = client.post("/api/team/invites", json={"emails": "v@x.co", "role": "viewer"}).get_json()["invites"][0]["link"]
    token = link.split("invite=")[1]
    v = Client(app)
    r = v.c.post("/api/auth/register", json={"email": "v@x.co", "password": "password1", "invite_token": token})
    assert r.status_code == 200
    v.h = {"X-CSRF-Token": v.c.get("/api/me").get_json()["csrf"]}
    assert v.get("/api/agents").status_code == 200
    assert v.patch("/api/settings/llm", json={"source": "byok"}).status_code == 403


def test_provider_key_is_never_returned(client):
    client.put("/api/settings/providers/openai", json={"api_key": "sk-secret-1234"})
    body = client.get("/api/settings/llm").get_data(as_text=True)
    assert "sk-secret" not in body and '"last4":"1234"' in body.replace(" ", "")


def test_platform_model_is_hidden(client):
    data = client.get("/api/settings/llm").get_json()
    assert data["active_model"] == "Platform default"
    assert "mock" not in client.get("/api/agents").get_data(as_text=True)


def test_api_only_json_everywhere(app):
    c = app.test_client()
    assert c.get("/").get_json()["service"] == "agentry-api"
    r = c.get("/inbox")  # old page route: now a JSON 404, the Vue app owns this URL
    assert r.status_code == 404 and r.get_json()["error"] == "not_found"


def test_invite_link_points_at_frontend(app, client):
    app.config["FRONTEND_URL"] = "https://app.example.com"
    link = client.post("/api/team/invites", json={"emails": "n@x.co"}).get_json()["invites"][0]["link"]
    assert link.startswith("https://app.example.com/register?invite=")


def test_passwords_work_without_scrypt(app, monkeypatch):
    """macOS system Python (LibreSSL) has no hashlib.scrypt: registration and login must still work."""
    import hashlib
    monkeypatch.delattr(hashlib, "scrypt", raising=False)
    c = Client(app).register("noscrypt@x.co", "NoScrypt")
    from app.db import query_one
    with app.app_context():
        assert query_one("SELECT password_hash FROM users WHERE email = ?", ["noscrypt@x.co"])["password_hash"].startswith("pbkdf2:sha256:600000")
    c.post("/api/auth/logout")
    assert c.c.post("/api/auth/login", json={"email": "noscrypt@x.co", "password": "password1"}).status_code == 200
    assert c.c.post("/api/auth/login", json={"email": "noscrypt@x.co", "password": "wrong-pass"}).status_code == 401
