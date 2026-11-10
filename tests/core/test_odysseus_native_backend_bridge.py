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


def test_odysseus_model_routes_expose_default_chat(tmp_path, monkeypatch):
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
