import asyncio
from contextlib import asynccontextmanager
import sys
import json
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
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ..integrations.media.study_reader import StudyReader
from ..integrations.media.study_ocr import ocr_image_bytes

from . import monikai
from .config import DATA_DIR as CONFIG_DATA_DIR
from .runtimes.daily_briefing_runtime import DailyBriefingRuntime
from .handlers.calendar_reminder_handlers import register_calendar_reminder_handlers
from .handlers.chat_input_handlers import register_chat_input_handlers
from .handlers.control_handlers import register_control_handlers
from .handlers.daily_briefing_handlers import register_daily_briefing_handlers
from .handlers.audio_lifecycle_handlers import register_audio_lifecycle_handlers
from .handlers.memory_page_handlers import register_memory_page_handlers
from .handlers.notes_journal_handlers import register_notes_journal_handlers
from .handlers.openclaw_skill_handlers import register_openclaw_skill_handlers
from .routers.progression_http_router import register_progression_http_routes
from .handlers.settings_profile_handlers import register_settings_profile_handlers
from .handlers.session_mode_handlers import register_session_mode_handlers
from .handlers.shared_activity_handlers import register_shared_activity_handlers
from .routers.frontend_router import (
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
from .lifecycle_discord import start_discord_service, stop_discord_service
from .runtimes.minecraft_autonomy_runtime import (
    build_minecraft_autonomy_cfg,
    run_minecraft_autonomy_loop,
    set_minecraft_game_mode as set_minecraft_game_mode_runtime,
)
from .routers.minecraft_http_router import register_minecraft_http_routes
from .runtimes.minecraft_perception_runtime import register_minecraft_perception_callback
from .handlers.minecraft_socket_handlers import register_minecraft_socket_handlers
from .runtimes.screen_ocr_runtime import ScreenOcrRuntime
from .settings_store import DEFAULT_SETTINGS, SETTINGS, load_settings, save_settings
from .runtime_serializers import serialize_reminders
from .storage_activity_helpers import (
    append_notes_text,
    audio_loop_mark_user_activity,
    journal_today_path,
    list_memory_pages,
    read_journal_today,
    read_notes_text,
    resolve_memory_page,
    write_notes_text,
)
from .handlers.system_frontend_handlers import register_system_frontend_handlers
from .routers.system_http_router import register_system_http_routes
from .routers.study_http_router import register_study_http_routes
from .handlers.study_socket_handlers import register_study_socket_handlers
from .runtimes.vn_scene_runtime import VnSceneRuntime
from backend.services.daily_briefing import DEFAULT_SECTIONS
from ..agents.kasa_agent import KasaAgent
from ..vn.activity_runtime import SharedActivityRuntime
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
        serialize_reminders=lambda: serialize_reminders(reminder_manager),
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

    global discord_service, discord_task
    discord_service, discord_task = start_discord_service(
        lambda: SETTINGS,
        calendar_manager=calendar_manager,
        reminder_manager=reminder_manager,
        spotify_manager=spotify_manager,
        personality=personality_system,
    )

    # v2 Soul Engine — initialize db + personality + discovery engines.
    from backend.core.runtimes import v2_runtime as _v2
    try:
        await _v2.initialize()
        if not _v2.get():
            raise RuntimeError("V2Runtime singleton is None after initialization")
        print("[SERVER] v2 Soul Engine initialized successfully.")
    except Exception as e:
        print(f"[CRITICAL] Failed to initialize MonikAI v2 runtime: {e}")
        raise RuntimeError(f"MonikAI v2 runtime failed to initialize: {e}") from e

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

        discord_service, discord_task = await stop_discord_service(
            discord_service,
            discord_task,
        )

        try:
            from backend.core.runtimes import v2_runtime as _v2
            await _v2.shutdown()
        except Exception:
            pass

# Create a Socket.IO server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*', max_http_buffer_size=25 * 1024 * 1024)
register_socketio(sio)
app = FastAPI(lifespan=lifespan)

register_minecraft_http_routes(
    app,
    get_minecraft_bot_manager=lambda: minecraft_bot_manager,
)

register_progression_http_routes(
    app,
    get_main_loop=lambda: MAIN_LOOP,
)

register_system_http_routes(
    app,
    get_spotify_manager=lambda: spotify_manager,
    emit_to_frontend=_emit_to_frontend,
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
discord_service = None
discord_task = None
DAILY_BRIEFING_RUNTIME = DailyBriefingRuntime(
    SETTINGS,
    get_audio_loop=lambda: audio_loop,
    get_personality_system=lambda: personality_system,
)


def _get_audio_loop():
    return audio_loop


def _set_audio_loop(value):
    global audio_loop
    audio_loop = value


def _get_loop_task():
    return loop_task


def _set_loop_task(value):
    global loop_task
    loop_task = value


def _get_authenticator():
    return authenticator


def _set_authenticator(value):
    global authenticator
    authenticator = value


def _get_calendar_manager():
    return calendar_manager


def _get_reminder_manager():
    return reminder_manager


def _get_spotify_manager():
    return spotify_manager


def _get_personality_system():
    return personality_system


def _get_hue_agent():
    return hue_agent


def _get_home_assistant_agent():
    return home_assistant_agent


def _get_minecraft_bot_manager():
    return minecraft_bot_manager


register_settings_profile_handlers(
    sio,
    get_settings_fn=lambda: SETTINGS,
    save_settings=save_settings,
    get_audio_loop=lambda: audio_loop,
    get_personality_system=lambda: personality_system,
    get_calendar_manager=lambda: calendar_manager,
    get_authenticator=lambda: authenticator,
    emit_to_frontend=_emit_to_frontend,
    data_dir=DATA_DIR,
    daily_briefing_runtime=DAILY_BRIEFING_RUNTIME,
)

register_system_frontend_handlers(
    sio,
    get_audio_loop=_get_audio_loop,
    get_personality_system=_get_personality_system,
    get_kasa_agent=lambda: kasa_agent,
    get_spotify_manager=_get_spotify_manager,
    get_settings=lambda: SETTINGS,
    save_settings=save_settings,
    shutdown_and_exit=_shutdown_and_exit,
    mark_user_activity=lambda loop, text: audio_loop_mark_user_activity(loop, text),
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
    serialize_reminders=lambda: serialize_reminders(reminder_manager),
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
    get_shared_activity_runtime=lambda: SHARED_ACTIVITY_RUNTIME,
)

VN_SCENE_RUNTIME = VnSceneRuntime(
    sio=sio,
    get_audio_loop=lambda: audio_loop,
)

SHARED_ACTIVITY_RUNTIME = SharedActivityRuntime(
    db_path=DATA_DIR / "monika.db",
)

register_audio_lifecycle_handlers(
    sio,
    get_settings=lambda: SETTINGS,
    get_audio_loop=_get_audio_loop,
    set_audio_loop=_set_audio_loop,
    get_loop_task=_get_loop_task,
    set_loop_task=_set_loop_task,
    get_authenticator=_get_authenticator,
    set_authenticator=_set_authenticator,
    set_active_frontend_sid=set_active_frontend_sid,
    clear_active_frontend_sid=clear_active_frontend_sid,
    schedule_emit_to_frontend=_schedule_emit_to_frontend,
    emit_to_frontend=_emit_to_frontend,
    serialize_reminders=lambda: serialize_reminders(reminder_manager),
    screen_ocr_runtime=SCREEN_OCR_RUNTIME,
    vn_scene_runtime=VN_SCENE_RUNTIME,
    data_dir=DATA_DIR,
    monikai_module=monikai,
    kasa_agent=kasa_agent,
    get_calendar_manager=_get_calendar_manager,
    get_reminder_manager=_get_reminder_manager,
    get_spotify_manager=_get_spotify_manager,
    get_personality_system=_get_personality_system,
    get_hue_agent=_get_hue_agent,
    get_home_assistant_agent=_get_home_assistant_agent,
    get_minecraft_bot_manager=_get_minecraft_bot_manager,
)


register_chat_input_handlers(
    sio,
    get_audio_loop=lambda: audio_loop,
    emit_to_frontend=_emit_to_frontend,
    audio_loop_mark_user_activity=lambda loop, text: audio_loop_mark_user_activity(loop, text),
    get_vn_user_buf=VN_SCENE_RUNTIME.get_user_buf,
    set_vn_user_buf=VN_SCENE_RUNTIME.set_user_buf,
    set_vn_user_last_ts=VN_SCENE_RUNTIME.set_user_last_ts,
    get_vn_scene_task=VN_SCENE_RUNTIME.get_scene_task,
    set_vn_scene_task=VN_SCENE_RUNTIME.set_scene_task,
    create_debounced_vn_scene_task=VN_SCENE_RUNTIME.create_debounced_task,
    is_private_web_task_request=lambda text: _is_private_web_task_request(text),
    study_reader=STUDY_READER,
    screen_ocr_runtime=SCREEN_OCR_RUNTIME,
)

register_notes_journal_handlers(
    sio,
    read_notes_text=lambda: read_notes_text(DATA_DIR),
    write_notes_text=lambda content: write_notes_text(DATA_DIR, content),
    append_notes_text=lambda content: append_notes_text(DATA_DIR, content),
    read_journal_today=lambda: read_journal_today(DATA_DIR),
    get_audio_loop=lambda: audio_loop,
)

register_memory_page_handlers(
    sio,
    data_dir=DATA_DIR,
    resolve_memory_page=lambda path: resolve_memory_page(DATA_DIR, path),
    list_memory_pages=lambda: list_memory_pages(DATA_DIR),
    get_audio_loop=lambda: audio_loop,
)

register_session_mode_handlers(
    sio,
    get_audio_loop=lambda: audio_loop,
    journal_today_path=lambda: journal_today_path(DATA_DIR),
    data_dir=DATA_DIR,
)

register_openclaw_skill_handlers(
    sio,
    get_audio_loop=lambda: audio_loop,
)

register_shared_activity_handlers(
    sio,
    runtime=SHARED_ACTIVITY_RUNTIME,
    get_audio_loop=lambda: audio_loop,
    screen_ocr_runtime=SCREEN_OCR_RUNTIME,
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

# Apply any saved model preset / voice from settings
from .model_config import apply_runtime_settings as _apply_model_settings
_apply_model_settings(
    preset=SETTINGS.get("gemini_model_preset"),
    voice=SETTINGS.get("gemini_voice"),
)

authenticator = None
# Initialize Kasa agent with devices from new smart_home structure
kasa_devices = SETTINGS.get("smart_home", {}).get("kasa", {}).get("devices", [])
# Fallback to old location for backward compatibility
if not kasa_devices:
    kasa_devices = SETTINGS.get("kasa_devices", [])
kasa_agent = KasaAgent(known_devices=kasa_devices)
# tool_permissions is now SETTINGS["tool_permissions"]


if __name__ == "__main__":
    uvicorn.run(
        app_socketio,
        host="127.0.0.1",
        port=8000,
        reload=False, # Reload enabled causes spawn of worker which might miss the event loop policy patch
        loop="asyncio",
        reload_excludes=["output.stl", "*.stl"]
    )
