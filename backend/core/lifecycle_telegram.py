import asyncio

from ..agents.telegram_bot import TelegramBotService


def start_telegram_service(
    settings_getter,
    *,
    calendar_manager,
    reminder_manager,
    spotify_manager,
    personality,
    server_mic_listener=None,
    kasa_agent=None,
    hue_agent=None,
    home_assistant_agent=None,
):
    channel_config = None
    channel_profile = None
    try:
        from src.channel_config import get_channel_integration, get_channel_profile
        channel_config = get_channel_integration("telegram")
        channel_profile = get_channel_profile(channel_config.get("profile_id") or "telegram")
    except Exception as exc:
        print(f"[SERVER] Typed Telegram config unavailable; using environment: {exc}")

    telegram_service = TelegramBotService.from_env(
        settings_getter,
        calendar_manager=calendar_manager,
        reminder_manager=reminder_manager,
        spotify_manager=spotify_manager,
        personality=personality,
        server_mic_listener=server_mic_listener,
        kasa_agent=kasa_agent,
        hue_agent=hue_agent,
        home_assistant_agent=home_assistant_agent,
        channel_config=channel_config,
        channel_profile=channel_profile,
    )
    telegram_task = None
    if telegram_service:
        if reminder_manager:
            orig_reminder_cb = getattr(reminder_manager, "on_reminder", None)
            def _on_reminder_hook(rem):
                telegram_service.notify_reminder_fired(rem)
                if orig_reminder_cb:
                    return orig_reminder_cb(rem)
            reminder_manager.on_reminder = _on_reminder_hook

        telegram_task = asyncio.create_task(telegram_service.run())
        print("[SERVER] Telegram bot service started.")
    return telegram_service, telegram_task


async def stop_telegram_service(telegram_service, telegram_task):
    if telegram_service:
        try:
            await telegram_service.stop()
        except Exception as e:
            print(f"[SERVER] Telegram bot stop failed: {e}")

    if telegram_task and not telegram_task.done():
        telegram_task.cancel()
        try:
            await telegram_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    return None, None
