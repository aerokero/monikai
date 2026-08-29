import json
from datetime import datetime

from backend.core import model_config as _mc


def register_settings_profile_handlers(
    sio,
    *,
    get_settings_fn,
    save_settings,
    get_audio_loop,
    get_personality_system,
    get_calendar_manager,
    get_authenticator,
    emit_to_frontend,
    data_dir,
    daily_briefing_runtime,
):
    @sio.on("get_settings")
    async def get_settings(sid):
        await sio.emit("settings", get_settings_fn(), room=sid)

    @sio.event
    async def update_settings(sid, data):
        settings = get_settings_fn()
        audio_loop = get_audio_loop()
        authenticator = get_authenticator()

        print(f"Updating settings: {data}")

        if "tool_permissions" in data:
            settings["tool_permissions"].update(data["tool_permissions"])
            if audio_loop:
                audio_loop.update_permissions(settings["tool_permissions"])

        if "show_internal_thoughts" in data:
            settings["show_internal_thoughts"] = bool(data["show_internal_thoughts"])

        if "camera_flipped" in data:
            settings["camera_flipped"] = data["camera_flipped"]
            print(f"[SERVER] Camera flip set to: {data['camera_flipped']}")

        if "camera_source" in data:
            settings["camera_source"] = data["camera_source"]
            if audio_loop and hasattr(audio_loop, "reload_capture_settings"):
                try:
                    audio_loop.reload_capture_settings()
                except Exception:
                    pass

        if "video_mode" in data:
            settings["video_mode"] = data["video_mode"]
            mode = str(settings["video_mode"]).lower()
            if mode == "screen":
                settings.setdefault("screen_capture", {})["stream_to_ai"] = True
            else:
                settings.setdefault("screen_capture", {})["stream_to_ai"] = False
            if audio_loop and hasattr(audio_loop, "set_video_mode"):
                try:
                    audio_loop.set_video_mode(settings["video_mode"])
                except Exception:
                    pass
            if audio_loop and getattr(audio_loop, "session", None):
                try:
                    if mode in ("screen", "camera"):
                        scope = "ekran" if mode == "screen" else "kamerę"
                        msg = (
                            f"System Notification: Włączono tryb obrazu ({mode}). "
                            f"Masz dostęp do opisu obrazu z {scope} użytkownika (na podstawie zrzutów)."
                        )
                    else:
                        msg = "System Notification: Tryb obrazu został wyłączony."
                    if hasattr(audio_loop, "send_system_message"):
                        await audio_loop.send_system_message(msg, end_of_turn=False)
                    else:
                        await audio_loop.session.send(input=msg, end_of_turn=False)
                except Exception:
                    pass

        if "camera_capture" in data and isinstance(data.get("camera_capture"), dict):
            settings.setdefault("camera_capture", {}).update(data["camera_capture"])
            if audio_loop and hasattr(audio_loop, "reload_capture_settings"):
                try:
                    audio_loop.reload_capture_settings()
                except Exception:
                    pass

        if "screen_capture" in data and isinstance(data.get("screen_capture"), dict):
            settings.setdefault("screen_capture", {}).update(data["screen_capture"])
            if audio_loop and hasattr(audio_loop, "reload_capture_settings"):
                try:
                    audio_loop.reload_capture_settings()
                except Exception:
                    pass

        if "daily_briefing" in data and isinstance(data.get("daily_briefing"), dict):
            if daily_briefing_runtime:
                incoming = data["daily_briefing"]
                settings.setdefault("daily_briefing", {})
                for k, v in incoming.items():
                    if k == "profile" and isinstance(v, dict):
                        daily_briefing_runtime.set_profile(v)
                    else:
                        settings["daily_briefing"][k] = v
                daily_briefing_runtime.invalidate_cache()

        _model_changed = False
        if "gemini_model_preset" in data or "gemini_voice" in data:
            new_preset = data.get("gemini_model_preset") or settings.get("gemini_model_preset")
            new_voice  = data.get("gemini_voice")  or settings.get("gemini_voice")
            if "gemini_model_preset" in data:
                settings["gemini_model_preset"] = new_preset
            if "gemini_voice" in data:
                settings["gemini_voice"] = new_voice
            _model_changed = _mc.apply_runtime_settings(
                preset=new_preset if "gemini_model_preset" in data else None,
                voice=new_voice  if "gemini_voice"         in data else None,
            )

        save_settings()
        await emit_to_frontend("settings", settings)

        if _model_changed and audio_loop:
            try:
                audio_loop.request_reconnect("model_settings_changed")
            except Exception:
                pass

    @sio.event
    async def get_tool_permissions(sid):
        settings = get_settings_fn()
        await sio.emit("tool_permissions", settings["tool_permissions"], room=sid)

    @sio.event
    async def update_tool_permissions(sid, data):
        settings = get_settings_fn()
        audio_loop = get_audio_loop()
        print(f"Updating permissions (legacy event): {data}")
        settings["tool_permissions"].update(data)
        save_settings()

        if audio_loop:
            audio_loop.update_permissions(settings["tool_permissions"])
        await emit_to_frontend("tool_permissions", settings["tool_permissions"])

    @sio.event
    async def report_visual_state(sid, data):
        personality_system = get_personality_system()
        audio_loop = get_audio_loop()
        if personality_system:
            loc = data.get("location")
            outfit = data.get("outfit")

            if loc == "outside":
                outfit = "School Uniform"

            changed = False
            if loc and loc != personality_system.state.current_location:
                personality_system.state.current_location = loc
                changed = True
            if outfit and outfit != personality_system.state.current_outfit:
                personality_system.state.current_outfit = outfit
                changed = True

            if changed and audio_loop and getattr(audio_loop, "session", None):
                update_msg = (
                    "System Notification: [Visual State Update] "
                    f"Monika Location: {personality_system.state.current_location}, "
                    f"Monika Outfit: {personality_system.state.current_outfit}."
                )
                print(f"[SERVER] Sending visual update to model: {update_msg}")
                if hasattr(audio_loop, "send_system_message"):
                    await audio_loop.send_system_message(update_msg, end_of_turn=False)
                else:
                    await audio_loop.session.send(input=update_msg, end_of_turn=False)

    @sio.event
    async def calendar_get_events(sid, data=None):
        _ = data
        calendar_manager = get_calendar_manager()
        try:
            if not calendar_manager:
                result = {"events": [], "error": "Calendar not available"}
                await sio.emit("error", {"msg": "Calendar not available"}, room=sid)
                return result

            events = calendar_manager.get_all_events()
            events_list = [
                {
                    "id": e.id,
                    "summary": e.summary,
                    "start_iso": e.start_iso,
                    "end_iso": e.end_iso,
                    "description": e.description or "",
                    "all_day": bool(getattr(e, "all_day", False)),
                    "is_birthday": getattr(e, "is_birthday", False),
                }
                for e in events
            ]
            events_list.sort(key=lambda x: x["start_iso"])

            print(f"[SERVER] Sending {len(events_list)} calendar events to frontend")

            result = {"events": events_list}
            await sio.emit("calendar_events", result, room=sid)
            return result
        except Exception as e:
            print(f"[SERVER] Error in calendar_get_events: {e}")
            result = {"events": [], "error": str(e)}
            await sio.emit("error", {"msg": f"Failed to get calendar events: {e}"}, room=sid)
            return result

    @sio.event
    async def calendar_get_birthdays(sid, data=None):
        _ = data
        try:
            birthdays = []

            profile_path = data_dir / "long_term_memory" / "profile.md"
            if profile_path.exists():
                import re
                content = profile_path.read_text(encoding="utf-8", errors="ignore")
                birth_match = re.search(r'(?:Birthday|Birthdate|DOB)[:\s]+(\d{4}-\d{2}-\d{2}|[A-Za-z]+ \d{1,2},? \d{4})', content)
                if birth_match:
                    birthdays.append({
                        "date": birth_match.group(1),
                        "label": "Your Birthday",
                    })

            profile_json_path = data_dir / "long_term_memory" / "profile_meta.json"
            if profile_json_path.exists():
                try:
                    profile_data = json.loads(profile_json_path.read_text())
                    if profile_data.get("birthday"):
                        birthdays.append({
                            "date": profile_data["birthday"],
                            "label": "Your Birthday",
                        })
                except Exception:
                    pass

            print(f"[SERVER] Sending {len(birthdays)} birthdays to frontend")

            result = {"birthdays": birthdays}
            await sio.emit("calendar_birthdays", result, room=sid)
            return result
        except Exception as e:
            print(f"[SERVER] Error in calendar_get_birthdays: {e}")
            result = {"birthdays": [], "error": str(e)}
            await sio.emit("error", {"msg": f"Failed to get birthdays: {e}"}, room=sid)
            return result

    @sio.event
    async def memory_get_profile(sid, data=None):
        _ = data
        try:
            profile = {
                "user_name": "",
                "gender": "",
                "birthday": "",
                "location": "",
                "occupation": "",
                "interests": "",
                "personality_traits": "",
            }

            profile_meta_path = data_dir / "long_term_memory" / "profile_meta.json"
            if profile_meta_path.exists():
                try:
                    profile_data = json.loads(profile_meta_path.read_text())
                    profile.update({
                        "user_name": profile_data.get("user_name", ""),
                        "gender": profile_data.get("gender", ""),
                        "birthday": profile_data.get("birthday", ""),
                        "location": profile_data.get("location", ""),
                        "occupation": profile_data.get("occupation", ""),
                        "interests": profile_data.get("interests", ""),
                        "personality_traits": profile_data.get("personality_traits", ""),
                    })
                except Exception:
                    pass

            print("[SERVER] Sending user profile to frontend")

            result = {"profile": profile}
            await sio.emit("memory_profile", result, room=sid)
            return result
        except Exception as e:
            print(f"[SERVER] Error in memory_get_profile: {e}")
            result = {"profile": {}, "error": str(e)}
            await sio.emit("error", {"msg": f"Failed to get profile: {e}"}, room=sid)
            return result

    @sio.event
    async def memory_update_profile(sid, data):
        try:
            profile = data.get("profile", {}) if isinstance(data, dict) else {}

            if not profile:
                result = {"success": False, "error": "No profile data provided"}
                await sio.emit("error", {"msg": "No profile data provided"}, room=sid)
                return result

            profile_meta_path = data_dir / "long_term_memory" / "profile_meta.json"
            profile_meta_path.parent.mkdir(parents=True, exist_ok=True)

            profile_data = {
                "user_name": profile.get("user_name", "").strip(),
                "gender": profile.get("gender", "").strip(),
                "birthday": profile.get("birthday", "").strip(),
                "location": profile.get("location", "").strip(),
                "occupation": profile.get("occupation", "").strip(),
                "interests": profile.get("interests", "").strip(),
                "personality_traits": profile.get("personality_traits", "").strip(),
                "updated_at": datetime.now().isoformat(),
            }

            profile_meta_path.write_text(json.dumps(profile_data, indent=2, ensure_ascii=False), encoding="utf-8")

            profile_md_path = data_dir / "long_term_memory" / "profile.md"
            profile_md_path.parent.mkdir(parents=True, exist_ok=True)

            md_content = f"""# User Profile

**Name:** {profile_data['user_name']}

**Gender:** {profile_data['gender']} 

**Birthday:** {profile_data['birthday']}

**Location:** {profile_data['location']}

**Occupation:** {profile_data['occupation']}

**Interests:** {profile_data['interests']}

**Personality Traits:** {profile_data['personality_traits']}

*Last updated: {profile_data['updated_at']}*
"""
            profile_md_path.write_text(md_content, encoding="utf-8")

            print(f"[SERVER] User profile updated: {profile_data['user_name']}")

            audio_loop = get_audio_loop()
            if audio_loop and audio_loop.session:
                try:
                    msg = (
                        "System Notification: User profile was updated: "
                        f"Name={profile_data['user_name']}, Gender={profile_data['gender']}, "
                        f"Birthday={profile_data['birthday']}, Location={profile_data['location']}, "
                        f"Occupation={profile_data['occupation']}."
                    )
                    if hasattr(audio_loop, "send_system_message"):
                        await audio_loop.send_system_message(msg, end_of_turn=False)
                    else:
                        await audio_loop.session.send(input=msg, end_of_turn=False)
                except Exception as e:
                    print(f"[SERVER] Failed to notify model about profile update: {e}")

            result = {"success": True, "profile": profile_data}
            await sio.emit("memory_profile", result, room=sid)
            await sio.emit("status", {"msg": "Profile saved successfully"}, room=sid)
            return result
        except Exception as e:
            print(f"[SERVER] Error in memory_update_profile: {e}")
            result = {"success": False, "error": str(e)}
            await sio.emit("error", {"msg": f"Failed to update profile: {e}"}, room=sid)
            return result

    @sio.on("get_models")
    async def handle_get_models(sid, data=None):
        _ = data
        from backend.models.model_router import get_model_router
        router = get_model_router()
        health_info = await router.health_all()
        await sio.emit("models_status", health_info, room=sid)

    @sio.on("select_model")
    async def handle_select_model(sid, data):
        from backend.models.model_router import get_model_router
        router = get_model_router()
        task = (data or {}).get("task", "default")
        provider = (data or {}).get("provider")
        if not provider:
            await sio.emit("error", {"msg": "Missing provider in select_model"}, room=sid)
            return
        if task == "default":
            ok = router.set_default_provider(provider)
        else:
            ok = router.set_task_provider(task, provider)
        if ok:
            health_info = await router.health_all()
            await sio.emit("models_status", health_info, room=sid)
            await sio.emit("status", {"msg": f"Model provider for {task} set to {provider}"}, room=sid)
        else:
            await sio.emit("error", {"msg": f"Failed to set provider {provider}"}, room=sid)
