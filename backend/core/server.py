import asyncio
from contextlib import asynccontextmanager
import sys
import os
import base64
import json
import time
import re
from datetime import datetime
from pathlib import Path

# Fix for asyncio subprocess support on Windows
# MUST BE SET BEFORE OTHER IMPORTS
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import socketio
import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from ..integrations.media.study_reader import StudyReader
from ..integrations.media.study_ocr import ocr_image_bytes
from dataclasses import asdict

from . import monikai
from .config import DATA_DIR as CONFIG_DATA_DIR
from .daily_briefing_runtime import DailyBriefingRuntime
from .calendar_reminder_handlers import register_calendar_reminder_handlers
from .chat_input_handlers import register_chat_input_handlers
from .control_handlers import register_control_handlers
from .daily_briefing_handlers import register_daily_briefing_handlers
from .memory_page_handlers import register_memory_page_handlers
from .notes_journal_handlers import register_notes_journal_handlers
from .session_mode_handlers import register_session_mode_handlers
from .frontend_router import (
    clear_active_frontend_sid,
    emit_to_frontend as _emit_to_frontend,
    register_socketio,
    schedule_emit_to_frontend as _schedule_emit_to_frontend,
    set_active_frontend_sid,
)
from .lifecycle_shutdown import (
    request_shutdown_from_signal as _request_shutdown_from_signal_impl,
    shutdown_and_exit as _shutdown_and_exit_impl,
    stop_minecraft_runtime,
    stop_runtime_components as _stop_runtime_components_impl,
)
from .lifecycle_startup import (
    initialize_calendar_manager,
    initialize_minecraft_bot_manager,
    initialize_reminder_and_personality,
    initialize_smart_home_agents,
    initialize_spotify_manager,
)
from .lifecycle_telegram import start_telegram_service, stop_telegram_service
from .minecraft_autonomy_runtime import (
    build_minecraft_autonomy_cfg,
    run_minecraft_autonomy_loop,
    set_minecraft_game_mode as set_minecraft_game_mode_runtime,
)
from .minecraft_http_router import register_minecraft_http_routes
from .minecraft_perception_runtime import register_minecraft_perception_callback
from .minecraft_socket_handlers import register_minecraft_socket_handlers
from .screen_ocr_runtime import ScreenOcrRuntime
from .settings_store import DEFAULT_SETTINGS, SETTINGS, load_settings, save_settings
from .study_http_router import register_study_http_routes
from .study_socket_handlers import register_study_socket_handlers
from ..ai.daily_briefing import DEFAULT_SECTIONS
from ..ai.personality_notifications import to_frontend_personality_event
from ..integrations.media.authenticator import FaceAuthenticator
from ..agents.kasa_agent import KasaAgent
MAIN_LOOP = None
minecraft_bot_manager = None
minecraft_autonomy_task = None
minecraft_autonomy_last_error_ts = 0.0
minecraft_autonomy_state = {
    "last_scan_ts": 0.0,
    "last_look_ts": 0.0,
    "last_move_ts": 0.0,
    "last_comment_ts": 0.0,
    "last_curiosity_ts": 0.0,
    "last_proposal_ts": 0.0,
    "last_bot_action_ts": 0.0,
}

# Smart home integrations
hue_agent = None
home_assistant_agent = None


def _stop_runtime_components():
    global audio_loop, loop_task, authenticator
    audio_loop, loop_task = _stop_runtime_components_impl(audio_loop, loop_task, authenticator)


async def _shutdown_and_exit(reason: str, delay_seconds: float = 0.15):
    await _shutdown_and_exit_impl(
        reason,
        stop_components_cb=_stop_runtime_components,
        delay_seconds=delay_seconds,
    )


def _request_shutdown_from_signal(sig):
    _request_shutdown_from_signal_impl(
        sig,
        main_loop=MAIN_LOOP,
        shutdown_coro_factory=lambda reason: _shutdown_and_exit(reason),
        stop_components_cb=_stop_runtime_components,
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code to run on startup
    print(f"[SERVER DEBUG] Startup Event Triggered")
    print(f"[SERVER DEBUG] Python Version: {sys.version}")
    try:
        loop = asyncio.get_running_loop()
        global MAIN_LOOP
        MAIN_LOOP = loop
        print(f"[SERVER DEBUG] Running Loop: {type(loop)}")
        policy = asyncio.get_event_loop_policy()
        print(f"[SERVER DEBUG] Current Policy: {type(policy)}")
    except Exception as e:
        print(f"[SERVER DEBUG] Error checking loop: {e}")

    global hue_agent, home_assistant_agent
    hue_agent, home_assistant_agent = await initialize_smart_home_agents(
        kasa_agent,
        SETTINGS,
    )

    # Initialize Global Managers (Persistent across AI sessions)
    global calendar_manager, reminder_manager, personality_system, spotify_manager
    data_dir = DATA_DIR
    user_memory_dir = data_dir / "user_memory"
    user_memory_dir.mkdir(parents=True, exist_ok=True)

    # 1. Calendar
    calendar_manager = initialize_calendar_manager(
        monikai,
        user_memory_dir,
        schedule_emit_to_frontend=_schedule_emit_to_frontend,
    )

    # 2-3. Reminders + Personality
    def _get_audio_loop():
        return audio_loop

    def _get_main_loop():
        return MAIN_LOOP

    reminder_manager, personality_system = initialize_reminder_and_personality(
        monikai,
        user_memory_dir,
        schedule_emit_to_frontend=_schedule_emit_to_frontend,
        serialize_reminders=_serialize_reminders,
        get_audio_loop=_get_audio_loop,
        emit_to_frontend=_emit_to_frontend,
        get_main_loop=_get_main_loop,
    )

    # 4. Spotify Manager (OAuth + token refresh)
    spotify_manager = initialize_spotify_manager(data_dir)

    # 5. Minecraft Bot Manager
    global minecraft_bot_manager
    minecraft_bot_manager = initialize_minecraft_bot_manager(Path(__file__).resolve())
    if minecraft_bot_manager:
        def _get_audio_loop():
            return audio_loop

        def _get_minecraft_autonomy_task():
            return minecraft_autonomy_task

        def _set_minecraft_autonomy_task(task):
            global minecraft_autonomy_task
            minecraft_autonomy_task = task

        def _set_minecraft_autonomy_state(state):
            global minecraft_autonomy_state
            minecraft_autonomy_state = state

        registered = register_minecraft_perception_callback(
            minecraft_bot_manager,
            get_audio_loop=_get_audio_loop,
            schedule_emit_to_frontend=_schedule_emit_to_frontend,
            minecraft_autonomy_cfg=_minecraft_autonomy_cfg,
            set_minecraft_game_mode=_set_minecraft_game_mode,
            minecraft_autonomy_loop=_minecraft_autonomy_loop,
            get_minecraft_autonomy_task=_get_minecraft_autonomy_task,
            set_minecraft_autonomy_task=_set_minecraft_autonomy_task,
            set_minecraft_autonomy_state=_set_minecraft_autonomy_state,
        )
        if not registered:
            minecraft_bot_manager = None

    global telegram_service, telegram_task
    telegram_service, telegram_task = start_telegram_service(
        lambda: SETTINGS,
        calendar_manager=calendar_manager,
        reminder_manager=reminder_manager,
        spotify_manager=spotify_manager,
        personality=personality_system,
    )

    try:
        yield
    finally:
        global minecraft_autonomy_task
        _, minecraft_autonomy_task = await stop_minecraft_runtime(
            minecraft_bot_manager,
            minecraft_autonomy_task,
        )
        
        telegram_service, telegram_task = await stop_telegram_service(
            telegram_service,
            telegram_task,
        )

# Create a Socket.IO server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*', max_http_buffer_size=25 * 1024 * 1024)
register_socketio(sio)
app = FastAPI(lifespan=lifespan)

register_minecraft_http_routes(
    app,
    get_minecraft_bot_manager=lambda: minecraft_bot_manager,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _force_cors_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Access-Control-Allow-Origin", "*")
    response.headers.setdefault("Access-Control-Allow-Methods", "GET, OPTIONS")
    response.headers.setdefault("Access-Control-Allow-Headers", "Range, Content-Type, Authorization")
    response.headers.setdefault("Access-Control-Expose-Headers", "Content-Length, Content-Range, Accept-Ranges")
    return response
app_socketio = socketio.ASGIApp(sio, app)

import signal

# --- SHUTDOWN HANDLER ---
def signal_handler(sig, frame):
    _request_shutdown_from_signal(sig)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Global state
audio_loop = None
calendar_manager = None
reminder_manager = None
personality_system = None
spotify_manager = None
loop_task = None
authenticator = None
kasa_agent = KasaAgent()
DATA_DIR = CONFIG_DATA_DIR
STUDY_DIR = DATA_DIR / "study"
last_start_params = {}
telegram_service = None
telegram_task = None
DAILY_BRIEFING_RUNTIME = DailyBriefingRuntime(
    SETTINGS,
    get_audio_loop=lambda: audio_loop,
    get_personality_system=lambda: personality_system,
)


def _safe_study_path(rel_path: str) -> Path:
    raw = (rel_path or "").replace("\\", "/").lstrip("/")
    candidate = (STUDY_DIR / raw).resolve()
    if STUDY_DIR not in candidate.parents and candidate != STUDY_DIR:
        raise HTTPException(status_code=400, detail="Invalid study path.")
    return candidate

STUDY_READER = StudyReader()

register_study_http_routes(
    app,
    study_dir=STUDY_DIR,
    safe_study_path=_safe_study_path,
)

register_study_socket_handlers(
    sio,
    get_audio_loop=lambda: audio_loop,
    study_reader=STUDY_READER,
    safe_study_path=_safe_study_path,
    ocr_image_bytes_fn=ocr_image_bytes,
)

register_daily_briefing_handlers(
    sio,
    runtime=DAILY_BRIEFING_RUNTIME,
    save_settings=save_settings,
    emit_to_frontend=_emit_to_frontend,
    settings=SETTINGS,
    default_sections=DEFAULT_SECTIONS,
)

register_calendar_reminder_handlers(
    sio,
    get_calendar_manager=lambda: calendar_manager,
    get_reminder_manager=lambda: reminder_manager,
    serialize_reminders=lambda: _serialize_reminders(),
    get_audio_loop=lambda: audio_loop,
)

register_control_handlers(
    sio,
    get_audio_loop=lambda: audio_loop,
    shutdown_and_exit=_shutdown_and_exit,
)

SCREEN_OCR_RUNTIME = ScreenOcrRuntime(
    get_audio_loop=lambda: audio_loop,
    ocr_image_bytes_fn=ocr_image_bytes,
)


def _get_vn_user_buf():
    return _vn_user_buf


def _set_vn_user_buf(value):
    global _vn_user_buf
    _vn_user_buf = value


def _set_vn_user_last_ts(value):
    global _vn_user_last_ts
    _vn_user_last_ts = value


def _get_vn_scene_task():
    return _vn_scene_task


def _set_vn_scene_task(task):
    global _vn_scene_task
    _vn_scene_task = task


def _create_debounced_vn_scene_task():
    return asyncio.create_task(_debounced_vn_scene_check())


register_chat_input_handlers(
    sio,
    get_audio_loop=lambda: audio_loop,
    emit_to_frontend=_emit_to_frontend,
    audio_loop_mark_user_activity=lambda loop, text: audio_loop_mark_user_activity(loop, text),
    get_vn_user_buf=_get_vn_user_buf,
    set_vn_user_buf=_set_vn_user_buf,
    set_vn_user_last_ts=_set_vn_user_last_ts,
    get_vn_scene_task=_get_vn_scene_task,
    set_vn_scene_task=_set_vn_scene_task,
    create_debounced_vn_scene_task=_create_debounced_vn_scene_task,
    is_private_web_task_request=lambda text: _is_private_web_task_request(text),
    study_reader=STUDY_READER,
    screen_ocr_runtime=SCREEN_OCR_RUNTIME,
)

register_notes_journal_handlers(
    sio,
    read_notes_text=lambda: _read_notes_text(),
    write_notes_text=lambda content: _write_notes_text(content),
    append_notes_text=lambda content: _append_notes_text(content),
    read_journal_today=lambda: _read_journal_today(),
    get_audio_loop=lambda: audio_loop,
)

register_memory_page_handlers(
    sio,
    data_dir=DATA_DIR,
    resolve_memory_page=lambda path: _resolve_memory_page(path),
    list_memory_pages=lambda: _list_memory_pages(),
    get_audio_loop=lambda: audio_loop,
)

register_session_mode_handlers(
    sio,
    get_audio_loop=lambda: audio_loop,
    journal_today_path=lambda: _journal_today_path(),
    data_dir=DATA_DIR,
)


def _is_private_web_task_request(text: str) -> bool:
    if not text:
        return False
    t = str(text).lower()
    patterns = [
        r"\bgmail\b",
        r"\binbox\b",
        r"\bmailbox\b",
        r"\bemail\b",
        r"\be-mail\b",
        r"\bagent\s+web\b",
        r"\bweb\s+agent\b",
        r"\bopenclaw\b",
        r"\bpoczta\b",
        r"\bskrzynk\w*\b",
        r"\bsprawd[zź]\w*\b.*\b(mail|gmail|poczt\w*|skrzynk\w*)\b",
        r"\bwejd[zź]\w*\b.*\b(gmail|mail|poczt\w*|konto)\b",
        r"\bzaloguj\w*\b.*\b(gmail|mail|poczt\w*|konto)\b",
    ]
    return any(re.search(p, t) for p in patterns)


def _minecraft_autonomy_cfg() -> dict:
    return build_minecraft_autonomy_cfg(DEFAULT_SETTINGS, SETTINGS)


async def _set_minecraft_game_mode(active: bool):
    await set_minecraft_game_mode_runtime(active, get_audio_loop=lambda: audio_loop)


def _get_minecraft_autonomy_last_error_ts():
    return minecraft_autonomy_last_error_ts


def _set_minecraft_autonomy_last_error_ts(value):
    global minecraft_autonomy_last_error_ts
    minecraft_autonomy_last_error_ts = value


async def _minecraft_autonomy_loop():
    await run_minecraft_autonomy_loop(
        get_minecraft_bot_manager=lambda: minecraft_bot_manager,
        get_audio_loop=lambda: audio_loop,
        schedule_emit_to_frontend=_schedule_emit_to_frontend,
        get_minecraft_autonomy_state=lambda: minecraft_autonomy_state,
        set_minecraft_autonomy_state=lambda state: _set_minecraft_autonomy_state(state),
        get_minecraft_autonomy_last_error_ts=_get_minecraft_autonomy_last_error_ts,
        set_minecraft_autonomy_last_error_ts=_set_minecraft_autonomy_last_error_ts,
        minecraft_autonomy_cfg=_minecraft_autonomy_cfg,
        set_minecraft_game_mode=_set_minecraft_game_mode,
    )


def _get_minecraft_autonomy_task():
    return minecraft_autonomy_task


def _set_minecraft_autonomy_task(task):
    global minecraft_autonomy_task
    minecraft_autonomy_task = task


def _set_minecraft_autonomy_state(state):
    global minecraft_autonomy_state
    minecraft_autonomy_state = state


register_minecraft_socket_handlers(
    sio,
    get_minecraft_bot_manager=lambda: minecraft_bot_manager,
    get_audio_loop=lambda: audio_loop,
    get_minecraft_autonomy_task=_get_minecraft_autonomy_task,
    set_minecraft_autonomy_task=_set_minecraft_autonomy_task,
    set_minecraft_autonomy_state=_set_minecraft_autonomy_state,
    minecraft_autonomy_loop=_minecraft_autonomy_loop,
    minecraft_autonomy_cfg=_minecraft_autonomy_cfg,
    set_minecraft_game_mode=_set_minecraft_game_mode,
    settings=SETTINGS,
    save_settings=save_settings,
)


# Load on startup
load_settings()

authenticator = None
# Initialize Kasa agent with devices from new smart_home structure
kasa_devices = SETTINGS.get("smart_home", {}).get("kasa", {}).get("devices", [])
# Fallback to old location for backward compatibility
if not kasa_devices:
    kasa_devices = SETTINGS.get("kasa_devices", [])
kasa_agent = KasaAgent(known_devices=kasa_devices)
# tool_permissions is now SETTINGS["tool_permissions"]

@app.get("/status")
async def status():
    return {"status": "running", "service": "MonikAI Backend"}


@app.get("/spotify/status")
async def spotify_status_http():
    if not spotify_manager:
        return {"ok": False, "error": "spotify manager unavailable"}
    try:
        return {"ok": True, "status": spotify_manager.status()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/spotify/auth/start")
async def spotify_auth_start_http():
    if not spotify_manager:
        raise HTTPException(status_code=503, detail="spotify manager unavailable")
    try:
        url = spotify_manager.build_auth_url()
        return {"ok": True, "url": url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/spotify/callback")
async def spotify_auth_callback_http(
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
):
    if not spotify_manager:
        raise HTTPException(status_code=503, detail="spotify manager unavailable")
    if error:
        detail = str(error_description or error).strip() or "spotify authorization failed"
        raise HTTPException(status_code=400, detail=detail)
    if not code:
        raise HTTPException(status_code=400, detail="missing code")
    try:
        status_obj = spotify_manager.exchange_code(code, state=state)
        try:
            await _emit_to_frontend("spotify_status", {"ok": True, "status": status_obj})
        except Exception:
            pass
        return Response(
            content=(
                "<html><body style='font-family: sans-serif; padding: 24px;'>"
                "<h2>Spotify connected.</h2>"
                "<p>You can close this tab and return to MonikAI.</p>"
                "</body></html>"
            ),
            media_type="text/html",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# PROGRESSION SYSTEM ENDPOINTS
# ============================================================================

@app.get("/api/progression/profile")
async def get_progression_profile():
    """Get user profile from progression system"""
    try:
        if not MAIN_LOOP or not hasattr(MAIN_LOOP, 'personality') or not hasattr(MAIN_LOOP.personality, 'progression'):
            return {"error": "Progression system not available"}
        profile = MAIN_LOOP.personality.progression.profile_manager.get_profile()
        if not profile:
            return {"error": "No profile loaded"}
        return profile.to_dict()
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/progression/metrics")
async def get_progression_metrics():
    """Get relationship metrics"""
    try:
        if not MAIN_LOOP or not hasattr(MAIN_LOOP, 'personality') or not hasattr(MAIN_LOOP.personality, 'progression'):
            return {"error": "Progression system not available"}
        metrics = MAIN_LOOP.personality.progression.metrics_engine.get_metrics_state()
        progress = MAIN_LOOP.personality.progression.metrics_engine.get_recommendation_progress()
        return {"metrics": metrics, "progress": progress}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/progression/quests/today")
async def get_progression_quests_today():
    """Get today's quests"""
    try:
        if not MAIN_LOOP or not hasattr(MAIN_LOOP, 'personality') or not hasattr(MAIN_LOOP.personality, 'progression'):
            return {"error": "Progression system not available"}
        quests = [q.to_dict() for q in MAIN_LOOP.personality.progression.quest_system.active_quests]
        return {"quests": quests, "total": len(quests)}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/progression/achievements")
async def get_progression_achievements():
    """Get achievements"""
    try:
        if not MAIN_LOOP or not hasattr(MAIN_LOOP, 'personality') or not hasattr(MAIN_LOOP.personality, 'progression'):
            return {"error": "Progression system not available"}
        unlocked = MAIN_LOOP.personality.progression.achievement_tracker.get_unlocked_achievements()
        locked = MAIN_LOOP.personality.progression.achievement_tracker.get_locked_achievements()
        return {
            "unlocked": [a.to_dict() for a in unlocked],
            "locked": [a.to_dict() for a in locked]
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/progression/unlocks")
async def get_progression_unlocks():
    """Get active unlocks"""
    try:
        if not MAIN_LOOP or not hasattr(MAIN_LOOP, 'personality') or not hasattr(MAIN_LOOP.personality, 'progression'):
            return {"error": "Progression system not available"}
        active = MAIN_LOOP.personality.progression.unlock_tracker.get_active_unlocks()
        return {"active_unlocks": active, "count": len(active)}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/progression/state")
async def get_progression_state():
    """Get full progression state"""
    try:
        if not MAIN_LOOP or not hasattr(MAIN_LOOP, 'personality') or not hasattr(MAIN_LOOP.personality, 'progression'):
            return {"error": "Progression system not available"}
        state = MAIN_LOOP.personality.progression.get_progression_state()
        return state
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/progression/notifications")
async def get_progression_notifications():
    """Get pending progression notifications"""
    try:
        if not MAIN_LOOP or not hasattr(MAIN_LOOP, 'personality') or not hasattr(MAIN_LOOP.personality, 'progression'):
            return {"error": "Progression system not available"}
        notifications = MAIN_LOOP.personality.progression.get_pending_notifications()
        return {"notifications": notifications}
    except Exception as e:
        return {"error": str(e)}


@sio.event
async def connect(sid, environ):
    set_active_frontend_sid(sid)
    print(f"[SYSTEM NOTIFICATION] Client connected: {sid}")
    await sio.emit('status', {'msg': 'Connected to MonikAI Backend'}, room=sid)

    global authenticator
    
    # Callback for Auth Status
    async def on_auth_status(is_auth):
        print(f"[SERVER] Auth status change: {is_auth}")
        await _emit_to_frontend('auth_status', {'authenticated': is_auth})

    # Callback for Auth Camera Frames
    async def on_auth_frame(frame_b64):
        await _emit_to_frontend('auth_frame', {'image': frame_b64})

    # Initialize Authenticator if not already done
    if authenticator is None:
        authenticator = FaceAuthenticator(
            reference_image_path=str(DATA_DIR / "reference.jpg"),
            on_status_change=on_auth_status,
            on_frame=on_auth_frame
        )
    
    # Check if already authenticated or needs to start
    if authenticator.authenticated:
        await sio.emit('auth_status', {'authenticated': True}, room=sid)
    else:
        # Check Settings for Auth
        if SETTINGS.get("face_auth_enabled", False):
            await sio.emit('auth_status', {'authenticated': False}, room=sid)
            # Start the auth loop in background
            asyncio.create_task(authenticator.start_authentication_loop())
        else:
            # Bypass Auth
            print("Face Auth Disabled. Auto-authenticating.")
            # We don't change authenticator state to true to avoid confusion if re-enabled? 
            # Or we should just tell client it's auth'd.
            await sio.emit('auth_status', {'authenticated': True}, room=sid)

@sio.event
async def disconnect(sid):
    """
    Handle client disconnect:
    1. Clear active frontend SID
    2. Generate session-end recap (PHASE B)
    3. Generate daily recap (PHASE C)
    4. Create memory summary
    """
    global audio_loop
    clear_active_frontend_sid(sid)
    print(f"Client disconnected: {sid}")
    
    # PHASE B + C: Generate recaps at session end
    try:
        if audio_loop and hasattr(audio_loop, 'session_manager'):
            session_id = audio_loop.session_manager.get_current_session_id()
            session_path = audio_loop.session_manager.get_current_session_path()
            
            if session_id and session_path:
                # Get session times from meta.json
                meta_file = session_path / "meta.json"
                if meta_file.exists():
                    import json
                    meta = json.loads(meta_file.read_text())
                    session_start = meta.get("started_at", datetime.now().isoformat())
                    session_end = datetime.now().isoformat()
                    
                    # PHASE B: Generate session recap if calendar_engine available
                    if hasattr(audio_loop, 'calendar_engine'):
                        recap = audio_loop.calendar_engine.generate_session_recap(
                            session_start=session_start,
                            session_end=session_end,
                            session_summary=None
                        )
                        print(f"[CALENDAR] Session recap generated: {session_id}")
                    
                    # PHASE C: Generate daily recap if recap_generator available
                    if hasattr(audio_loop, 'recap_generator'):
                        today = datetime.now().strftime("%Y-%m-%d")
                        daily_recap = audio_loop.recap_generator.generate_daily_recap(date=today)
                        if daily_recap:
                            print(f"[RECAP] Daily recap generated for {today}")
    except Exception as e:
        print(f"[RECAP] Error generating recaps on disconnect: {e}")

@sio.event
async def start_audio(sid, data=None):
    global audio_loop, loop_task, last_start_params
    set_active_frontend_sid(sid)
    
    # Save params for auto-restart
    last_start_params = {'sid': sid, 'data': data}
    
    # Optional: Block if not authenticated
    # Only block if auth is ENABLED and not authenticated
    if SETTINGS.get("face_auth_enabled", False):
        if authenticator and not authenticator.authenticated:
            print("[SYSTEM ERROR] Blocked start_audio: Not authenticated.")
            await sio.emit('error', {'msg': 'Authentication Required'}, room=sid)
            return

    print("[SYSTEM NOTIFICATION] Starting Audio Loop...")
    
    device_index = None
    device_name = None
    if data:
        if 'device_index' in data:
            device_index = data['device_index']
        if 'device_name' in data:
            device_name = data['device_name']
            
    print(f"[SYSTEM NOTIFICATION] Using input device: Name='{device_name}', Index={device_index}")
    
    if loop_task and not loop_task.done():
        print("[SYSTEM NOTIFICATION] Audio loop already running. Re-connecting client to session.")
        await sio.emit('status', {'msg': 'MonikAI Already Running'}, room=sid)
        return
    if audio_loop:
        if loop_task and (loop_task.done() or loop_task.cancelled()):
            print("[SYSTEM NOTIFICATION] Audio loop task appeared finished/cancelled. Clearing and restarting...")
            audio_loop = None
            loop_task = None
        else:
            print("[SYSTEM NOTIFICATION] Audio loop already running. Re-connecting client to session.")
            await sio.emit('status', {'msg': 'MonikAI Already Running'}, room=sid)
            return


    # Callback to send audio data to frontend
    def on_audio_data(data_bytes):
        # We need to schedule this on the event loop
        # This is high frequency, so we might want to downsample or batch if it's too much
        _schedule_emit_to_frontend('audio_data', {'data': list(data_bytes)})

    # Callback to send Browser data to frontend
    def on_web_data(data):
        log_text = str((data or {}).get("log") or "")
        job_id = (data or {}).get("job_id")
        job_status = (data or {}).get("job_status")
        if log_text:
            compact = " ".join(log_text.split())
            if len(compact) > 320:
                compact = compact[:317] + "..."
            print(f"[WEB AGENT] job={job_id or '-'} status={job_status or '-'} log={compact}")
        else:
            print(f"Sending Browser data to frontend: {len(log_text)} chars logs")
        _schedule_emit_to_frontend('browser_frame', data)
        
    # Callback to send Transcription data to frontend
    def on_transcription(data):
        # data = {"sender": "User"|"MonikAI", "text": "..."}
        _schedule_emit_to_frontend('transcription', data)

        try:
            sender = (data or {}).get("sender", "")
            text = (data or {}).get("text") or ""
            if sender in ("Ty", "User") and text:
                norm_text = str(text).lower()
                if re.search(r"\bcan you see (this )?current page\??\b", norm_text):
                    _schedule_emit_to_frontend('study_request_share', {'reason': 'current_page'})

                    async def _send_reminder():
                        reminder = (
                            'System Notification: The user is asking if you can see the current study page. '
                            'You must tell them: "Send me the current page", and explain you can only read it '
                            "after they send it via the chat button."
                        )
                        try:
                            if hasattr(audio_loop, "send_system_message"):
                                await audio_loop.send_system_message(reminder, end_of_turn=False)
                            else:
                                await audio_loop.session.send(input=reminder, end_of_turn=False)
                        except Exception:
                            pass

                    asyncio.create_task(_send_reminder())
                else:
                    SCREEN_OCR_RUNTIME.schedule_from_transcription()
        except Exception:
            pass

        # Scene switching based on user text
        try:
            sender = (data or {}).get("sender", "")
            if sender in ("Ty", "User"):
                global _vn_user_buf, _vn_user_last_ts, _vn_scene_task
                _vn_user_buf = (_vn_user_buf + " " + (data.get("text") or "")).strip()[-400:]
                _vn_user_last_ts = time.time()
                if _vn_scene_task is None or _vn_scene_task.done():
                    _vn_scene_task = asyncio.create_task(_debounced_vn_scene_check())
        except Exception:
            pass

    # Callback to send Confirmation Request to frontend
    def on_tool_confirmation(data):
        # data = {"id": "uuid", "tool": "tool_name", "args": {...}}
        tool_name = data.get('tool', 'unknown')
        print(f"[SYSTEM NOTIFICATION] Requesting confirmation for tool: {tool_name}")
        _schedule_emit_to_frontend('tool_confirmation_request', data)

    # Callback to send Session Update to frontend
    def on_session_update(session_id):
        print(f"[SYSTEM NOTIFICATION] Session updated to: {session_id}")
        _schedule_emit_to_frontend('session_update', {'session': session_id})

    # Callback to show session prompt windows
    def on_session_prompt(payload):
        try:
            _schedule_emit_to_frontend('session_prompt', payload)
        except Exception:
            pass

    # Callback to send Device Update to frontend
    def on_device_update(devices):
        # devices is a list of dicts
        print(f"[SYSTEM NOTIFICATION] Smart device list updated: {len(devices)} devices found.")
        _schedule_emit_to_frontend('kasa_devices', devices)

    # Callback to send Notes update to frontend
    def on_notes_update(payload):
        try:
            print("[SYSTEM NOTIFICATION] Notes were updated.")
            _schedule_emit_to_frontend('notes_data', payload)
        except Exception:
            pass

    # Callback to send Error to frontend
    def on_error(msg):
        print(f"[SYSTEM ERROR] {msg}")
        _schedule_emit_to_frontend('error', {'msg': msg})

    # Callback to send Vision Frames (screen/camera) to frontend
    def on_video_frame(payload):
        try:
            _schedule_emit_to_frontend('vision_frame', payload)
        except Exception:
            pass

    # Callback to send a reminder/timer alarm event to frontend (for ringing / notifications)
    def on_reminder_fired(payload):
        try:
            message = payload.get('message', 'No message')
            print(f"[SYSTEM NOTIFICATION] Reminder fired: {message}")
            _schedule_emit_to_frontend('reminder_fired', payload)
            # Also push an updated list so UI stays consistent
            _schedule_emit_to_frontend('reminders_list', {'reminders': _serialize_reminders()})
        except Exception as e:
            print(f"[SERVER] Failed to emit reminder_fired: {e}")

    # Callback for Calendar data
    def on_calendar_update(events):
        try:
            print(f"[SERVER] Emitting calendar_data with {len(events)} events.")
            _schedule_emit_to_frontend('calendar_data', events)
        except Exception as e:
            print(f"[SERVER] Failed to emit calendar_data: {e}")

    # Callback for Personality data
    def on_personality_update(data):
        try:
            _schedule_emit_to_frontend('personality_status', data)
        except Exception as e:
            print(f"[SERVER] Failed to emit personality_status: {e}")

    # Callback for Internal Thoughts
    def on_internal_thought(thought):
        print(f"[SYSTEM NOTIFICATION] Internal Thought: {thought}")
        _schedule_emit_to_frontend('internal_thought', {'thought': thought})
        
        # Emit to chat log only when user enabled thought visibility.
        if bool(SETTINGS.get("show_internal_thoughts", False)):
            _schedule_emit_to_frontend('transcription', {
                "sender": "Monika (Thought)",
                "text": f"{thought}",
                "is_new": True
            })

    def on_reminders_updated():
        try:
            _schedule_emit_to_frontend('reminders_list', {'reminders': _serialize_reminders()})
        except Exception as e:
            print(f"[SERVER] Failed to emit reminders_list update: {e}")

    def on_study_fields(payload):
        try:
            _schedule_emit_to_frontend('study_fields', payload)
        except Exception as e:
            print(f"[SERVER] Failed to emit study_fields: {e}")

    def on_study_notes(payload):
        try:
            _schedule_emit_to_frontend('study_notes', payload)
        except Exception as e:
            print(f"[SERVER] Failed to emit study_notes: {e}")

    def on_study_page(payload):
        try:
            _schedule_emit_to_frontend('study_page', payload)
        except Exception as e:
            print(f"[SERVER] Failed to emit study_page: {e}")

    def on_personality_event(payload):
        try:
            raw = payload if isinstance(payload, dict) else {"type": "unknown", "raw": payload}
            event = to_frontend_personality_event(raw)
            _schedule_emit_to_frontend('personality_event', event)
        except Exception as e:
            print(f"[SERVER] Failed to emit personality_event: {e}")

    # Initialize MonikAI
    data_dir = DATA_DIR
    try:
        video_mode = "none"
        if data and isinstance(data, dict) and data.get("video_mode"):
            video_mode = str(data.get("video_mode")).lower()
        else:
            video_mode = str(SETTINGS.get("video_mode", "none")).lower()

        print(f"[SYSTEM NOTIFICATION] Initializing AudioLoop with device_index={device_index}, video_mode={video_mode}")
        audio_loop = monikai.AudioLoop(
            video_mode=video_mode,
            on_audio_data=on_audio_data,
            on_video_frame=on_video_frame,
            on_web_data=on_web_data,
            on_transcription=on_transcription,
            on_tool_confirmation=on_tool_confirmation,
            on_session_update=on_session_update,
            on_session_prompt=on_session_prompt,
            on_device_update=on_device_update,
            on_notes_update=on_notes_update,
            on_error=on_error,
            on_reminder_fired=on_reminder_fired,
            on_reminders_updated=on_reminders_updated,
            on_calendar_update=on_calendar_update,
            on_personality_update=on_personality_update,
            on_personality_event=on_personality_event,
            on_internal_thought=on_internal_thought,
            on_study_fields=on_study_fields,
            on_study_notes=on_study_notes,
            on_study_page=on_study_page,

            input_device_index=device_index,
            input_device_name=device_name,
            kasa_agent=kasa_agent,
            calendar_manager=calendar_manager,
            reminder_manager=reminder_manager,
            spotify_manager=spotify_manager,
            personality=personality_system
            
        )
        print("[SYSTEM NOTIFICATION] AudioLoop initialized successfully.")
        
        # Attach smart home agents
        audio_loop.hue_agent = hue_agent
        audio_loop.home_assistant_agent = home_assistant_agent
        
        # Set Minecraft bot manager reference
        audio_loop.minecraft_bot_manager = minecraft_bot_manager
        
        # PHASE B: Set calendar_engine for unified calendar system
        try:
            from backend.ai.calendar_unification import UnifiedCalendarEngine
            audio_loop.calendar_engine = UnifiedCalendarEngine(
                base_dir=data_dir,
                memory_engine=getattr(audio_loop, 'memory_engine', None),
                calendar_manager=calendar_manager
            )
        except Exception as e:
            print(f"[CALENDAR] Warning: Could not initialize UnifiedCalendarEngine in audio_loop: {e}")
        
        # PHASE C: Set recap_generator for daily recaps and hierarchical compression
        try:
            from backend.ai.daily_recap_generator import DailyRecapGenerator
            audio_loop.recap_generator = DailyRecapGenerator(
                base_dir=data_dir,
                memory_engine=getattr(audio_loop, 'memory_engine', None)
            )
        except Exception as e:
            print(f"[RECAP] Warning: Could not initialize DailyRecapGenerator in audio_loop: {e}")
        
        # PHASE D: Set kg_engine for knowledge graph and entity linking
        try:
            from backend.ai.user_knowledge_graph import UserKnowledgeGraph
            audio_loop.kg_engine = UserKnowledgeGraph(
                base_dir=data_dir,
                memory_engine=getattr(audio_loop, 'memory_engine', None)
            )
            # Also link KG to memory engine for auto-extraction
            if getattr(audio_loop, 'memory_engine', None):
                audio_loop.memory_engine.kg_engine = audio_loop.kg_engine
        except Exception as e:
            print(f"[KG] Warning: Could not initialize UserKnowledgeGraph in audio_loop: {e}")
        
        # PHASE E: Set adaptive_retriever for multi-source query routing
        try:
            from backend.ai.adaptive_retriever import AdaptiveRetriever
            audio_loop.adaptive_retriever = AdaptiveRetriever(
                base_dir=data_dir,
                memory_engine=getattr(audio_loop, 'memory_engine', None),
                kg_engine=getattr(audio_loop, 'kg_engine', None),
                calendar_manager=calendar_manager,
            )
        except Exception as e:
            print(f"[RETRIEVER] Warning: Could not initialize AdaptiveRetriever in audio_loop: {e}")
        
        try:
            audio_loop.note_user_activity("start_audio")
        except Exception:
            pass

        # Apply current permissions
        audio_loop.update_permissions(SETTINGS["tool_permissions"])
        
        # Check initial mute state
        if data and data.get('muted', False):
            print("[SYSTEM NOTIFICATION] Starting with Audio Paused")
            audio_loop.set_paused(True)

        print("[SYSTEM NOTIFICATION] Creating asyncio task for AudioLoop.run()")
        loop_task = asyncio.create_task(audio_loop.run())
        
        # Add a done callback to catch silent failures in the loop
        def handle_loop_exit(task):
            try:
                task.result()
            except asyncio.CancelledError:
                print("[SYSTEM NOTIFICATION] Audio Loop Cancelled")
            except Exception as e:
                print(f"[SYSTEM ERROR] Audio Loop Crashed: {e}. Attempting restart...")
                _schedule_emit_to_frontend('status', {'msg': 'Connection lost. Reconnecting...'})
                
                async def restart_session():
                    await asyncio.sleep(2)
                    # Use global params to ensure we have the latest valid config
                    if last_start_params.get('sid'):
                        print("[SERVER] Triggering auto-restart...")
                        await start_audio(last_start_params['sid'], last_start_params.get('data'))
                
                asyncio.create_task(restart_session())
        
        loop_task.add_done_callback(handle_loop_exit)
        
        print("[SYSTEM NOTIFICATION] MonikAI Started")
        await sio.emit('status', {'msg': 'MonikAI Started'}, room=sid)
        
    except Exception as e:
        print(f"[SYSTEM ERROR] CRITICAL ERROR STARTING MonikAI: {e}")
        import traceback
        traceback.print_exc()
        await sio.emit('error', {'msg': f"Failed to start: {str(e)}"}, room=sid)
        audio_loop = None # Ensure we can try again

@sio.event
async def stop_audio(sid):
    global audio_loop
    if audio_loop:
        audio_loop.stop() 
        print("[SYSTEM NOTIFICATION] Stopping Audio Loop")
    # Ensure background task is fully stopped to avoid duplicate sessions
    global loop_task
    if loop_task and not loop_task.done():
        try:
            loop_task.cancel()
            await loop_task
        except Exception:
            pass
        loop_task = None
    audio_loop = None
    print("[SYSTEM NOTIFICATION] MonikAI Stopped")
    await sio.emit('status', {'msg': 'MonikAI Stopped'}, room=sid)

@sio.event
async def pause_audio(sid):
    global audio_loop
    if audio_loop:
        audio_loop.set_paused(True)
        print("[SYSTEM NOTIFICATION] Audio Paused")
        await sio.emit('status', {'msg': 'Audio Paused'}, room=sid)

@sio.event
async def resume_audio(sid):
    global audio_loop
    if audio_loop:
        audio_loop.set_paused(False)
        print("[SYSTEM NOTIFICATION] Audio Resumed")
        await sio.emit('status', {'msg': 'Audio Resumed'}, room=sid)


# --------------------------------------------------------------------------------------
# Reminders API (frontend-driven list/cancel; creation optional)
# --------------------------------------------------------------------------------------

def _serialize_reminders():
    """Return a JSON-serializable list of reminders from the active audio_loop."""
    if not reminder_manager:
        return []

    items = reminder_manager.list()
    result = []
    for r in items:
        try:
            when_dt = datetime.fromisoformat(r.when_iso)
            when_epoch_ms = int(when_dt.timestamp() * 1000)
        except Exception:
            when_epoch_ms = None
        result.append({
            'id': r.id,
            'message': r.message,
            'when_iso': r.when_iso,
            'speak': bool(r.speak),
            'when_epoch_ms': when_epoch_ms,
            'alert': bool(getattr(r, 'alert', True)),
            'created_iso': getattr(r, 'created_iso', None),
        })
    # Sort by scheduled time
    result.sort(key=lambda x: (x['when_epoch_ms'] is None, x['when_epoch_ms'] or 0))
    return result


def _serialize_kasa_devices():
    """Return a JSON-serializable list of known Kasa devices (no discovery scan)."""
    if not kasa_agent:
        return []
    return kasa_agent.serialize_devices()


# --------------------------------------------------------------------------------------
# VN Scene Switch (content-aware)
# --------------------------------------------------------------------------------------
VN_SCENE_KEYWORDS = [
    ("kitchen", [
        "gotow", "kuchar", "kuchni", "kuchnia", "obiad", "kolac", "śniad", "sniad",
        "piec", "piecz", "makaron", "przepis", "herbat", "kawa", "jedz", "jedzenie"
    ]),
    ("outside", [
        "na dworze", "na zewnątrz", "na zewnatrz", "spacer", "park", "natura", "pogod",
        "deszcz", "śnieg", "snieg", "wiatr", "słońc", "slonc", "plaż", "plaz", "las"
    ]),
    ("school", [
        "szkoł", "szkol", "uczeln", "studia", "lekcj", "egzamin", "nauka", "klasa"
    ]),
    ("room", [
        "pokój", "pokoj", "biurko", "prac", "kod", "komputer", "projekt", "pisan"
    ]),
    ("club", [
        "klub", "literatur", "wiersz", "poezj", "spotkanie"
    ]),
    ("library", [
        "bibliotek", "książk", "czyta", "lektur"
    ]),
    ("bedroom", [
        "sypialni", "łóżk", "spac", "drzemk", "noc"
    ]),
]

_vn_scene_state = {"current": None, "last_ts": 0.0}
_vn_user_buf = ""
_vn_user_last_ts = 0.0
_vn_scene_task = None


def _pick_scene_from_text(text: str):
    if not text:
        return None, None
    t = text.lower()
    for scene, keys in VN_SCENE_KEYWORDS:
        for k in keys:
            if k in t:
                return scene, k
    return None, None


async def _debounced_vn_scene_check():
    global _vn_user_buf, _vn_user_last_ts, _vn_scene_task
    await asyncio.sleep(0.8)
    if (time.time() - _vn_user_last_ts) < 0.7:
        _vn_scene_task = asyncio.create_task(_debounced_vn_scene_check())
        return

    text = (_vn_user_buf or "").strip()
    if len(text) < 6:
        return

    scene, keyword = _pick_scene_from_text(text)
    if not scene:
        return

    now = time.time()
    if _vn_scene_state["current"] == scene:
        return
    if (now - _vn_scene_state["last_ts"]) < 90:
        return

    _vn_scene_state["current"] = scene
    _vn_scene_state["last_ts"] = now
    _vn_user_buf = ""

    # Emit scene change to frontend
    try:
        asyncio.create_task(sio.emit('vn_scene', {"scene": scene, "reason": keyword, "ttl_ms": 180000}))
    except Exception:
        pass

    # Notify model so it can briefly acknowledge the change
    try:
        if audio_loop and getattr(audio_loop, "session", None):
            await audio_loop.session.send(
                input=(
                    "System Notification: Scene changed to '" + scene +
                    "' because user mentioned '" + str(keyword) +
                    "'. Briefly acknowledge the change in a natural way (1 short sentence), then continue."
                ),
                end_of_turn=False,
            )
    except Exception as e:
        print(f"[SERVER] Failed to notify model about scene change: {e}")


@sio.event
async def get_personality_status(sid):
    """Frontend requests current personality status."""
    if personality_system:
        data = asdict(personality_system.state)
        aff = max(0.0, min(100.0, float(data.get("affection", 0))))
        score = aff / 10.0
        full = int(score)
        hearts = "❤️" * full + "🤍" * (10 - full)
        data["affection_hearts"] = f"{hearts} ({score:.1f}/10)"
        await sio.emit('personality_status', data, room=sid)

import json
from datetime import datetime
from pathlib import Path

# ... (imports)

@sio.event
async def video_frame(sid, data):
    # data should contain 'image' which is binary (blob) or base64 encoded
    image_data = data.get('image')
    if image_data and audio_loop:
        # We don't await this because we don't want to block the socket handler
        # But send_frame is async, so we create a task
        asyncio.create_task(audio_loop.send_frame(image_data))


@sio.event
async def user_activity(sid, data):
    try:
        text = (data or {}).get("text") or ""
        audio_loop_mark_user_activity(audio_loop, text)
    except Exception:
        pass

def _notes_path():
    try:
        base = DATA_DIR / "memory" / "pages"
        base.mkdir(parents=True, exist_ok=True)
        return base / "notes.md"
    except Exception:
        return DATA_DIR / "memory" / "pages" / "notes.md"

def _read_notes_text():
    path = _notes_path()
    try:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"[ERROR] Failed to read notes: {e}"

def _write_notes_text(content: str):
    path = _notes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or "", encoding="utf-8")
    return path

def _append_notes_text(content: str):
    path = _notes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8", errors="ignore")
    addition = content or ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    new_text = existing + addition + ("\n" if addition and not addition.endswith("\n") else "")
    path.write_text(new_text, encoding="utf-8")
    return path

def _journal_today_path():
    date_key = datetime.now().strftime("%Y-%m-%d")
    base = DATA_DIR / "memory" / "pages" / "journal"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{date_key}.md", date_key

def _read_journal_today():
    path, date_key = _journal_today_path()
    try:
        if not path.exists():
            return "", date_key
        return path.read_text(encoding="utf-8", errors="ignore"), date_key
    except Exception:
        return "", date_key

def _resolve_memory_page(path: str) -> Path:
    base = DATA_DIR / "memory" / "pages"
    base.mkdir(parents=True, exist_ok=True)
    if not path:
        path = "notes.md"
    p = Path(path)
    if not p.is_absolute():
        p = (base / path).resolve()
    if base not in p.parents and p != base:
        raise ValueError("Path outside memory pages.")
    return p

def _list_memory_pages() -> list[dict]:
    base = DATA_DIR / "memory" / "pages"
    base.mkdir(parents=True, exist_ok=True)
    pages = []

    def _extract_title(path: Path) -> str:
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for _ in range(40):
                    line = f.readline()
                    if not line:
                        break
                    text = line.strip()
                    if not text:
                        continue
                    if text.startswith("#"):
                        cleaned = text.lstrip("#").strip()
                        if cleaned:
                            return cleaned[:120]
                    return text[:120]
        except Exception:
            pass
        return path.stem

    for p in base.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(base).as_posix()
        except Exception:
            rel = str(p).replace("\\", "/")
        category = rel.split("/")[0] if "/" in rel else "root"
        pages.append({
            "path": rel,
            "title": _extract_title(p),
            "category": category,
        })
    pages.sort(key=lambda x: (x.get("title", "").lower(), x.get("path", "")))
    return pages

@sio.event
async def discover_kasa(sid):
    print(f"Received discover_kasa request")
    try:
        devices = await kasa_agent.discover_devices()
        await sio.emit('kasa_devices', devices, room=sid)
        await sio.emit('status', {'msg': f"Found {len(devices)} Kasa devices"}, room=sid)
        
        # Save to settings
        # devices is a list of full device info dicts. minimizing for storage.
        saved_devices = []
        for d in devices:
            saved_devices.append({
                "ip": d["ip"],
                "alias": d["alias"],
                "model": d["model"]
            })
        
        # Save to new smart_home.kasa.devices structure
        if "smart_home" not in SETTINGS:
            SETTINGS["smart_home"] = {}
        if "kasa" not in SETTINGS["smart_home"]:
            SETTINGS["smart_home"]["kasa"] = {}
        SETTINGS["smart_home"]["kasa"]["devices"] = saved_devices
        save_settings()
        print(f"[SERVER] Saved {len(saved_devices)} Kasa devices to settings (smart_home.kasa.devices).")
        
    except Exception as e:
        print(f"Error discovering kasa: {e}")
        await sio.emit('error', {'msg': f"Kasa Discovery Failed: {str(e)}"}, room=sid)


@sio.event
async def list_kasa(sid, data=None):
    """Return cached/known Kasa devices without discovery scan."""
    await sio.emit('kasa_devices', _serialize_kasa_devices(), room=sid)

@sio.event
async def prompt_web_agent(sid, data):
    # data: { prompt: "find xyz" }
    prompt = data.get('prompt')
    print(f"Received web agent prompt: '{prompt}'")

    try:
        if not audio_loop or not getattr(audio_loop, "web_agent", None):
            await sio.emit('error', {'msg': "Monika OpenClaw fork is not available"}, room=sid)
            return

        await sio.emit('status', {'msg': 'Monika OpenClaw fork running...'}, room=sid)

        await audio_loop.handle_openclaw_agent_request(prompt)
        
        await sio.emit('status', {'msg': 'Monika OpenClaw fork finished'}, room=sid)
        
    except Exception as e:
        print(f"Error running Monika OpenClaw fork: {e}")
        await sio.emit('error', {'msg': f"Monika OpenClaw fork error: {str(e)}"}, room=sid)


@sio.event
async def control_agent_job(sid, data):
    action = str((data or {}).get("action") or "").strip().lower()
    job_id = (data or {}).get("job_id")
    if not audio_loop:
        await sio.emit('error', {'msg': "Agent loop not active"}, room=sid)
        return

    try:
        if action == "start":
            prompt = str((data or {}).get("prompt") or "").strip()
            if not prompt:
                await sio.emit('agent_job_status', {"ok": False, "error": "prompt required for action=start"}, room=sid)
                return
            provider = str((data or {}).get("provider") or "openclaw").strip().lower() or "openclaw"
            agent = (data or {}).get("agent")
            thinking = (data or {}).get("thinking")
            timeout_sec = (data or {}).get("timeout_sec")
            new_job_id = audio_loop.start_agent_job(
                prompt=prompt,
                provider=provider,
                agent=agent,
                thinking=thinking,
                timeout_sec=timeout_sec,
            )
            await sio.emit('agent_job_status', {"ok": True, "job_id": new_job_id, "status": "queued"}, room=sid)
        elif action == "status":
            status_obj = audio_loop.get_agent_job_status(job_id)
            await sio.emit('agent_job_status', status_obj, room=sid)
        elif action == "list":
            status_obj = audio_loop.get_agent_job_status(None)
            await sio.emit('agent_job_status', status_obj, room=sid)
        elif action == "stop":
            result = await audio_loop.stop_agent_job(job_id)
            await sio.emit('agent_job_status', result, room=sid)
        elif action == "resume":
            result = await audio_loop.resume_agent_job(job_id)
            await sio.emit('agent_job_status', result, room=sid)
        else:
            await sio.emit('agent_job_status', {"ok": False, "error": "unknown action"}, room=sid)
    except Exception as e:
        await sio.emit('agent_job_status', {"ok": False, "error": str(e)}, room=sid)


def _skills_manager():
    if not audio_loop:
        return None
    return getattr(audio_loop, "skills_manager", None) or getattr(audio_loop, "openclaw_skills", None)


async def _emit_skills_payload(sid, payload):
    await sio.emit('skills', payload, room=sid)
    await sio.emit('openclaw_skills', payload, room=sid)


async def _emit_skill_install_result(sid, payload):
    await sio.emit('skill_install_result', payload, room=sid)
    await sio.emit('openclaw_skill_install_result', payload, room=sid)


async def _emit_skill_uninstall_result(sid, payload):
    await sio.emit('skill_uninstall_result', payload, room=sid)
    await sio.emit('openclaw_skill_uninstall_result', payload, room=sid)


async def _list_skills_impl(sid, data=None):
    include_ineligible = bool((data or {}).get("include_ineligible", False))
    include_disabled = bool((data or {}).get("include_disabled", False))
    manager = _skills_manager()
    if not manager:
        payload = {
            "count": 0,
            "skills": [],
            "error": "Skills manager unavailable",
        }
    else:
        skills = manager.list_skills(
            include_ineligible=include_ineligible,
            include_disabled=include_disabled,
        )
        payload = {"count": len(skills), "skills": skills}
    await _emit_skills_payload(sid, payload)


@sio.event
async def list_openclaw_skills(sid, data=None):
    await _list_skills_impl(sid, data)


@sio.on('list_skills')
async def list_skills(sid, data=None):
    await _list_skills_impl(sid, data)


async def _refresh_skills_impl(sid, data=None):
    include_ineligible = bool((data or {}).get("include_ineligible", True))
    include_disabled = bool((data or {}).get("include_disabled", True))
    manager = _skills_manager()
    if not manager:
        payload = {
            "count": 0,
            "skills": [],
            "error": "Skills manager unavailable",
        }
    else:
        _ = manager.refresh()
        skills = manager.list_skills(
            include_ineligible=include_ineligible,
            include_disabled=include_disabled,
        )
        payload = {"count": len(skills), "skills": skills}
    await _emit_skills_payload(sid, payload)


@sio.event
async def refresh_openclaw_skills(sid, data=None):
    await _refresh_skills_impl(sid, data)


@sio.on('refresh_skills')
async def refresh_skills(sid, data=None):
    await _refresh_skills_impl(sid, data)


async def _install_skill_zip_impl(sid, data=None):
    filename = str((data or {}).get("filename") or "skill.zip").strip() or "skill.zip"
    zip_b64 = (data or {}).get("zip_b64") or ""
    replace = bool((data or {}).get("replace", True))

    manager = _skills_manager()
    if not manager:
        await _emit_skill_install_result(sid, {
            "ok": False,
            "error": "Skills manager unavailable",
        })
        return

    if not zip_b64:
        await _emit_skill_install_result(sid, {
            "ok": False,
            "error": "Missing zip_b64 payload",
        })
        return

    try:
        raw_zip = base64.b64decode(str(zip_b64), validate=False)
    except Exception as e:
        await _emit_skill_install_result(sid, {
            "ok": False,
            "error": f"Invalid base64 ZIP payload: {e}",
        })
        return

    try:
        result = manager.install_from_zip_bytes(
            raw_zip,
            filename=filename,
            replace=replace,
        )
        skills = manager.list_skills(
            include_ineligible=True,
            include_disabled=True,
        )
        await _emit_skill_install_result(sid, {
            "ok": True,
            "result": result,
        })
        await _emit_skills_payload(sid, {"count": len(skills), "skills": skills})
    except Exception as e:
        await _emit_skill_install_result(sid, {
            "ok": False,
            "error": str(e),
        })


@sio.event
async def install_openclaw_skill_zip(sid, data=None):
    await _install_skill_zip_impl(sid, data)


@sio.on('install_skill_zip')
async def install_skill_zip(sid, data=None):
    await _install_skill_zip_impl(sid, data)


async def _install_skill_source_impl(sid, data=None):
    source = str((data or {}).get("source") or "").strip()
    raw_skill_name = (data or {}).get("skill_name")
    raw_skill_names = (data or {}).get("skill_names")
    agent = str((data or {}).get("agent") or "codex").strip() or "codex"
    global_scope = bool((data or {}).get("global_scope", False))
    copy_files = bool((data or {}).get("copy_files", True))

    manager = _skills_manager()
    if not manager:
        await _emit_skill_install_result(sid, {
            "ok": False,
            "error": "Skills manager unavailable",
        })
        return

    if not source:
        await _emit_skill_install_result(sid, {
            "ok": False,
            "error": "source is required",
        })
        return

    skill_names = []
    if isinstance(raw_skill_names, list):
        skill_names.extend(str(item or "").strip() for item in raw_skill_names)
    elif isinstance(raw_skill_names, str) and raw_skill_names.strip():
        skill_names.extend(part.strip() for part in raw_skill_names.split(","))
    if raw_skill_name:
        skill_names.append(str(raw_skill_name).strip())
    skill_names = [name for name in skill_names if name]

    try:
        result = manager.install_from_source(
            source,
            skill_names=skill_names,
            agent=agent,
            global_scope=global_scope,
            copy_files=copy_files,
            yes=True,
        )
        skills = manager.list_skills(
            include_ineligible=True,
            include_disabled=True,
        )
        await _emit_skill_install_result(sid, {
            "ok": True,
            "result": result,
        })
        await _emit_skills_payload(sid, {"count": len(skills), "skills": skills})
    except Exception as e:
        await _emit_skill_install_result(sid, {
            "ok": False,
            "error": str(e),
        })


@sio.event
async def install_openclaw_skill_source(sid, data=None):
    await _install_skill_source_impl(sid, data)


@sio.on('install_skill_source')
async def install_skill_source(sid, data=None):
    await _install_skill_source_impl(sid, data)


async def _uninstall_skill_impl(sid, data=None):
    name = str((data or {}).get("name") or "").strip()
    if not name:
        await _emit_skill_uninstall_result(sid, {
            "ok": False,
            "error": "name is required",
        })
        return

    manager = _skills_manager()
    if not manager:
        await _emit_skill_uninstall_result(sid, {
            "ok": False,
            "error": "Skills manager unavailable",
        })
        return

    try:
        result = manager.uninstall_skill(name)
        skills = manager.list_skills(
            include_ineligible=True,
            include_disabled=True,
        )
        await _emit_skill_uninstall_result(sid, {
            "ok": True,
            "result": result,
        })
        await _emit_skills_payload(sid, {"count": len(skills), "skills": skills})
    except Exception as e:
        await _emit_skill_uninstall_result(sid, {
            "ok": False,
            "error": str(e),
        })


@sio.event
async def uninstall_openclaw_skill(sid, data=None):
    await _uninstall_skill_impl(sid, data)


@sio.on('uninstall_skill')
async def uninstall_skill(sid, data=None):
    await _uninstall_skill_impl(sid, data)


@sio.event
async def spotify_get_status(sid, data=None):
    _ = data
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
    # data: { ip, action: "on"|"off"|"brightness"|"color", value: ... }
    ip = data.get('ip')
    action = data.get('action')
    print(f"Kasa Control: {ip} -> {action}")
    
    try:
        success = False
        if action == "on":
            success = await kasa_agent.turn_on(ip)
        elif action == "off":
            success = await kasa_agent.turn_off(ip)
        elif action == "brightness":
            val = data.get('value')
            success = await kasa_agent.set_brightness(ip, val)
        elif action == "color":
            # value is {h, s, v} - convert to tuple for set_color
            h = data.get('value', {}).get('h', 0)
            s = data.get('value', {}).get('s', 100)
            v = data.get('value', {}).get('v', 100)
            success = await kasa_agent.set_color(ip, (h, s, v))
        
        if success:
            await sio.emit('kasa_update', {
                'ip': ip,
                'is_on': True if action == "on" else (False if action == "off" else None),
                'brightness': data.get('value') if action == "brightness" else None,
            }, room=sid)
 
        else:
             await sio.emit('error', {'msg': f"Failed to control device {ip}"}, room=sid)

    except Exception as e:
         print(f"Error controlling kasa: {e}")
         await sio.emit('error', {'msg': f"Kasa Control Error: {str(e)}"}, room=sid)

@sio.event
async def get_settings(sid):
    await sio.emit('settings', SETTINGS, room=sid)

@sio.event
async def update_settings(sid, data):
    # Generic update
    print(f"Updating settings: {data}")
    
    # Handle specific keys if needed
    if "tool_permissions" in data:
        SETTINGS["tool_permissions"].update(data["tool_permissions"])
        if audio_loop:
            audio_loop.update_permissions(SETTINGS["tool_permissions"])
            
    if "show_internal_thoughts" in data:
        SETTINGS["show_internal_thoughts"] = bool(data["show_internal_thoughts"])
            
    if "face_auth_enabled" in data:
        SETTINGS["face_auth_enabled"] = data["face_auth_enabled"]
        # If turned OFF, maybe emit auth status true?
        if not data["face_auth_enabled"]:
             await sio.emit('auth_status', {'authenticated': True}, room=sid)
             # Stop auth loop if running?
             if authenticator:
                 authenticator.stop() 

    if "camera_flipped" in data:
        SETTINGS["camera_flipped"] = data["camera_flipped"]
        print(f"[SERVER] Camera flip set to: {data['camera_flipped']}")

    if "camera_source" in data:
        SETTINGS["camera_source"] = data["camera_source"]
        if audio_loop and hasattr(audio_loop, "reload_capture_settings"):
            try:
                audio_loop.reload_capture_settings()
            except Exception:
                pass

    if "video_mode" in data:
        SETTINGS["video_mode"] = data["video_mode"]
        mode = str(SETTINGS["video_mode"]).lower()
        if mode == "screen":
            SETTINGS.setdefault("screen_capture", {})["stream_to_ai"] = True
        else:
            SETTINGS.setdefault("screen_capture", {})["stream_to_ai"] = False
        if audio_loop and hasattr(audio_loop, "set_video_mode"):
            try:
                audio_loop.set_video_mode(SETTINGS["video_mode"])
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
        SETTINGS.setdefault("camera_capture", {}).update(data["camera_capture"])
        if audio_loop and hasattr(audio_loop, "reload_capture_settings"):
            try:
                audio_loop.reload_capture_settings()
            except Exception:
                pass

    if "screen_capture" in data and isinstance(data.get("screen_capture"), dict):
        SETTINGS.setdefault("screen_capture", {}).update(data["screen_capture"])
        if audio_loop and hasattr(audio_loop, "reload_capture_settings"):
            try:
                audio_loop.reload_capture_settings()
            except Exception:
                pass

    if "daily_briefing" in data and isinstance(data.get("daily_briefing"), dict):
        incoming = data["daily_briefing"]
        SETTINGS.setdefault("daily_briefing", {})
        for k, v in incoming.items():
            if k == "profile" and isinstance(v, dict):
                DAILY_BRIEFING_RUNTIME.set_profile(v)
            else:
                SETTINGS["daily_briefing"][k] = v
        DAILY_BRIEFING_RUNTIME.invalidate_cache()

    save_settings()
    # Broadcast new full settings
    await _emit_to_frontend('settings', SETTINGS)


# Deprecated/Mapped for compatibility if frontend still uses specific events
@sio.event
async def get_tool_permissions(sid):
    await sio.emit('tool_permissions', SETTINGS["tool_permissions"], room=sid)

@sio.event
async def report_visual_state(sid, data):
    """Frontend reports current visual state (location/outfit) for AI context."""
    if personality_system:
        loc = data.get("location")
        outfit = data.get("outfit")

        # Enforce canon: when Monika is outside, she wears her school uniform.
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
async def update_tool_permissions(sid, data):
    print(f"Updating permissions (legacy event): {data}")
    SETTINGS["tool_permissions"].update(data)
    save_settings()
    
    if audio_loop:
        audio_loop.update_permissions(SETTINGS["tool_permissions"])
    # Broadcast update to all
    await _emit_to_frontend('tool_permissions', SETTINGS["tool_permissions"])


@sio.event
async def kill_server(sid, data=None):
    """Kill the server when quit button is clicked."""
    print("[SERVER] Kill server requested from frontend")
    asyncio.create_task(_shutdown_and_exit("[SERVER] Kill server requested from frontend."))
    await asyncio.sleep(0.1)


@sio.event
async def calendar_get_events(sid, data=None):
    """Frontend requests upcoming calendar events."""
    try:
        if not calendar_manager:
            result = {'events': [], 'error': 'Calendar not available'}
            await sio.emit('error', {'msg': 'Calendar not available'}, room=sid)
            return result
        
        events = calendar_manager.get_all_events()
        events_list = [
            {
                'id': e.id,
                'summary': e.summary,
                'start_iso': e.start_iso,
                'end_iso': e.end_iso,
                'description': e.description or '',
                'is_birthday': getattr(e, 'is_birthday', False)
            }
            for e in events
        ]
        
        # Sort by start time
        events_list.sort(key=lambda x: x['start_iso'])
        
        print(f"[SERVER] Sending {len(events_list)} calendar events to frontend")
        
        result = {'events': events_list}
        await sio.emit('calendar_events', result, room=sid)
        return result
    except Exception as e:
        print(f"[SERVER] Error in calendar_get_events: {e}")
        result = {'events': [], 'error': str(e)}
        await sio.emit('error', {'msg': f"Failed to get calendar events: {e}"}, room=sid)
        return result


@sio.event
async def calendar_get_birthdays(sid, data=None):
    """Frontend requests birthday entries from profile.md."""
    try:
        birthdays = []
        
        # Read from profile.md in long_term_memory
        profile_path = DATA_DIR / "long_term_memory" / "profile.md"
        if profile_path.exists():
            import re
            content = profile_path.read_text(encoding='utf-8', errors='ignore')
            
            # Look for birthday field in markdown (e.g., "Birthday: 1990-01-15")
            birth_match = re.search(r'(?:Birthday|Birthdate|DOB)[:\s]+(\d{4}-\d{2}-\d{2}|[A-Za-z]+ \d{1,2},? \d{4})', content)
            if birth_match:
                birthdays.append({
                    'date': birth_match.group(1),
                    'label': 'Your Birthday'
                })
        
        # Also check profile.json if it exists
        profile_json_path = DATA_DIR / "long_term_memory" / "profile_meta.json"
        if profile_json_path.exists():
            try:
                import json
                profile_data = json.loads(profile_json_path.read_text())
                if profile_data.get('birthday'):
                    birthdays.append({
                        'date': profile_data['birthday'],
                        'label': 'Your Birthday'
                    })
            except:
                pass
        
        print(f"[SERVER] Sending {len(birthdays)} birthdays to frontend")
        
        result = {'birthdays': birthdays}
        await sio.emit('calendar_birthdays', result, room=sid)
        return result
    except Exception as e:
        print(f"[SERVER] Error in calendar_get_birthdays: {e}")
        result = {'birthdays': [], 'error': str(e)}
        await sio.emit('error', {'msg': f"Failed to get birthdays: {e}"}, room=sid)
        return result


@sio.event
async def memory_get_profile(sid, data=None):
    """Frontend requests to load user profile."""
    try:
        profile = {
            'user_name': '',
            'gender': '',
            'birthday': '',
            'location': '',
            'occupation': '',
            'interests': '',
            'personality_traits': ''
        }
        
        # Try to load from profile_meta.json
        profile_meta_path = DATA_DIR / "long_term_memory" / "profile_meta.json"
        if profile_meta_path.exists():
            try:
                import json
                profile_data = json.loads(profile_meta_path.read_text())
                profile.update({
                    'user_name': profile_data.get('user_name', ''),
                    'gender': profile_data.get('gender', ''),
                    'birthday': profile_data.get('birthday', ''),
                    'location': profile_data.get('location', ''),
                    'occupation': profile_data.get('occupation', ''),
                    'interests': profile_data.get('interests', ''),
                    'personality_traits': profile_data.get('personality_traits', '')
                })
            except:
                pass
        
        print(f"[SERVER] Sending user profile to frontend")
        
        result = {'profile': profile}
        await sio.emit('memory_profile', result, room=sid)
        return result
    except Exception as e:
        print(f"[SERVER] Error in memory_get_profile: {e}")
        result = {'profile': {}, 'error': str(e)}
        await sio.emit('error', {'msg': f"Failed to get profile: {e}"}, room=sid)
        return result


@sio.event
async def memory_update_profile(sid, data):
    """Frontend submits updated user profile."""
    try:
        profile = data.get('profile', {}) if isinstance(data, dict) else {}
        
        if not profile:
            result = {'success': False, 'error': 'No profile data provided'}
            await sio.emit('error', {'msg': 'No profile data provided'}, room=sid)
            return result
        
        # Ensure directory exists
        profile_meta_path = DATA_DIR / "long_term_memory" / "profile_meta.json"
        profile_meta_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save to profile_meta.json
        import json
        profile_data = {
            'user_name': profile.get('user_name', '').strip(),
            'gender': profile.get('gender', '').strip(),
            'birthday': profile.get('birthday', '').strip(),
            'location': profile.get('location', '').strip(),
            'occupation': profile.get('occupation', '').strip(),
            'interests': profile.get('interests', '').strip(),
            'personality_traits': profile.get('personality_traits', '').strip(),
            'updated_at': datetime.now().isoformat()
        }
        
        profile_meta_path.write_text(json.dumps(profile_data, indent=2, ensure_ascii=False), encoding='utf-8')
        
        # Also update profile.md with basic info
        profile_md_path = DATA_DIR / "long_term_memory" / "profile.md"
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
        profile_md_path.write_text(md_content, encoding='utf-8')
        
        print(f"[SERVER] User profile updated: {profile_data['user_name']}")
        
        # Notify the model if session is active
        if audio_loop and audio_loop.session:
            try:
                msg = f"System Notification: User profile was updated: Name={profile_data['user_name']}, Gender={profile_data['gender']}, Birthday={profile_data['birthday']}, Location={profile_data['location']}, Occupation={profile_data['occupation']}."
                if hasattr(audio_loop, "send_system_message"):
                    await audio_loop.send_system_message(msg, end_of_turn=False)
                else:
                    await audio_loop.session.send(input=msg, end_of_turn=False)
            except Exception as e:
                print(f"[SERVER] Failed to notify model about profile update: {e}")
        
        result = {'success': True, 'profile': profile_data}
        await sio.emit('memory_profile', result, room=sid)
        await sio.emit('status', {'msg': 'Profile saved successfully'}, room=sid)
        return result
    except Exception as e:
        print(f"[SERVER] Error in memory_update_profile: {e}")
        result = {'success': False, 'error': str(e)}
        await sio.emit('error', {'msg': f"Failed to update profile: {e}"}, room=sid)
        return result


if __name__ == "__main__":
    uvicorn.run(
        app_socketio,
        host="127.0.0.1", 
        port=8000, 
        reload=False, # Reload enabled causes spawn of worker which might miss the event loop policy patch
        loop="asyncio",
        reload_excludes=["output.stl", "*.stl"]
    )
def audio_loop_mark_user_activity(loop, text: str):
    """Prefer AudioLoop.mark_user_activity(text) if available; fall back to legacy names."""
    if loop is None:
        return
    for fn_name in ("mark_user_activity", "note_user_activity", "note_user_activity_ts"):
        if _loop_has(loop, fn_name):
            try:
                getattr(loop, fn_name)(text)
                return
            except Exception:
                return
    # Best-effort: update timestamp fields if present
    try:
        if hasattr(loop, "_last_user_activity_ts"):
            setattr(loop, "_last_user_activity_ts", asyncio.get_event_loop().time())
    except Exception:
        pass
