from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ODY_ROOT = Path(__file__).resolve().parents[2] / "backend" / "odysseus"
if str(ODY_ROOT) not in sys.path:
    sys.path.insert(0, str(ODY_ROOT))

from src import channel_config  # noqa: E402
from src import secret_storage  # noqa: E402


@pytest.fixture
def isolated_channel_config(tmp_path, monkeypatch):
    config_path = tmp_path / "channel_config.json"
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(channel_config, "CHANNEL_CONFIG_FILE", str(config_path))
    monkeypatch.setattr(channel_config, "SETTINGS_FILE", str(settings_path))
    monkeypatch.setattr(secret_storage, "_KEY_PATH", tmp_path / ".app_key")
    monkeypatch.setattr(secret_storage, "_fernet", None)
    for name in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_CHAT_IDS",
        "TELEGRAM_ALLOWED_CHAT_ID",
        "DISCORD_BOT_TOKEN",
        "DISCORD_ALLOWED_CHANNEL_IDS",
    ):
        monkeypatch.delenv(name, raising=False)
    return config_path, settings_path


def test_legacy_home_assistant_is_read_and_public_token_is_masked(isolated_channel_config):
    config_path, settings_path = isolated_channel_config
    settings_path.write_text(
        json.dumps({
            "smart_home": {
                "home_assistant": {
                    "url": "http://homeassistant.local:8123/",
                    "token": "legacy-secret-token",
                    "entities_filter": ["light.*", "switch.salon"],
                }
            }
        }),
        encoding="utf-8",
    )

    public = channel_config.public_channel_config()
    ha = public["integrations"]["home_assistant"]

    assert ha["enabled"] is True
    assert ha["url"] == "http://homeassistant.local:8123"
    assert ha["token"] == ""
    assert ha["token_configured"] is True
    assert ha["token_masked"] == "lega****"
    assert not config_path.exists(), "GET must not write a migration unexpectedly"


def test_update_persists_encrypted_token_and_blank_token_keeps_it(isolated_channel_config):
    config_path, _ = isolated_channel_config

    channel_config.update_channel_config({
        "integrations": {
            "home_assistant": {
                "enabled": True,
                "url": "https://ha.example.test",
                "token": "super-secret",
                "entities_filter": "light.*, switch.*",
            },
        },
        "profiles": {
            "telegram": {
                "preset_id": "custom",
                "prompt_overlay": "Keep Telegram replies concise.",
                "tool_scopes": ["list_smart_devices", "not-a-tool"],
            },
        },
    })

    stored = json.loads(config_path.read_text(encoding="utf-8"))
    assert stored["integrations"]["home_assistant"]["token"].startswith("enc:")
    assert "super-secret" not in config_path.read_text(encoding="utf-8")

    channel_config.update_channel_config({
        "integrations": {"home_assistant": {"url": "https://ha.example.test/"}},
    })
    runtime = channel_config.get_channel_integration("home_assistant")
    assert runtime["token"] == "super-secret"
    assert runtime["url"] == "https://ha.example.test"
    assert channel_config.get_channel_profile("telegram")["tool_scopes"] == ["list_smart_devices"]

    channel_config.update_channel_config({
        "integrations": {"home_assistant": {"clear_token": True}},
    })
    assert channel_config.get_channel_integration("home_assistant")["token"] == ""


def test_invalid_urls_and_unknown_fields_are_rejected(isolated_channel_config):
    with pytest.raises(ValueError, match=r"HTTP\(S\)"):
        channel_config.update_channel_config({
            "integrations": {"home_assistant": {"url": "file:///etc/passwd"}},
        })

    with pytest.raises(ValueError, match="Unknown fields"):
        channel_config.update_channel_config({
            "integrations": {"telegram": {"callback_url": "https://example.test"}},
        })


def test_connection_errors_explain_dns_failures_without_secrets():
    error = OSError(-2, "Name or service not known")

    message = channel_config._format_connection_error("home_assistant", error)

    assert message.startswith("DNS lookup failed")
    assert "Home Assistant" in message
    assert "token" not in message.lower()


def test_channel_config_routes_are_available_in_single_user_mode(isolated_channel_config, monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from core.auth import AuthManager
    from routes.auth_routes import setup_auth_routes

    app = FastAPI()
    app.state.auth_manager = AuthManager(str(tmp_path / "auth.json"))
    app.include_router(setup_auth_routes(app.state.auth_manager))
    client = TestClient(app)

    response = client.get("/api/auth/channel-config")
    assert response.status_code == 200
    assert response.json()["integrations"]["telegram"]["token"] == ""

    response = client.put(
        "/api/auth/channel-config",
        json={
            "integrations": {
                "telegram": {
                    "enabled": True,
                    "token": "telegram-secret",
                    "allowed_chat_ids": ["123", "invalid"],
                },
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()["config"]["integrations"]["telegram"]
    assert payload["token"] == ""
    assert payload["token_configured"] is True
    assert payload["allowed_chat_ids"] == [123]
