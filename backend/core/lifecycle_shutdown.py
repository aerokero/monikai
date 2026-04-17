import asyncio
import os


def stop_runtime_components(audio_loop, loop_task, authenticator):
    if audio_loop:
        try:
            print("[SERVER] Stopping Audio Loop...")
            audio_loop.stop()
        except Exception as exc:
            print(f"[SERVER] Failed to stop audio loop: {exc}")
        finally:
            audio_loop = None

    if loop_task and not loop_task.done():
        try:
            print("[SERVER] Cancelling loop task...")
            loop_task.cancel()
        except Exception as exc:
            print(f"[SERVER] Failed to cancel loop task: {exc}")
        finally:
            loop_task = None

    if authenticator:
        try:
            print("[SERVER] Stopping Authenticator...")
            authenticator.stop()
        except Exception as exc:
            print(f"[SERVER] Failed to stop authenticator: {exc}")

    return audio_loop, loop_task


async def shutdown_and_exit(reason: str, *, stop_components_cb, delay_seconds: float = 0.15):
    print(reason)
    stop_components_cb()
    print("[SERVER] Graceful shutdown complete. Terminating process...")
    await asyncio.sleep(delay_seconds)
    os._exit(0)


def request_shutdown_from_signal(sig, *, main_loop, shutdown_coro_factory, stop_components_cb):
    reason = f"[SERVER] Caught signal {sig}. Exiting gracefully..."
    print(f"\n{reason}")
    if main_loop and main_loop.is_running():
        asyncio.run_coroutine_threadsafe(shutdown_coro_factory(reason), main_loop)
    else:
        stop_components_cb()
        print("[SERVER] Graceful shutdown complete. Terminating process...")
        os._exit(0)


async def stop_minecraft_runtime(minecraft_bot_manager, minecraft_autonomy_task):
    if minecraft_autonomy_task and not minecraft_autonomy_task.done():
        minecraft_autonomy_task.cancel()
        minecraft_autonomy_task = None

    if minecraft_bot_manager:
        try:
            await minecraft_bot_manager.stop()
        except Exception as e:
            print(f"[SERVER] Minecraft bot stop failed: {e}")

    return minecraft_bot_manager, minecraft_autonomy_task
