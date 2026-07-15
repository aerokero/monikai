import asyncio
import traceback


def _new_autonomy_state() -> dict:
    return {
        "last_scan_ts": 0.0,
        "last_look_ts": 0.0,
        "last_move_ts": 0.0,
        "last_comment_ts": 0.0,
        "last_curiosity_ts": 0.0,
        "last_proposal_ts": 0.0,
    }


def register_minecraft_perception_callback(
    minecraft_bot_manager,
    *,
    get_audio_loop,
    schedule_emit_to_frontend,
    minecraft_autonomy_cfg,
    set_minecraft_game_mode,
    minecraft_autonomy_loop,
    get_minecraft_autonomy_task,
    set_minecraft_autonomy_task,
    set_minecraft_autonomy_state,
) -> bool:
    async def on_minecraft_perception(event):
        # Keep logs readable by suppressing successful high-frequency action_result events.
        should_log_event = event.event_type in {"ready", "disconnected", "error", "chat"}
        if event.event_type == "action_result":
            result = event.data or {}
            if not bool(result.get("success", False)):
                should_log_event = True
                print(
                    f"[PERCEPTION] Action failed: action={result.get('action', 'unknown')} "
                    f"message={result.get('message', 'No message')}"
                )
        elif event.event_type not in {"status_update", "environment_update"}:
            should_log_event = True

        audio_loop = get_audio_loop()

        if should_log_event:
            print(
                f"[PERCEPTION] Received event: type={event.event_type}, "
                f"has_session={'Yes' if (audio_loop and audio_loop.session) else 'No'}"
            )

        schedule_emit_to_frontend(
            "minecraft_perception",
            {
                "event_type": event.event_type,
                "data": event.data,
                "timestamp": event.timestamp,
            },
        )

        if not audio_loop or not audio_loop.session:
            print(
                "[PERCEPTION] Skipping: "
                f"audio_loop={audio_loop is not None}, "
                f"session_exists={audio_loop.session is not None if audio_loop else 'N/A'}"
            )
            return

        try:
            if event.event_type == "chat":
                data = event.data or {}
                username = data.get("username", "Unknown")
                message = data.get("message", "")
                if message:
                    msg = f"[Minecraft Chat] {username}: {message}"
                    print(f"[PERCEPTION] Sending to Monika: {msg}")
                    await audio_loop.session.send(input=msg, end_of_turn=False)
                    # v3: shared play becomes memory — in-game chat lands in the
                    # minecraft stream, digested into a daily recap (Phase G).
                    try:
                        sm = getattr(audio_loop, "session_manager", None)
                        if sm:
                            sm.log_stream("minecraft", f"MC:{username}", message)
                    except Exception:
                        pass

            elif event.event_type == "action_result":
                data = event.data or {}
                action = data.get("action", "unknown")
                success = data.get("success", False)
                result_msg = data.get("message", "No message")

                if action and not success:
                    msg = f"[Minecraft] Action '{action}' failed: {result_msg}"
                    print(f"[PERCEPTION] Sending to Monika: {msg}")
                    await audio_loop.session.send(input=msg, end_of_turn=False)

            elif event.event_type == "error":
                data = event.data or {}
                error_msg = data.get("message", "Unknown error")
                msg = f"[Minecraft] Error: {error_msg}"
                print(f"[PERCEPTION] Sending to Monika: {msg}")
                await audio_loop.session.send(input=msg, end_of_turn=False)

            elif event.event_type == "ready":
                data = event.data or {}
                bot_name = data.get("username") or "strawberryglass"
                msg = (
                    f"[Minecraft] You are now connected as player '{bot_name}'. "
                    "When user says 'come to me', ask for their nickname if missing, then use that target."
                )
                # v3: her own in-world goals give her life continuity between play sessions.
                try:
                    from backend.core.runtimes.v2_runtime import get as _v2_get
                    from backend.progression.minecraft_goals import format_open_goals
                    _v2rt = _v2_get()
                    goals_line = await format_open_goals(_v2rt._db_path if _v2rt else None)
                    if goals_line:
                        msg += f" {goals_line} Use the minecraft_goals tool to manage them."
                except Exception:
                    pass
                print(f"[PERCEPTION] Sending to Monika: {msg}")
                await audio_loop.session.send(input=msg, end_of_turn=False)
                try:
                    sm = getattr(audio_loop, "session_manager", None)
                    if sm:
                        sm.log_stream("minecraft", "MC:system", f"Monika dołączyła do gry Minecraft jako '{bot_name}'.")
                except Exception:
                    pass

                cfg = minecraft_autonomy_cfg()
                if cfg.get("auto_game_mode_on_connect", True):
                    await set_minecraft_game_mode(True)

                task = get_minecraft_autonomy_task()
                if not task or task.done():
                    set_minecraft_autonomy_state(_new_autonomy_state())
                    set_minecraft_autonomy_task(asyncio.create_task(minecraft_autonomy_loop()))

            elif event.event_type == "disconnected":
                data = event.data or {}
                reason = data.get("reason") or "Connection ended"
                msg = f"[Minecraft] Bot disconnected. Reason: {reason}"
                print(f"[PERCEPTION] Sending to Monika: {msg}")
                await audio_loop.session.send(input=msg, end_of_turn=False)

                await set_minecraft_game_mode(False)

                task = get_minecraft_autonomy_task()
                if task and not task.done():
                    task.cancel()
                    set_minecraft_autonomy_task(None)

        except Exception as e:
            print(f"[PERCEPTION] Failed to send minecraft event to Monika: {e}")
            traceback.print_exc()

    try:
        minecraft_bot_manager.register_perception_callback(on_minecraft_perception)
        return True
    except Exception as e:
        print(f"[SERVER] Minecraft Bot callback registration failed: {e}")
        return False
