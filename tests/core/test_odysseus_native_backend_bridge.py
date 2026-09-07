from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

_ODY_ROOT = Path(__file__).resolve().parents[2] / "backend" / "odysseus"
if str(_ODY_ROOT) not in sys.path:
    sys.path.insert(0, str(_ODY_ROOT))

from backend.core.routers.odysseus_http_router import register_odysseus_http_routes


def test_odysseus_native_chat_persists_in_native_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "odysseus-data"
    data_dir.mkdir()
    monkeypatch.setenv("ODYSSEUS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{data_dir / 'app.db'}")

    from core.database import ChatMessage, Session, SessionLocal, init_db

    init_db()

    app = FastAPI()
    register_odysseus_http_routes(app)
    client = TestClient(app)

    models_response = client.get("/api/models")
    assert models_response.status_code == 200
    models_payload = models_response.json()
    assert "monika-companion" not in models_payload["models"]
    assert models_payload["default_model"] == "gemini-2.5-flash"
    assert models_payload["items"][0]["endpoint_id"] == "gemini-text"

    default_response = client.get("/api/default-chat")
    assert default_response.status_code == 200
    payload = default_response.json()
    assert payload["endpoint_id"] == "gemini-text"
    assert payload["model"] == "gemini-2.5-flash"

    generated = {}

    class FakeGeminiTextProvider:
        def __init__(self, **kwargs):
            pass

        async def generate(self, request):
            generated["model"] = request.model
            generated["system_instruction"] = request.system_instruction
            return "Wybrany model działa."

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        "backend.conversation.providers.GeminiTextProvider",
        FakeGeminiTextProvider,
    )

    session_id = "native-session-test"
    response = client.post(
        "/api/chat_stream",
        data={
            "message": "Test integracji natywnej",
            "session": session_id,
            "selected_model": "gemini-2.5-pro",
            "selected_endpoint_id": "gemini-text",
        },
    )

    assert response.status_code == 200
    body = response.text
    assert "data: [DONE]" in body
    assert generated["model"] == "gemini-2.5-pro"
    assert "ZASADY OPERACYJNE" in generated["system_instruction"]

    with SessionLocal() as db:
        session = db.query(Session).filter(Session.id == session_id).first()
        assert session is not None
        assert session.model == "gemini-2.5-pro"
        assert session.name
        messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).all()
        assert len(messages) >= 2
