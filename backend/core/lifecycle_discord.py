import asyncio
import os
import logging
from typing import Optional

from ..vn.discord_adapter import DiscordChannelAdapter

logger = logging.getLogger(__name__)


def start_discord_service(
    settings_getter,
    *,
    calendar_manager,
    reminder_manager,
    spotify_manager,
    personality,
    home_assistant_agent=None,
    hue_agent=None,
):
    channel_config = None
    channel_profile = None
    try:
        from src.channel_config import get_channel_integration, get_channel_profile
        channel_config = get_channel_integration("discord")
        channel_profile = get_channel_profile(channel_config.get("profile_id") or "discord")
    except Exception as exc:
        logger.warning("[SERVER] Typed Discord config unavailable; using environment: %s", exc)

    channel_config = channel_config or {}
    token = str(channel_config.get("token") or os.getenv("DISCORD_BOT_TOKEN", "")).strip()
    if channel_config and channel_config.get("enabled") is False:
        token = ""
    if not token:
        logger.info("[SERVER] Discord bot token not set; skipping Discord bot startup.")
        return None, None

    # The typed config already includes environment fallbacks when no saved
    # channel record exists. Keep parsing here as a final compatibility guard
    # for callers that inject only a token.
    allowed_ids = channel_config.get("allowed_channel_ids") or []
    allowed_guild_ids = channel_config.get("allowed_guild_ids") or []
    allowed_user_ids = channel_config.get("allowed_user_ids") or []

    try:
        discord_service = DiscordChannelAdapter(
            token=token,
            settings_getter=settings_getter,
            calendar_manager=calendar_manager,
            reminder_manager=reminder_manager,
            spotify_manager=spotify_manager,
            personality=personality,
            allowed_channel_ids=allowed_ids,
            allowed_guild_ids=allowed_guild_ids,
            allowed_user_ids=allowed_user_ids,
            allow_dms=channel_config.get("allow_dms", True),
            require_mention=channel_config.get("require_mention", True),
            home_assistant_agent=home_assistant_agent,
            hue_agent=hue_agent,
            channel_profile=channel_profile,
        )
        discord_task = asyncio.create_task(discord_service.start_bot())
        print("[SERVER] Discord bot service started.")
        return discord_service, discord_task
    except Exception as exc:
        print(f"[SERVER] Failed to start Discord bot: {exc}")
        return None, None


async def stop_discord_service(discord_service: Optional[DiscordChannelAdapter], discord_task: Optional[asyncio.Task]):
    if discord_service:
        try:
            await discord_service.stop_bot()
        except Exception as e:
            print(f"[SERVER] Discord bot stop failed: {e}")

    if discord_task and not discord_task.done():
        discord_task.cancel()
        try:
            await discord_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    return None, None
