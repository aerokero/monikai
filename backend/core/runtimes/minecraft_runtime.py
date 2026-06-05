"""Minecraft bootstrap helpers for MonikAI backend startup."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from dotenv import dotenv_values


def discover_minecraft_env_path(server_file: Path) -> Optional[Path]:
    project_root = server_file.parents[2]
    env_candidates = [
        project_root / ".env",
        project_root / "backend" / "integrations" / "games" / ".env",
        project_root / "backend" / "minecraft-bot" / ".env",
        server_file.parent / "minecraft-bot" / ".env",
    ]
    return next((path for path in env_candidates if path.exists()), None)


def load_minecraft_bot_config(server_file: Path) -> Dict[str, str]:
    env_path = discover_minecraft_env_path(server_file)
    if env_path is None:
        print("[SERVER] Minecraft .env not found, using default MC_* settings.")
        return {}

    config = dotenv_values(env_path)
    print(f"[SERVER] Minecraft config loaded from: {env_path}")
    return dict(config)