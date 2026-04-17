import asyncio

from ..agents.telegram_bot import TelegramBotService


def start_telegram_service(
    settings_getter,
    *,
    calendar_manager,
    reminder_manager,
    spotify_manager,
    personality,
):
    telegram_service = TelegramBotService.from_env(
        settings_getter,
        calendar_manager=calendar_manager,
        reminder_manager=reminder_manager,
        spotify_manager=spotify_manager,
        personality=personality,
    )
    telegram_task = None
    if telegram_service:
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
