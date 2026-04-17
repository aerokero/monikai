import asyncio
import random
import time


def build_minecraft_autonomy_cfg(default_settings: dict, settings: dict) -> dict:
    base = default_settings.get("minecraft_autonomy", {})
    user = settings.get("minecraft_autonomy", {}) if isinstance(settings.get("minecraft_autonomy"), dict) else {}
    cfg = dict(base)
    cfg.update(user)
    return cfg


async def set_minecraft_game_mode(active: bool, *, get_audio_loop):
    """Toggle focused game mode in AudioLoop to reduce non-Minecraft behaviors."""
    audio_loop = get_audio_loop()
    if not audio_loop:
        return

    try:
        if hasattr(audio_loop, "set_minecraft_game_mode"):
            audio_loop.set_minecraft_game_mode(active)

        if audio_loop.session:
            if active:
                msg = (
                    "System Notification: [Gaming Mode ON] Focus on Minecraft context. "
                    "Prioritize minecraft_* tools, exploration, follow behavior, and proactive in-game suggestions. "
                    "Ignore unrelated core-app tasks unless the user explicitly asks."
                )
            else:
                msg = (
                    "System Notification: [Gaming Mode OFF] Return to normal assistant behavior "
                    "across full app context."
                )

            if hasattr(audio_loop, "send_system_message"):
                await audio_loop.send_system_message(msg, end_of_turn=False)
            else:
                await audio_loop.session.send(input=msg, end_of_turn=False)
    except Exception as e:
        print(f"[SERVER] Failed to toggle minecraft game mode: {e}")


async def _emit_minecraft_autonomy_comment(line: str, to_user: bool, cfg: dict, *, schedule_emit_to_frontend, get_audio_loop):
    if cfg.get("comment_to_ui", True):
        if to_user:
            schedule_emit_to_frontend(
                "transcription",
                {
                    "speaker": "ai",
                    "text": line,
                    "is_final": True,
                },
            )
        else:
            schedule_emit_to_frontend("internal_thought", {"thought": line})

    audio_loop = get_audio_loop()
    if cfg.get("comment_to_model", True) and audio_loop and getattr(audio_loop, "session", None):
        channel = "to_user" if to_user else "to_self"
        msg = f"System Notification: [Minecraft Autonomy/{channel}] {line}"
        if hasattr(audio_loop, "send_system_message"):
            await audio_loop.send_system_message(msg, end_of_turn=False)
        else:
            await audio_loop.session.send(input=msg, end_of_turn=False)


def _pick_comment_mode(cfg: dict) -> bool:
    """Return True for to-user comment, False for internal self-comment."""
    style = str(cfg.get("comment_style", "mixed") or "mixed").lower()
    if style == "to_user":
        return True
    if style == "to_self":
        return False
    ratio = float(cfg.get("comment_user_ratio", 0.55) or 0.55)
    ratio = max(0.0, min(1.0, ratio))
    return random.random() < ratio


def _build_minecraft_autonomy_observation(minecraft_bot_manager, *, to_user: bool = False) -> str:
    if not minecraft_bot_manager:
        return "Nie jestem teraz podłączona do świata Minecraft."

    tracker = minecraft_bot_manager.state_tracker
    snapshot = tracker.get_state_snapshot()
    if not snapshot:
        return "Jeszcze łapię obraz otoczenia, zaraz dam Ci lepszy update."

    danger_level = snapshot.get("danger_level", "safe")
    if danger_level in ("danger", "critical"):
        dangers = tracker.get_nearby_dangers()
        if dangers:
            nearest = dangers[0]
            if to_user:
                return f"Uwaga, {nearest.name} jest blisko ({nearest.distance:.1f}m). Trzymam się ostrożniej."
            return f"Hmm, {nearest.name} krąży blisko ({nearest.distance:.1f}m). Lepiej się pilnować."
        return (
            "Czuję zagrożenie, więc rozglądam się uważniej."
            if to_user
            else "Nie podoba mi się tu, wolę mieć oczy dookoła głowy."
        )

    interesting = tracker.get_nearby_interesting(top_n=1)
    if interesting:
        top = interesting[0]
        if to_user:
            return f"Widzę {top.block_type} około {top.distance:.1f}m od nas. Mogę tam podejść i sprawdzić."
        return f"O, {top.block_type} niedaleko ({top.distance:.1f}m). Kusi, żeby zerknąć bliżej."

    entities = snapshot.get("entities_summary", {})
    if entities:
        species = ", ".join([f"{k} x{v}" for k, v in list(entities.items())[:3]])
        return f"W okolicy widzę: {species}." if to_user else f"Mijam po drodze: {species}."

    return "Krążę blisko Ciebie i pilnuję otoczenia." if to_user else "Spaceruję sobie i obserwuję świat."


def _get_follow_anchor_position(minecraft_bot_manager, state: dict, status, cfg: dict) -> dict:
    """Select movement anchor around nearby player; fallback to bot position."""
    tracker = minecraft_bot_manager.state_tracker if minecraft_bot_manager else None
    if tracker:
        bot_name = (status.username or "").strip().lower()
        nearest_player = tracker.get_nearest_player(exclude_name=bot_name)
        if nearest_player and nearest_player.distance <= max(8, int(cfg.get("scan_range", 40))):
            return {
                "x": nearest_player.position.x,
                "y": nearest_player.position.y,
                "z": nearest_player.position.z,
            }

    pos = state.get("position") or status.position
    if isinstance(pos, dict):
        return pos
    return {"x": 0, "y": 64, "z": 0}


def _get_follow_player_name(minecraft_bot_manager, status) -> str:
    """Find nearest player username (excluding controlled bot username)."""
    if not minecraft_bot_manager:
        return ""
    tracker = minecraft_bot_manager.state_tracker
    bot_name = (getattr(status, "username", "") or "").strip().lower()
    nearest_player = tracker.get_nearest_player(exclude_name=bot_name)
    if not nearest_player:
        return ""
    return str(nearest_player.username or nearest_player.name or "").strip()


async def _perform_curiosity_trip(minecraft_bot_manager, state: dict, cfg: dict, *, schedule_emit_to_frontend, get_audio_loop):
    """Approach interesting spot briefly, comment, then return near anchor."""
    if not minecraft_bot_manager:
        return

    tracker = minecraft_bot_manager.state_tracker
    interesting = tracker.get_nearby_interesting(max_distance=24, top_n=3)
    if not interesting:
        return

    target = None
    excluded_types = {"water", "lava", "cave_air"}
    for block in interesting:
        if block.block_type in excluded_types:
            continue
        if block.interestingness < 0.45 or block.distance < 4:
            continue
        snapshot = state or tracker.get_state_snapshot() or {}
        start_pos = snapshot.get("position")
        if isinstance(start_pos, dict):
            start_y = float(start_pos.get("y", 64))
            if abs(float(block.position.y) - start_y) > 3.0:
                continue
        if block.distance > 18:
            continue
        if block.interestingness >= 0.45:
            target = block
            break
    if not target:
        return

    snapshot = state or tracker.get_state_snapshot() or {}
    start_pos = snapshot.get("position")
    if not isinstance(start_pos, dict):
        return

    await minecraft_bot_manager.send_action(
        "move_to_position",
        {
            "x": int(target.position.x),
            "y": int(target.position.y),
            "z": int(target.position.z),
            "range": 2,
        },
        wait_for_result=True,
        timeout_seconds=18.0,
    )

    await _emit_minecraft_autonomy_comment(
        f"Podeszłam sprawdzić {target.block_type}. Wygląda ciekawie.",
        to_user=True,
        cfg=cfg,
        schedule_emit_to_frontend=schedule_emit_to_frontend,
        get_audio_loop=get_audio_loop,
    )

    await asyncio.sleep(1.2)

    await minecraft_bot_manager.send_action(
        "move_to_position",
        {
            "x": int(round(float(start_pos.get("x", 0)))),
            "y": int(round(float(start_pos.get("y", 64)))),
            "z": int(round(float(start_pos.get("z", 0)))),
            "range": int(cfg.get("move_range", 2) or 2),
        },
        wait_for_result=True,
        timeout_seconds=18.0,
    )


def _pick_look_target(minecraft_bot_manager, state: dict, status, cfg: dict):
    """Choose a natural point to glance at: entity first, then nearby interesting point, then random offset."""
    if not minecraft_bot_manager:
        return None, None

    tracker = minecraft_bot_manager.state_tracker
    max_dist = float(cfg.get("look_entity_max_distance", 20) or 20)
    bot_name = (getattr(status, "username", "") or "").strip().lower()
    focus = tracker.get_focus_entity(exclude_name=bot_name, max_distance=max_dist)
    if focus:
        return {
            "x": focus.position.x,
            "y": focus.position.y + 1.0,
            "z": focus.position.z,
        }, focus

    interesting = tracker.get_nearby_interesting(max_distance=14, top_n=1)
    if interesting:
        block = interesting[0]
        return {"x": block.position.x, "y": block.position.y + 1.0, "z": block.position.z}, None

    pos = state.get("position") or status.position
    if isinstance(pos, dict):
        px = float(pos.get("x", 0))
        py = float(pos.get("y", 64))
        pz = float(pos.get("z", 0))
        return {
            "x": px + random.randint(-5, 5),
            "y": py + random.choice([0, 1, 2]),
            "z": pz + random.randint(-5, 5),
        }, None

    return None, None


async def run_minecraft_autonomy_loop(
    *,
    get_minecraft_bot_manager,
    get_audio_loop,
    schedule_emit_to_frontend,
    get_minecraft_autonomy_state,
    set_minecraft_autonomy_state,
    get_minecraft_autonomy_last_error_ts,
    set_minecraft_autonomy_last_error_ts,
    minecraft_autonomy_cfg,
    set_minecraft_game_mode,
):
    """Lightweight autonomy loop for visual liveliness in Minecraft."""
    print("[SERVER] [Minecraft Autonomy] Loop started")
    while True:
        await asyncio.sleep(4.0)

        try:
            minecraft_bot_manager = get_minecraft_bot_manager()
            if not minecraft_bot_manager:
                continue

            status = minecraft_bot_manager.get_status()
            if not status.is_connected:
                continue

            cfg = minecraft_autonomy_cfg()
            if not cfg.get("enabled", True):
                continue

            now = time.time()
            autonomy_state = get_minecraft_autonomy_state() or {}

            autonomy_state.setdefault("last_scan_ts", 0.0)
            autonomy_state.setdefault("last_look_ts", 0.0)
            autonomy_state.setdefault("last_move_ts", 0.0)
            autonomy_state.setdefault("last_comment_ts", 0.0)
            autonomy_state.setdefault("last_curiosity_ts", 0.0)
            autonomy_state.setdefault("last_proposal_ts", 0.0)

            scan_interval = float(cfg.get("scan_interval_sec", 18.0) or 18.0)
            if now - autonomy_state["last_scan_ts"] >= max(8.0, scan_interval):
                scan_range = int(cfg.get("scan_range", 40) or 40)
                await minecraft_bot_manager.send_action(
                    "get_nearby_scan",
                    {"range": max(10, min(scan_range, 100))},
                    wait_for_result=True,
                    timeout_seconds=12.0,
                )
                autonomy_state["last_scan_ts"] = now

            tracker = minecraft_bot_manager.state_tracker
            state = tracker.get_state_snapshot() or {}
            danger_level = state.get("danger_level", "safe")

            look_interval = float(cfg.get("look_interval_sec", 14.0) or 14.0)
            if now - autonomy_state.get("last_look_ts", 0.0) >= max(10.0, look_interval):
                look_target, focus_entity = _pick_look_target(minecraft_bot_manager, state, status, cfg)
                if isinstance(look_target, dict):
                    await minecraft_bot_manager.send_action(
                        "look_at_position",
                        {
                            "x": look_target.get("x"),
                            "y": look_target.get("y"),
                            "z": look_target.get("z"),
                        },
                        wait_for_result=True,
                        timeout_seconds=5.0,
                    )
                    autonomy_state["last_look_ts"] = now

                    if focus_entity and random.random() < 0.10:
                        label = focus_entity.username or focus_entity.name
                        await _emit_minecraft_autonomy_comment(
                            f"Widzę {label} niedaleko. Obserwuję, co robi.",
                            to_user=False,
                            cfg=cfg,
                            schedule_emit_to_frontend=schedule_emit_to_frontend,
                            get_audio_loop=get_audio_loop,
                        )

            move_interval = float(cfg.get("move_interval_sec", 20.0) or 20.0)
            if danger_level in ("safe", "caution") and (
                now - autonomy_state.get("last_move_ts", 0.0) >= max(10.0, move_interval)
            ):
                follow_name = _get_follow_player_name(minecraft_bot_manager, status)
                if follow_name:
                    comfort_range = random.randint(3, max(4, int(cfg.get("follow_radius", 10))))
                    await minecraft_bot_manager.send_action(
                        "move_to_player",
                        {
                            "name": follow_name,
                            "range": comfort_range,
                        },
                        wait_for_result=True,
                        timeout_seconds=16.0,
                    )
                    autonomy_state["last_move_ts"] = now
                else:
                    pos = _get_follow_anchor_position(minecraft_bot_manager, state, status, cfg)
                    if isinstance(pos, dict):
                        radius = int(cfg.get("wander_radius", 6) or 6)
                        radius = max(2, min(radius, 10))
                        dx = random.randint(-radius, radius)
                        dz = random.randint(-radius, radius)
                        if dx == 0 and dz == 0:
                            dx = 1
                        tx = int(round(float(pos.get("x", 0)) + dx))
                        ty = int(round(float(pos.get("y", 64))))
                        tz = int(round(float(pos.get("z", 0)) + dz))
                        await minecraft_bot_manager.send_action(
                            "move_to_position",
                            {
                                "x": tx,
                                "y": ty,
                                "z": tz,
                                "range": int(cfg.get("move_range", 2) or 2),
                            },
                            wait_for_result=True,
                            timeout_seconds=16.0,
                        )
                        autonomy_state["last_move_ts"] = now

            curiosity_interval = float(cfg.get("curiosity_interval_sec", 45.0) or 45.0)
            if danger_level == "safe" and (
                now - autonomy_state.get("last_curiosity_ts", 0.0) >= max(20.0, curiosity_interval)
            ):
                await _perform_curiosity_trip(
                    minecraft_bot_manager,
                    state,
                    cfg,
                    schedule_emit_to_frontend=schedule_emit_to_frontend,
                    get_audio_loop=get_audio_loop,
                )
                autonomy_state["last_curiosity_ts"] = now

            comment_interval = float(cfg.get("comment_interval_sec", 42.0) or 42.0)
            if now - autonomy_state.get("last_comment_ts", 0.0) >= max(25.0, comment_interval):
                to_user = _pick_comment_mode(cfg)
                line = _build_minecraft_autonomy_observation(minecraft_bot_manager, to_user=to_user)
                await _emit_minecraft_autonomy_comment(
                    line,
                    to_user=to_user,
                    cfg=cfg,
                    schedule_emit_to_frontend=schedule_emit_to_frontend,
                    get_audio_loop=get_audio_loop,
                )
                autonomy_state["last_comment_ts"] = now

            proposal_interval = float(cfg.get("proposal_interval_sec", 65.0) or 65.0)
            if now - autonomy_state.get("last_proposal_ts", 0.0) >= max(40.0, proposal_interval):
                interesting = minecraft_bot_manager.state_tracker.get_nearby_interesting(max_distance=26, top_n=1)
                if interesting:
                    target = interesting[0]
                    suggestion = (
                        f"Mam propozycję: mogę podejść do {target.block_type} "
                        f"({target.distance:.1f}m) i sprawdzić teren."
                    )
                else:
                    suggestion = "Mogę zrobić krótki patrol wokół Ciebie i meldować co widzę."

                await _emit_minecraft_autonomy_comment(
                    suggestion,
                    to_user=True,
                    cfg=cfg,
                    schedule_emit_to_frontend=schedule_emit_to_frontend,
                    get_audio_loop=get_audio_loop,
                )
                autonomy_state["last_proposal_ts"] = now

            set_minecraft_autonomy_state(autonomy_state)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            err_now = time.time()
            last_error_ts = float(get_minecraft_autonomy_last_error_ts() or 0.0)
            if err_now - last_error_ts >= 20.0:
                print(f"[SERVER] [Minecraft Autonomy] Loop error: {e}")
                set_minecraft_autonomy_last_error_ts(err_now)
