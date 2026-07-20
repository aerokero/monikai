"""Settings persistence and migration helpers for MonikAI."""

from __future__ import annotations

import json
import os
from copy import deepcopy

from backend.services.daily_briefing import DEFAULT_SECTIONS, normalize_profile
from .config import SETTINGS_PATH

DEFAULT_SETTINGS = {
    "face_auth_enabled": False,
    "show_internal_thoughts": False,
    "tool_permissions": {
        "cancel_reminder": True,
        "control_light": True,
        "clear_work_memory": True,
        "notes_set": True,
        "run_web_agent": False,  # Allow explicit browser-agent tasks without confirmation
        "run_openclaw_agent": True,
        "manage_agent_job": True,
        "request_program_shutdown": False,
        "list_openclaw_skills": False,
        "list_skills": False,
        "get_openclaw_skill": False,
        "get_skill": False,
        "refresh_openclaw_skills": False,
        "refresh_skills": False,
        "run_openclaw_skill_command": True,
        "run_skill_command": True,
        "spotify_get_auth_url": False,
        "spotify_get_status": False,
        "spotify_get_now_playing": False,
        "spotify_list_playlists": False,
        "spotify_recently_played": False,
        "write_file": True,
    },
    "kasa_devices": [],
    "smart_home": {
        "kasa": {
            "devices": [],
        },
        "hue": {
            "bridge_ip": None,
            "api_key": None,
            "devices": [],
        },
        "home_assistant": {
            "url": None,
            "token": None,
            "entities_filter": ["light.*", "switch.*"],
            "entities": [],
        },
    },
    "gemini_model_preset": "2.5",
    "gemini_voice": "Leda",
    "camera_flipped": False,
    "camera_source": "frontend",
    "video_mode": "none",
    "camera_capture": {
        "fps": 2.0,
        "max_size": 1024,
        "jpeg_quality": 80,
    },
    "screen_capture": {
        "fps": 6.0,
        "max_size": 1280,
        "jpeg_quality": 70,
        "monitor": 1,
        "format": "jpeg",
        "region": None,
        "mode": "continuous",
    },
    "proactivity": {
        "idle_nudges": {
            "enabled": True,
            "threshold_sec": 900,
            "cooldown_sec": 1800,
            "min_ai_quiet_sec": 60,
            "max_per_session": 3,
            "max_per_hour": 4,
            "topic_memory_size": 6,
            "score_threshold": 0.98,
            "quiet_hours_enabled": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "06:00",
            "adaptive_enabled": True,
            "adaptive_backoff_step": 0.7,
            "adaptive_max_multiplier": 4.0,
            "recent_user_memory_size": 3,
            "recent_user_max_chars": 160,
            "question_min_interval_sec": 1800.0,
            "question_backoff_1_sec": 2700.0,
            "question_backoff_2_sec": 3600.0,
            "startup_grace_sec": 600.0,
            "min_user_messages_before_nudge": 2,
        },
        "reasoning": {
            "enabled": True,
            "interval_sec": 120.0,
        },
    },
    "daily_briefing": {
        "enabled": True,
        "cache_minutes": 20,
        "use_v2_briefing": False,
        "profile": {
            "pinned_sections": ["weather"],
            "preferred_sections": [],
            "auto_slots": 1,
            "candidate_pool": list(DEFAULT_SECTIONS.keys()),
            "language_mode": "auto",
            "max_items_per_section": 7,
        },
    },
    "vn": {
        "branch_selection_mode": "heuristic",
    },
    # Myśliciel (drugi mózg): gemini-3.5-flash przygotowuje analizę i rdzeń
    # odpowiedzi, wstrzykiwane do sesji Live jako <response_brief>.
    # Off = zachowanie bez zmian.
    "thinker": {
        "enabled": False,
        "min_chars": 18,
        # Model głosowy jest rendererem; każda znacząca tura powinna dostać
        # brief, zamiast polegać na jego płytkim natywnym rozumowaniu.
        "min_interval_sec": 0.0,
        # 0 = flash zapisuje rozumowanie jawnie w briefie bez dodatkowej,
        # ukrytej warstwy thinking, która nie mieściła się w timeout_sec.
        "thinking_budget": 0,
        "timeout_sec": 8.0,
        # Przerwa po 429/503 — 120 s wyciszało mózg na kilka tur rozmowy.
        "cooldown_sec": 60.0,
    },
    "minecraft_autonomy": {
        "enabled": True,
        "auto_game_mode_on_connect": True,
        "scan_interval_sec": 18.0,
        "look_interval_sec": 14.0,
        "move_interval_sec": 20.0,
        "min_bot_action_gap_sec": 6.0,
        "max_actions_per_tick": 1,
        "comment_interval_sec": 42.0,
        "curiosity_interval_sec": 45.0,
        "proposal_interval_sec": 65.0,
        "scan_range": 40,
        "look_entity_max_distance": 20,
        "wander_radius": 8,
        "follow_radius": 10,
        "move_range": 2,
        "comment_to_model": True,
        "comment_to_ui": True,
        "comment_style": "mixed",
        "comment_user_ratio": 0.55,
    },
}

SETTINGS_FILE = SETTINGS_PATH
SETTINGS = deepcopy(DEFAULT_SETTINGS)


def _deep_merge_dict(base: dict, override: dict) -> dict:
    merged = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged.get(key) or {}, value)
        else:
            merged[key] = value
    return merged


def _migrate_settings_v1_to_v2(settings: dict) -> dict:
    migrated = dict(settings)
    old_kasa = migrated.pop("kasa_devices", [])
    if old_kasa and isinstance(old_kasa, list):
        migrated.setdefault("smart_home", {})
        migrated["smart_home"].setdefault("kasa", {})
        migrated["smart_home"]["kasa"]["devices"] = old_kasa
        print("[SETTINGS] Migrated old kasa_devices to smart_home.kasa.devices")
    return migrated


def load_settings() -> None:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            loaded = _migrate_settings_v1_to_v2(loaded)
            defaults_copy = deepcopy(DEFAULT_SETTINGS)
            if isinstance(loaded, dict):
                new_settings = _deep_merge_dict(defaults_copy, loaded)
            else:
                new_settings = defaults_copy

            briefing = new_settings.get("daily_briefing") or {}
            profile = briefing.get("profile") if isinstance(briefing, dict) else None
            if isinstance(profile, dict):
                new_settings["daily_briefing"]["profile"] = normalize_profile(profile)

            SETTINGS.clear()
            SETTINGS.update(new_settings)
            print(f"Loaded settings: {SETTINGS}")
        except Exception as exc:
            print(f"Error loading settings: {exc}")
            SETTINGS.clear()
            SETTINGS.update(deepcopy(DEFAULT_SETTINGS))
    else:
        SETTINGS.clear()
        SETTINGS.update(deepcopy(DEFAULT_SETTINGS))


def save_settings() -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as handle:
            json.dump(SETTINGS, handle, indent=4)
        print("Settings saved.")
    except Exception as exc:
        print(f"Error saving settings: {exc}")
