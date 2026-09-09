"""Typed configuration for MonikAI transports and channel profiles.

The generic Integrations store is designed for user-authored HTTP APIs and
webhooks. Telegram, Discord and Home Assistant also have runtime lifecycle,
access-policy and persona concerns, so they need a small typed layer of their
own. Secrets still use the same Fernet-backed storage used by other native
Odysseus credentials.

The module intentionally has no FastAPI dependency. It can be used by the
settings routes, startup lifecycle and tests without importing the application
object. Environment variables remain a backwards-compatible read fallback;
values entered in Settings are persisted in ``channel_config.json``.
"""

from __future__ import annotations

import copy
import json
import os
import re
import socket
from typing import Any, Dict, Iterable, Mapping
from urllib.parse import urlparse

from core.atomic_io import atomic_write_json
from core.platform_compat import safe_chmod
from src.constants import CHANNEL_CONFIG_FILE, SETTINGS_FILE
from src.secret_storage import decrypt, encrypt


INTEGRATION_IDS = ("home_assistant", "telegram", "discord")
PROFILE_IDS = ("desktop", "telegram", "discord")
SECRET_FIELDS = frozenset({"token"})
ALLOWED_TOOL_SCOPES = frozenset({
    "list_smart_devices",
    "control_light",
    "manage_shopping_list",
})


DEFAULT_CHANNEL_CONFIG: Dict[str, Any] = {
    "version": 1,
    "integrations": {
        "home_assistant": {
            "enabled": False,
            "url": "",
            "token": "",
            "entities_filter": ["light.*", "switch.*", "scene.*"],
        },
        "telegram": {
            "enabled": False,
            "token": "",
            "allowed_chat_ids": [],
            "allow_groups": False,
            "proactive_enabled": False,
            "profile_id": "telegram",
        },
        "discord": {
            "enabled": False,
            "token": "",
            "allowed_channel_ids": [],
            "allowed_guild_ids": [],
            "allowed_user_ids": [],
            "allow_dms": True,
            "require_mention": True,
            "proactive_enabled": False,
            "profile_id": "discord",
        },
    },
    "profiles": {
        "desktop": {
            "preset_id": "monika",
            "prompt_overlay": "",
            "model": "",
            "endpoint_id": "",
            "tool_scopes": sorted(ALLOWED_TOOL_SCOPES),
            "require_confirmation": True,
        },
        "telegram": {
            "preset_id": "monika",
            "prompt_overlay": "",
            "model": "",
            "endpoint_id": "",
            # Read-only smart-home discovery is a safe first default. Mutating
            # operations will be enabled explicitly and audited in the next
            # integration/runtime slice.
            "tool_scopes": ["list_smart_devices"],
            "require_confirmation": True,
        },
        "discord": {
            "preset_id": "monika",
            "prompt_overlay": "",
            "model": "",
            "endpoint_id": "",
            "tool_scopes": ["list_smart_devices"],
            "require_confirmation": True,
        },
    },
}


_PROFILE_FIELDS = frozenset({
    "preset_id",
    "prompt_overlay",
    "model",
    "endpoint_id",
    "tool_scopes",
    "require_confirmation",
})
_INTEGRATION_FIELDS = {
    "home_assistant": frozenset({"enabled", "url", "token", "entities_filter"}),
    "telegram": frozenset({
        "enabled", "token", "allowed_chat_ids", "allow_groups",
        "proactive_enabled", "profile_id",
    }),
    "discord": frozenset({
        "enabled", "token", "allowed_channel_ids", "allowed_guild_ids",
        "allowed_user_ids", "allow_dms", "require_mention",
        "proactive_enabled", "profile_id",
    }),
}


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for key, value in (override or {}).items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _read_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _legacy_home_assistant_config() -> Dict[str, Any]:
    """Read the old smart_home block without changing the legacy file."""
    settings = _read_json(SETTINGS_FILE)
    legacy = ((settings.get("smart_home") or {}).get("home_assistant") or {})
    if not isinstance(legacy, Mapping):
        return {}
    result: Dict[str, Any] = {}
    for key in ("url", "token", "entities_filter"):
        if key in legacy and legacy[key] not in (None, "", []):
            result[key] = copy.deepcopy(legacy[key])
    if result.get("url") or result.get("token"):
        result["enabled"] = True
    return result


def _base_with_legacy() -> Dict[str, Any]:
    base = copy.deepcopy(DEFAULT_CHANNEL_CONFIG)
    legacy_ha = _legacy_home_assistant_config()
    if legacy_ha:
        base["integrations"]["home_assistant"].update(legacy_ha)
    return base


def _decrypt_secrets(config: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(config)
    for integration_id in INTEGRATION_IDS:
        item = result.get("integrations", {}).get(integration_id, {})
        if isinstance(item, dict) and item.get("token"):
            item["token"] = decrypt(str(item["token"]))
    return result


def _encrypt_secrets(config: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(config)
    for integration_id in INTEGRATION_IDS:
        item = result.get("integrations", {}).get(integration_id, {})
        if isinstance(item, dict) and item.get("token"):
            item["token"] = encrypt(str(item["token"]))
    return result


def _read_storage() -> Dict[str, Any]:
    return _decrypt_secrets(_read_json(CHANNEL_CONFIG_FILE))


def _parse_id_list(value: Any, *, allow_negative: bool = False) -> list[int]:
    if value is None:
        return []
    if isinstance(value, str):
        values: Iterable[Any] = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = [value]

    result: list[int] = []
    seen = set()
    pattern = r"^-?\d+$" if allow_negative else r"^\d+$"
    for raw in values:
        text = str(raw or "").strip()
        if not text or not re.match(pattern, text):
            continue
        try:
            parsed = int(text)
        except (TypeError, ValueError):
            continue
        if parsed not in seen:
            seen.add(parsed)
            result.append(parsed)
        if len(result) >= 200:
            break
    return result


def _normalize_url(value: Any) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must be an HTTP(S) URL")
    if parsed.query or parsed.fragment:
        raise ValueError("URL must not include a query string or fragment")
    return text


def _normalize_filters(value: Any) -> list[str]:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = []
    result = []
    for raw in values:
        text = str(raw or "").strip()
        if text and text not in result:
            result.append(text[:128])
        if len(result) >= 50:
            break
    return result


def normalize_channel_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a validated, storage-safe config with only known fields."""
    merged = _deep_merge(DEFAULT_CHANNEL_CONFIG, config or {})
    normalized = copy.deepcopy(DEFAULT_CHANNEL_CONFIG)

    integrations = merged.get("integrations") or {}
    for integration_id in INTEGRATION_IDS:
        incoming = integrations.get(integration_id) or {}
        if not isinstance(incoming, Mapping):
            incoming = {}
        target = normalized["integrations"][integration_id]
        target["enabled"] = bool(incoming.get("enabled", target["enabled"]))
        target["token"] = str(incoming.get("token") or "").strip()

        if integration_id == "home_assistant":
            target["url"] = _normalize_url(incoming.get("url"))
            target["entities_filter"] = _normalize_filters(incoming.get("entities_filter"))
        elif integration_id == "telegram":
            target["allowed_chat_ids"] = _parse_id_list(incoming.get("allowed_chat_ids"), allow_negative=True)
            target["allow_groups"] = bool(incoming.get("allow_groups", False))
            target["proactive_enabled"] = bool(incoming.get("proactive_enabled", False))
            profile_id = str(incoming.get("profile_id") or "telegram").strip()
            target["profile_id"] = profile_id if profile_id in PROFILE_IDS else "telegram"
        else:
            target["allowed_channel_ids"] = _parse_id_list(incoming.get("allowed_channel_ids"))
            target["allowed_guild_ids"] = _parse_id_list(incoming.get("allowed_guild_ids"))
            target["allowed_user_ids"] = _parse_id_list(incoming.get("allowed_user_ids"))
            target["allow_dms"] = bool(incoming.get("allow_dms", True))
            target["require_mention"] = bool(incoming.get("require_mention", True))
            target["proactive_enabled"] = bool(incoming.get("proactive_enabled", False))
            profile_id = str(incoming.get("profile_id") or "discord").strip()
            target["profile_id"] = profile_id if profile_id in PROFILE_IDS else "discord"

    profiles = merged.get("profiles") or {}
    for profile_id in PROFILE_IDS:
        incoming = profiles.get(profile_id) or {}
        if not isinstance(incoming, Mapping):
            incoming = {}
        target = normalized["profiles"][profile_id]
        target["preset_id"] = str(incoming.get("preset_id") or "monika").strip()[:100]
        target["prompt_overlay"] = str(incoming.get("prompt_overlay") or "")[:4000]
        target["model"] = str(incoming.get("model") or "").strip()[:200]
        target["endpoint_id"] = str(incoming.get("endpoint_id") or "").strip()[:200]
        raw_scopes = incoming.get("tool_scopes")
        if not isinstance(raw_scopes, (list, tuple, set)):
            raw_scopes = []
        target["tool_scopes"] = [
            str(scope).strip() for scope in raw_scopes
            if str(scope).strip() in ALLOWED_TOOL_SCOPES
        ]
        target["tool_scopes"] = list(dict.fromkeys(target["tool_scopes"]))
        target["require_confirmation"] = bool(incoming.get("require_confirmation", True))

    normalized["version"] = 1
    return normalized


def load_channel_config() -> Dict[str, Any]:
    """Load stored configuration, transparently including legacy HA values."""
    return normalize_channel_config(_deep_merge(_base_with_legacy(), _read_storage()))


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _apply_environment_fallback(config: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(config)
    integrations = result["integrations"]
    storage = _read_json(CHANNEL_CONFIG_FILE)
    stored_integrations = storage.get("integrations") if isinstance(storage, Mapping) else {}
    if not isinstance(stored_integrations, Mapping):
        stored_integrations = {}

    telegram = integrations["telegram"]
    telegram_stored = isinstance(stored_integrations.get("telegram"), Mapping)
    if not telegram.get("token"):
        env_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if env_token:
            telegram["token"] = env_token
            if not telegram_stored:
                telegram["enabled"] = True
    if not telegram.get("allowed_chat_ids"):
        telegram["allowed_chat_ids"] = _parse_id_list(
            os.getenv("TELEGRAM_ALLOWED_CHAT_IDS") or os.getenv("TELEGRAM_ALLOWED_CHAT_ID"),
            allow_negative=True,
        )
    if not telegram_stored:
        telegram["allow_groups"] = _env_flag("TELEGRAM_ALLOW_GROUPS", telegram["allow_groups"])

    discord = integrations["discord"]
    discord_stored = isinstance(stored_integrations.get("discord"), Mapping)
    if not discord.get("token"):
        env_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
        if env_token:
            discord["token"] = env_token
            if not discord_stored:
                discord["enabled"] = True
    if not discord.get("allowed_channel_ids"):
        discord["allowed_channel_ids"] = _parse_id_list(os.getenv("DISCORD_ALLOWED_CHANNEL_IDS"))
    if not discord.get("allowed_guild_ids"):
        discord["allowed_guild_ids"] = _parse_id_list(os.getenv("DISCORD_ALLOWED_GUILD_IDS"))
    if not discord.get("allowed_user_ids"):
        discord["allowed_user_ids"] = _parse_id_list(os.getenv("DISCORD_ALLOWED_USER_IDS"))
    if not discord_stored:
        discord["allow_dms"] = _env_flag("DISCORD_ALLOW_DMS", discord["allow_dms"])
        discord["require_mention"] = _env_flag("DISCORD_REQUIRE_MENTION", discord["require_mention"])

    return normalize_channel_config(result)


def get_effective_channel_config() -> Dict[str, Any]:
    return _apply_environment_fallback(load_channel_config())


def get_channel_integration(integration_id: str) -> Dict[str, Any]:
    if integration_id not in INTEGRATION_IDS:
        raise ValueError(f"Unknown channel integration: {integration_id}")
    return copy.deepcopy(get_effective_channel_config()["integrations"][integration_id])


def get_channel_profile(profile_id: str) -> Dict[str, Any]:
    if profile_id not in PROFILE_IDS:
        raise ValueError(f"Unknown channel profile: {profile_id}")
    return copy.deepcopy(get_effective_channel_config()["profiles"][profile_id])


async def test_channel_integration(integration_id: str) -> Dict[str, Any]:
    """Perform a read-only connectivity check for a typed channel."""
    if integration_id not in INTEGRATION_IDS:
        raise ValueError(f"Unknown channel integration: {integration_id}")

    item = get_channel_integration(integration_id)
    if not item.get("enabled"):
        return {"ok": False, "message": "Integration is disabled"}

    token = str(item.get("token") or "").strip()
    if integration_id == "home_assistant":
        base_url = str(item.get("url") or "").strip().rstrip("/")
        if not base_url or not token:
            return {"ok": False, "message": "Home Assistant URL and token are required"}
        # Home Assistant's API root is `/api/`; `/api` is a separate 404 route
        # on the reverse proxy used by the local deployment.
        url = f"{base_url}/api/"
        headers = {"Authorization": f"Bearer {token}"}
    elif integration_id == "telegram":
        if not token:
            return {"ok": False, "message": "Telegram bot token is required"}
        url = f"https://api.telegram.org/bot{token}/getMe"
        headers = {}
    else:
        if not token:
            return {"ok": False, "message": "Discord bot token is required"}
        url = "https://discord.com/api/v10/users/@me"
        headers = {"Authorization": f"Bot {token}"}

    try:
        import httpx

        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            response = await client.get(url, headers=headers)
        if response.is_success:
            return {"ok": True, "message": "Connection successful"}
        if response.status_code in (401, 403):
            return {"ok": False, "message": "Connection rejected — check the token"}
        return {"ok": False, "message": f"Service returned HTTP {response.status_code}"}
    except Exception as exc:
        # Never return the URL with a token embedded (Telegram URL contains it).
        return {"ok": False, "message": _format_connection_error(integration_id, exc)}


def _format_connection_error(integration_id: str, exc: Exception) -> str:
    """Turn transport exceptions into actionable, secret-free UI messages."""
    service = {
        "home_assistant": "Home Assistant",
        "telegram": "Telegram",
        "discord": "Discord",
    }.get(integration_id, "Service")
    error_text = str(exc or "").lower()
    cause = exc
    causes = []
    while cause is not None and len(causes) < 5:
        causes.append(cause)
        cause = getattr(cause, "__cause__", None) or getattr(cause, "__context__", None)

    dns_failure = any(
        isinstance(item, socket.gaierror)
        or any(marker in str(item).lower() for marker in (
            "name or service not known",
            "temporary failure in name resolution",
            "nodename nor servname",
            "getaddrinfo failed",
        ))
        for item in causes
    )
    if dns_failure:
        return f"DNS lookup failed — MonikAI cannot resolve the {service} host. Check the hostname or use a reachable LAN IP."

    error_name = type(exc).__name__.lower()
    if "timeout" in error_name or "timed out" in error_text:
        return f"Connection timed out — check the {service} URL, port and firewall."
    if "unsupportedprotocol" in error_name:
        return f"Invalid {service} URL — use an http:// or https:// address."
    if "connecterror" in error_name or "connection refused" in error_text:
        return f"Could not connect to {service} — check the URL, port and network access."
    return f"Connection failed — check the {service} URL and network access."


def _mask_token(value: Any) -> str:
    token = str(value or "")
    return f"{token[:4]}****" if token else ""


def public_channel_config() -> Dict[str, Any]:
    """Return UI-safe config; token values are never returned."""
    config = get_effective_channel_config()
    safe = copy.deepcopy(config)
    for integration_id in INTEGRATION_IDS:
        item = safe["integrations"][integration_id]
        token = item.get("token", "")
        item["token"] = ""
        item["token_configured"] = bool(token)
        item["token_masked"] = _mask_token(token)
    safe["runtime"] = {
        "reload_supported": False,
        "restart_required": True,
    }
    return safe


def save_channel_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = normalize_channel_config(config)
    os.makedirs(os.path.dirname(CHANNEL_CONFIG_FILE), exist_ok=True)
    atomic_write_json(CHANNEL_CONFIG_FILE, _encrypt_secrets(normalized), indent=2)
    safe_chmod(CHANNEL_CONFIG_FILE, 0o600)
    return normalized


def update_channel_config(patch: Mapping[str, Any]) -> Dict[str, Any]:
    """Apply a constrained patch and persist it.

    An empty token means "keep the current value" for password inputs. The UI
    can explicitly clear a secret with ``clear_token: true``.
    """
    if not isinstance(patch, Mapping):
        raise ValueError("Channel configuration must be an object")

    current = load_channel_config()
    for section in ("integrations", "profiles"):
        incoming_section = patch.get(section)
        if incoming_section is None:
            continue
        if not isinstance(incoming_section, Mapping):
            raise ValueError(f"{section} must be an object")

        if section == "integrations":
            for integration_id, incoming in incoming_section.items():
                if integration_id not in INTEGRATION_IDS:
                    raise ValueError(f"Unknown channel integration: {integration_id}")
                if not isinstance(incoming, Mapping):
                    raise ValueError(f"{integration_id} must be an object")
                unknown = set(incoming) - set(_INTEGRATION_FIELDS[integration_id]) - {"clear_token"}
                if unknown:
                    raise ValueError(f"Unknown fields for {integration_id}: {', '.join(sorted(unknown))}")
                target = current["integrations"][integration_id]
                if incoming.get("clear_token") is True:
                    target["token"] = ""
                for key, value in incoming.items():
                    if key == "token":
                        if value is None:
                            target[key] = ""
                        elif str(value).strip():
                            target[key] = str(value).strip()
                    elif key != "clear_token":
                        target[key] = copy.deepcopy(value)
        else:
            for profile_id, incoming in incoming_section.items():
                if profile_id not in PROFILE_IDS:
                    raise ValueError(f"Unknown channel profile: {profile_id}")
                if not isinstance(incoming, Mapping):
                    raise ValueError(f"{profile_id} must be an object")
                unknown = set(incoming) - set(_PROFILE_FIELDS)
                if unknown:
                    raise ValueError(f"Unknown fields for {profile_id}: {', '.join(sorted(unknown))}")
                current["profiles"][profile_id].update(copy.deepcopy(dict(incoming)))

    return save_channel_config(current)


__all__ = [
    "DEFAULT_CHANNEL_CONFIG",
    "get_channel_integration",
    "get_channel_profile",
    "get_effective_channel_config",
    "load_channel_config",
    "normalize_channel_config",
    "public_channel_config",
    "save_channel_config",
    "test_channel_integration",
    "update_channel_config",
]
