import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.config import TestConfig  # noqa: E402
from app.whatsapp.adapters import SandboxAdapter  # noqa: E402


@pytest.fixture
def app(tmp_path):
    SandboxAdapter.sent.clear()
    return create_app(TestConfig, INSTANCE_DIR=tmp_path, DATABASE_PATH=tmp_path / "test.db",
                      UPLOAD_DIR=tmp_path / "uploads")


class Client:
    """Test client that carries the CSRF header like the browser does."""

    def __init__(self, app):
        self.c = app.test_client()
        self.h = {}

    def register(self, email="owner@x.co", workspace="Acme"):
        r = self.c.post("/api/auth/register", json={"email": email, "password": "password1", "workspace": workspace})
        assert r.status_code == 200, r.get_json()
        self.h = {"X-CSRF-Token": self.c.get("/api/me").get_json()["csrf"]}
        return self

    def __getattr__(self, method):
        def call(url, **kw):
            kw.setdefault("headers", self.h)
            return getattr(self.c, method)(url, **kw)
        return call


@pytest.fixture
def client(app):
    return Client(app).register()


@pytest.fixture
def setup_chat(client):
    """A sandbox number with Customer Service on it and one FAQ file."""
    agents = {a["name"]: a["id"] for a in client.get("/api/agents").get_json()["agents"]}
    client.post("/api/knowledge/text", json={"title": "FAQ", "agent_ids": [agents["Customer Service"]],
                                             "text": "Sale items can be returned within 14 days for store credit."})
    conn = client.post("/api/whatsapp/connections", json={"name": "Support", "provider": "sandbox"}).get_json()["connection"]

    def configure(mode):
        client.patch(f"/api/whatsapp/connections/{conn['id']}",
                     json={"default_agent_id": agents["Customer Service"], "default_mode": mode})
        return conn
    return client, agents, configure
