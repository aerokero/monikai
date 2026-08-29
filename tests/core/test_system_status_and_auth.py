import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.routers.system_http_router import register_system_http_routes


def test_healthz_and_api_health():
    app = FastAPI()
    register_system_http_routes(app)
    client = TestClient(app)

    res1 = client.get("/healthz")
    assert res1.status_code == 200
    assert res1.json() == {"status": "ok", "service": "monikai"}

    res2 = client.get("/api/v1/health")
    assert res2.status_code == 200
    assert res2.json() == {"status": "ok", "service": "monikai"}


def test_api_v1_status_diagnostics():
    app = FastAPI()
    register_system_http_routes(
        app,
        get_spotify_manager=lambda: None,
        get_audio_loop=lambda: None,
        get_minecraft_bot_manager=lambda: None,
    )
    client = TestClient(app)

    res = client.get("/api/v1/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["version"] == "2.0-workspace"
    assert "client" in data
    assert "subsystems" in data
    assert data["subsystems"]["audio_loop"] == "stopped"
    assert data["subsystems"]["spotify"] == "unavailable"
