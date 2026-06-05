import asyncio


def _new_autonomy_state() -> dict:
    return {
        "last_scan_ts": 0.0,
        "last_look_ts": 0.0,
        "last_move_ts": 0.0,
        "last_comment_ts": 0.0,
        "last_curiosity_ts": 0.0,
        "last_proposal_ts": 0.0,
    }


def register_minecraft_socket_handlers(
    sio,
    *,
    get_minecraft_bot_manager,
    get_audio_loop,
    get_minecraft_autonomy_task,
    set_minecraft_autonomy_task,
    set_minecraft_autonomy_state,
    minecraft_autonomy_loop,
    minecraft_autonomy_cfg,
    set_minecraft_game_mode,
    settings,
    save_settings,
):
    @sio.event
    async def minecraft_connect(sid, data=None):
        """Frontend requests to start the Minecraft bot."""
        _ = data
        minecraft_bot_manager = get_minecraft_bot_manager()
        if not minecraft_bot_manager:
            await sio.emit("error", {"msg": "Minecraft bot manager not initialized"}, room=sid)
            return

        try:
            print("[SERVER] [Minecraft] Starting bot connection...")
            success = await minecraft_bot_manager.start()
            if not success:
                await sio.emit("error", {"msg": "Failed to start bot"}, room=sid)
                return

            status = minecraft_bot_manager.get_status()
            position = {"x": 0, "y": 0, "z": 0}
            if status.position and isinstance(status.position, dict):
                position = {
                    "x": status.position.get("x", 0),
                    "y": status.position.get("y", 0),
                    "z": status.position.get("z", 0),
                }

            await sio.emit(
                "minecraft_status",
                {
                    "connected": True,
                    "health": status.health,
                    "hunger": status.hunger,
                    "position": position,
                    "dimension": status.dimension,
                },
                room=sid,
            )
            print("[SERVER] [Minecraft] Bot connected successfully.")

            task = get_minecraft_autonomy_task()
            if task and not task.done():
                task.cancel()
            set_minecraft_autonomy_state(_new_autonomy_state())
            set_minecraft_autonomy_task(asyncio.create_task(minecraft_autonomy_loop()))

            cfg = minecraft_autonomy_cfg()
            await sio.emit(
                "minecraft_autonomy_status",
                {
                    "enabled": bool(cfg.get("enabled", True)),
                    "config": cfg,
                },
                room=sid,
            )

            if cfg.get("auto_game_mode_on_connect", True):
                await set_minecraft_game_mode(True)

            audio_loop = get_audio_loop()
            if audio_loop and audio_loop.session:
                try:
                    await audio_loop.session.send(
                        input="System Notification: [Minecraft] The bot is now connected to the server. You can use minecraft_* tools to interact.",
                        end_of_turn=False,
                    )
                except Exception:
                    pass
        except Exception as e:
            print(f"[SERVER] [Minecraft] Connection failed: {e}")
            await sio.emit("error", {"msg": f"Minecraft connection failed: {e}"}, room=sid)

    @sio.event
    async def minecraft_disconnect(sid, data=None):
        """Frontend requests to stop the Minecraft bot."""
        _ = data
        minecraft_bot_manager = get_minecraft_bot_manager()
        if not minecraft_bot_manager:
            await sio.emit("error", {"msg": "Minecraft bot manager not initialized"}, room=sid)
            return

        try:
            print("[SERVER] [Minecraft] Stopping bot...")
            await minecraft_bot_manager.stop()
            await sio.emit("minecraft_status", {"connected": False}, room=sid)
            print("[SERVER] [Minecraft] Bot disconnected.")

            task = get_minecraft_autonomy_task()
            if task and not task.done():
                task.cancel()
                set_minecraft_autonomy_task(None)

            await set_minecraft_game_mode(False)

            audio_loop = get_audio_loop()
            if audio_loop and audio_loop.session:
                try:
                    await audio_loop.session.send(
                        input="System Notification: [Minecraft] The bot has disconnected from the server.",
                        end_of_turn=False,
                    )
                except Exception:
                    pass
        except Exception as e:
            print(f"[SERVER] [Minecraft] Disconnection error: {e}")
            await sio.emit("error", {"msg": f"Minecraft disconnection error: {e}"}, room=sid)

    @sio.event
    async def minecraft_action(sid, data):
        """Frontend sends a minecraft action to execute."""
        minecraft_bot_manager = get_minecraft_bot_manager()
        if not minecraft_bot_manager:
            await sio.emit("error", {"msg": "Minecraft bot manager not initialized"}, room=sid)
            return

        action_name = (data or {}).get("action")
        params = (data or {}).get("params") or {}

        if not action_name:
            await sio.emit("error", {"msg": "Missing action name"}, room=sid)
            return

        try:
            print(f"[SERVER] [Minecraft] Executing action: {action_name} with params {params}")
            result = await minecraft_bot_manager.send_action(action_name, params)
            success = bool(result.get("success")) if isinstance(result, dict) else bool(result)
            await sio.emit(
                "minecraft_action_result",
                {
                    "action": action_name,
                    "success": success,
                    "result": result.get("message")
                    if isinstance(result, dict)
                    else ("Action sent to bot" if success else None),
                    "data": result.get("data") if isinstance(result, dict) else None,
                    "error": result.get("error")
                    if isinstance(result, dict)
                    else (None if success else "Failed to send action to bot subprocess"),
                },
                room=sid,
            )
        except Exception as e:
            print(f"[SERVER] [Minecraft] Action failed: {e}")
            await sio.emit(
                "minecraft_action_result",
                {
                    "action": action_name,
                    "success": False,
                    "error": str(e),
                },
                room=sid,
            )

    @sio.event
    async def minecraft_query_status(sid, data=None):
        """Frontend requests current bot status."""
        _ = data
        minecraft_bot_manager = get_minecraft_bot_manager()
        if not minecraft_bot_manager:
            await sio.emit("error", {"msg": "Minecraft bot manager not initialized"}, room=sid)
            return

        try:
            status = minecraft_bot_manager.get_status()
            perception = minecraft_bot_manager.get_perception_snapshot()

            position = {"x": 0, "y": 0, "z": 0}
            if status.position and isinstance(status.position, dict):
                position = {
                    "x": status.position.get("x", 0),
                    "y": status.position.get("y", 0),
                    "z": status.position.get("z", 0),
                }

            await sio.emit(
                "minecraft_status",
                {
                    "connected": status.is_connected,
                    "health": status.health,
                    "hunger": status.hunger,
                    "position": position,
                    "dimension": status.dimension,
                    "inventory": status.inventory,
                    "perception": perception,
                    "autonomy": minecraft_autonomy_cfg(),
                },
                room=sid,
            )
        except Exception as e:
            print(f"[SERVER] [Minecraft] Status query failed: {e}")
            await sio.emit("error", {"msg": f"Minecraft status query failed: {e}"}, room=sid)

    @sio.event
    async def minecraft_set_autonomy(sid, data=None):
        """Enable/disable lightweight autonomous wandering + commentary for Minecraft."""
        incoming = data if isinstance(data, dict) else {}
        settings.setdefault("minecraft_autonomy", {})
        settings["minecraft_autonomy"].update(incoming)
        save_settings()

        cfg = minecraft_autonomy_cfg()
        await sio.emit(
            "minecraft_autonomy_status",
            {
                "enabled": bool(cfg.get("enabled", True)),
                "config": cfg,
            },
            room=sid,
        )

    @sio.event
    async def minecraft_connect_to_server(sid, data=None, callback=None):
        """Frontend sends a request to connect to a different Minecraft server."""
        minecraft_bot_manager = get_minecraft_bot_manager()
        if not minecraft_bot_manager:
            result = {"success": False, "message": "Minecraft bot manager not initialized"}
            if callback:
                callback(result)
            return

        host = (data or {}).get("host")
        port = (data or {}).get("port", 25565)

        if not host:
            result = {"success": False, "message": "Missing host parameter"}
            if callback:
                callback(result)
            return

        try:
            print(f"[SERVER] [Minecraft] Connecting to {host}:{port}...")

            await minecraft_bot_manager.stop()
            await asyncio.sleep(0.5)

            minecraft_bot_manager.host = host
            minecraft_bot_manager.port = port

            success = await minecraft_bot_manager.start()

            if success:
                result = {"success": True, "message": f"Connected to {host}:{port}"}
                print(f"[SERVER] [Minecraft] Successfully connected to {host}:{port}")

                audio_loop = get_audio_loop()
                if audio_loop and audio_loop.session:
                    try:
                        await audio_loop.session.send(
                            input=f"System Notification: [Minecraft] Connected to server {host}:{port}. You can now play!",
                            end_of_turn=False,
                        )
                    except Exception:
                        pass
            else:
                result = {
                    "success": False,
                    "message": f"Failed to connect to {host}:{port}. Check server is running and version matches.",
                }
                print(f"[SERVER] [Minecraft] Failed to connect to {host}:{port}")

            if callback:
                callback(result)

        except Exception as e:
            result = {"success": False, "message": f"Connection error: {str(e)}"}
            print(f"[SERVER] [Minecraft] Connection to {host}:{port} failed: {e}")
            if callback:
                callback(result)
