from __future__ import annotations

import asyncio
from dataclasses import asdict


def register_system_frontend_handlers(
    sio,
    *,
    get_audio_loop,
    get_personality_system,
    get_kasa_agent,
    get_spotify_manager,
    get_settings,
    save_settings,
    shutdown_and_exit,
    mark_user_activity,
):
    def _serialize_kasa_devices():
        kasa_agent = get_kasa_agent()
        if not kasa_agent:
            return []
        return kasa_agent.serialize_devices()

    @sio.event
    async def get_personality_status(sid):
        try:
            from backend.core.runtimes import v2_runtime
            runtime = v2_runtime.get()
            if runtime is not None:
                await sio.emit("personality_status", await runtime.get_status_payload(), room=sid)
                return
        except Exception:
            pass

        if get_personality_system():
            data = asdict(get_personality_system().state)
            aff = max(0.0, min(100.0, float(data.get("affection", 0))))
            score = aff / 10.0
            full = int(score)
            hearts = "❤️" * full + "🤍" * (10 - full)
            data["affection_hearts"] = f"{hearts} ({score:.1f}/10)"
            await sio.emit("personality_status", data, room=sid)

    @sio.event
    async def video_frame(sid, data):
        image_data = data.get("image")
        audio_loop = get_audio_loop()
        if image_data and audio_loop:
            asyncio.create_task(audio_loop.send_frame(image_data))

    @sio.event
    async def user_activity(sid, data):
        try:
            text = (data or {}).get("text") or ""
            mark_user_activity(get_audio_loop(), text)
        except Exception:
            pass

    @sio.event
    async def discover_kasa(sid):
        print("Received discover_kasa request")
        kasa_agent = get_kasa_agent()
        try:
            if not kasa_agent:
                await sio.emit("error", {"msg": "Kasa agent unavailable"}, room=sid)
                return

            devices = await kasa_agent.discover_devices()
            await sio.emit("kasa_devices", devices, room=sid)
            await sio.emit("status", {"msg": f"Found {len(devices)} Kasa devices"}, room=sid)

            saved_devices = []
            for device in devices:
                saved_devices.append({
                    "ip": device["ip"],
                    "alias": device["alias"],
                    "model": device["model"],
                })

            settings = get_settings()
            if "smart_home" not in settings:
                settings["smart_home"] = {}
            if "kasa" not in settings["smart_home"]:
                settings["smart_home"]["kasa"] = {}
            settings["smart_home"]["kasa"]["devices"] = saved_devices
            save_settings()
            print(f"[SERVER] Saved {len(saved_devices)} Kasa devices to settings (smart_home.kasa.devices).")
        except Exception as e:
            print(f"Error discovering kasa: {e}")
            await sio.emit("error", {"msg": f"Kasa Discovery Failed: {str(e)}"}, room=sid)

    @sio.event
    async def list_kasa(sid, data=None):
        _ = data
        await sio.emit("kasa_devices", _serialize_kasa_devices(), room=sid)

    @sio.event
    async def spotify_get_status(sid, data=None):
        _ = data
        spotify_manager = get_spotify_manager()
        if not spotify_manager:
            await sio.emit("spotify_status", {"ok": False, "error": "spotify manager unavailable"}, room=sid)
            return
        try:
            await sio.emit("spotify_status", {"ok": True, "status": spotify_manager.status()}, room=sid)
        except Exception as e:
            await sio.emit("spotify_status", {"ok": False, "error": str(e)}, room=sid)

    @sio.event
    async def spotify_get_auth_url(sid, data=None):
        _ = data
        spotify_manager = get_spotify_manager()
        if not spotify_manager:
            await sio.emit("spotify_auth_url", {"ok": False, "error": "spotify manager unavailable"}, room=sid)
            return
        try:
            url = spotify_manager.build_auth_url()
            await sio.emit("spotify_auth_url", {"ok": True, "url": url}, room=sid)
        except Exception as e:
            await sio.emit("spotify_auth_url", {"ok": False, "error": str(e)}, room=sid)

    @sio.event
    async def spotify_refresh_token(sid, data=None):
        _ = data
        spotify_manager = get_spotify_manager()
        if not spotify_manager:
            await sio.emit("spotify_status", {"ok": False, "error": "spotify manager unavailable"}, room=sid)
            return
        try:
            st = spotify_manager.refresh_access_token()
            await sio.emit("spotify_status", {"ok": True, "status": st}, room=sid)
        except Exception as e:
            await sio.emit("spotify_status", {"ok": False, "error": str(e)}, room=sid)

    @sio.event
    async def control_kasa(sid, data):
        kasa_agent = get_kasa_agent()
        if not kasa_agent:
            await sio.emit("error", {"msg": "Kasa agent unavailable"}, room=sid)
            return

        ip = data.get("ip")
        action = data.get("action")
        print(f"Kasa Control: {ip} -> {action}")

        try:
            success = False
            if action == "on":
                success = await kasa_agent.turn_on(ip)
            elif action == "off":
                success = await kasa_agent.turn_off(ip)
            elif action == "brightness":
                success = await kasa_agent.set_brightness(ip, data.get("value"))
            elif action == "color":
                value = data.get("value", {})
                h = value.get("h", 0)
                s = value.get("s", 100)
                v = value.get("v", 100)
                success = await kasa_agent.set_color(ip, (h, s, v))

            if success:
                await sio.emit(
                    "kasa_update",
                    {
                        "ip": ip,
                        "is_on": True if action == "on" else (False if action == "off" else None),
                        "brightness": data.get("value") if action == "brightness" else None,
                    },
                    room=sid,
                )
            else:
                await sio.emit("error", {"msg": f"Failed to control device {ip}"}, room=sid)
        except Exception as e:
            print(f"Error controlling kasa: {e}")
            await sio.emit("error", {"msg": f"Kasa Control Error: {str(e)}"}, room=sid)

    @sio.event
    async def kill_server(sid, data=None):
        _ = data
        print("[SERVER] Kill server requested from frontend")
        asyncio.create_task(shutdown_and_exit("[SERVER] Kill server requested from frontend."))
        await asyncio.sleep(0.1)
