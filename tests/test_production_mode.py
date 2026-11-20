"""Production defaults: no placeholder model, no sandbox numbers, no Simulate."""
import pytest

from app import create_app
from app.config import TestConfig
from tests.conftest import Client


@pytest.fixture
def prod(tmp_path):
    app = create_app(TestConfig, INSTANCE_DIR=tmp_path, DATABASE_PATH=tmp_path / "p.db", UPLOAD_DIR=tmp_path / "u",
                     ENABLE_TEST_TOOLS=False, PLATFORM_LLM_PROVIDER="", PLATFORM_LLM_MODEL="")
    return Client(app).register()


def test_no_model_says_so_instead_of_faking_a_reply(prod):
    me = prod.get("/api/me").get_json()
    assert me["setup"] == {"model_ready": False, "real_whatsapp": False, "test_tools": False}
    sid = prod.post("/api/playground/sessions", json={}).get_json()["id"]
    r = prod.post(f"/api/playground/sessions/{sid}/messages", json={"text": "hello"})
    assert r.status_code == 502 and "Settings" in r.get_json()["error"] and "mock" not in r.get_data(as_text=True)
    assert prod.get("/api/settings/llm").get_json()["active_model"] == "No model set up"


def test_mock_platform_model_is_refused_without_test_tools(tmp_path):
    app = create_app(TestConfig, INSTANCE_DIR=tmp_path, DATABASE_PATH=tmp_path / "m.db", UPLOAD_DIR=tmp_path / "u",
                     ENABLE_TEST_TOOLS=False)  # PLATFORM_LLM_PROVIDER is still "mock" here
    c = Client(app).register()
    assert c.get("/api/me").get_json()["setup"]["model_ready"] is False


def test_sandbox_and_simulate_are_disabled(prod):
    r = prod.post("/api/whatsapp/connections", json={"name": "x", "provider": "sandbox", "config": {}})
    assert r.status_code == 400
    assert prod.post("/api/whatsapp/connections/1/simulate", json={"text": "hi"}).status_code == 404
    assert prod.c.post("/webhooks/sandbox/1/token", json={"text": "hi"}).status_code == 404
