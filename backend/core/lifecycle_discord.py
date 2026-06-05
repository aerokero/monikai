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
):
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        logger.info("[SERVER] Discord bot token not set; skipping Discord bot startup.")
        return None, None

    # Load allowed channel IDs from env
    raw_channel_ids = os.getenv("DISCORD_ALLOWED_CHANNEL_IDS", "").strip()
    allowed_ids = []
    if raw_channel_ids:
        for p in raw_channel_ids.split(","):
            val = p.strip()
            if val.isdigit():
                allowed_ids.append(int(val))

    try:
        discord_service = DiscordChannelAdapter(
            token=token,
            settings_getter=settings_getter,
            calendar_manager=calendar_manager,
            reminder_manager=reminder_manager,
            spotify_manager=spotify_manager,
            personality=personality,
            allowed_channel_ids=allowed_ids,
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
