import sys
import asyncio

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
from fastapi.responses import FileResponse
import asyncio
from contextlib import asynccontextmanager
import threading
import sys
import os
import base64
import json
import time
import re
from datetime import datetime
from pathlib import Path

from study_reader import StudyReader
from study_ocr import ocr_image_bytes
from dataclasses import asdict



# Ensure we can import monikai
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import monikai
from authenticator import FaceAuthenticator
from kasa_agent import KasaAgent
from spotify_manager import SpotifyManager
from telegram_bot import TelegramBotService
from minecraft_agent import MinecraftBotManager
from dotenv import dotenv_values

def _determine_sprite(state_dict: dict) -> str:
    """
    Determines the visual sprite based on personality state.
    Returns a filename stem (e.g. 'monika_happy') expected in /public/vn/.
    """
    mood = (state_dict.get("mood") or "neutral").lower()
    affection = float(state_dict.get("affection") or 0.0)
    energy = float(state_dict.get("energy") or 0.8)
    
    # Base mapping
    variant = "neutral"
    
    # Energy overrides
    if energy < 0.35:
        variant = "tired"
    
    # Mood overrides
    elif "happy" in mood or "sunny" in mood or "excited" in mood:
        variant = "happy"
    elif "sad" in mood or "rainy" in mood or "depressed" in mood or "lonely" in mood:
        variant = "sad"
    elif "angry" in mood or "annoyed" in mood:
        variant = "angry"
    elif "surprised" in mood or "shocked" in mood:
        variant = "surprised"
    elif "shy" in mood or "embarrassed" in mood or "flirty" in mood:
        variant = "shy"
    elif "mysterious" in mood or "foggy" in mood:
        variant = "leaning"
    elif "love" in mood:
        variant = "love"

    # Affection overrides (if not already negative mood)
    if variant not in ("sad", "angry", "tired"):
        if affection > 40.0 and variant == "neutral":
            variant = "happy"
        if affection > 80.0 and variant in ("happy", "neutral", "shy"):
            variant = "love"
            
    return f"monika_{variant}"




MAIN_LOOP = None
ACTIVE_FRONTEND_SID = None
minecraft_bot_manager = None


async def _emit_to_frontend(event: str, payload, room: str = None):
    target_room = room if room is not None else ACTIVE_FRONTEND_SID
    if target_room:
        await sio.emit(event, payload, room=target_room)
    else:
        await sio.emit(event, payload)


def _schedule_emit_to_frontend(event: str, payload, room: str = None):
    asyncio.create_task(_emit_to_frontend(event, payload, room=room))


async def _force_exit_after_delay(delay_seconds: float = 0.15):
    await asyncio.sleep(delay_seconds)
    os._exit(0)

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

    print("[SERVER] Startup: Initializing Kasa Agent...")
    await kasa_agent.initialize()

    # Initialize Global Managers (Persistent across AI sessions)
    global calendar_manager, reminder_manager, personality_system, spotify_manager
    base_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    data_dir = base_dir.parent / "data"
    user_memory_dir = data_dir / "user_memory"
    user_memory_dir.mkdir(parents=True, exist_ok=True)

    # 1. Calendar
    def on_calendar_update_server():
        if calendar_manager:
            events = [e.__dict__ for e in calendar_manager.get_all_events()]
            _schedule_emit_to_frontend('calendar_data', events)
    
    calendar_manager = monikai.CalendarManager(storage_dir=user_memory_dir, on_update=on_calendar_update_server)
    calendar_manager.load()
    print("[SERVER] Calendar Manager initialized.")

    # 2. Reminders
    async def on_reminder_fired_server(rem):
        # Emit to UI
        payload = {
            "id": rem.id, "message": rem.message, "when_iso": rem.when_iso,
            "speak": bool(rem.speak), "alert": bool(getattr(rem, "alert", True))
        }
        _schedule_emit_to_frontend('reminder_fired', payload)
        _schedule_emit_to_frontend('reminders_list', {'reminders': _serialize_reminders()})
        
        # If AI is running, let it handle speaking/logging
        if audio_loop:
            await audio_loop.handle_reminder_fired(rem)

    reminder_manager = monikai.ReminderManager(get_time_context_fn=monikai.get_time_context, storage_dir=user_memory_dir, on_reminder=on_reminder_fired_server)
    reminder_manager.load()
    print("[SERVER] Reminder Manager initialized.")

    # 3. Personality
    def on_personality_update_server(state):
        data = asdict(state)
        data["sprite"] = _determine_sprite(data)
        
        # Calculate hearts for UI display
        aff = max(0.0, min(100.0, float(data.get("affection", 0))))
        score = aff / 10.0
        full = int(score)
        hearts = "❤️" * full + "🤍" * (10 - full)
        data["affection_hearts"] = f"{hearts} ({score:.1f}/10)"
        
        async def _emit():
            await _emit_to_frontend('personality_status', data)
        try:
            if MAIN_LOOP and MAIN_LOOP.is_running():
                asyncio.run_coroutine_threadsafe(_emit(), MAIN_LOOP)
            else:
                asyncio.create_task(_emit())
        except Exception as e:
            print(f"[SERVER] Failed to emit personality_status: {e}")
    
    personality_system = monikai.PersonalitySystem(storage_dir=user_memory_dir, on_update=on_personality_update_server)
    print("[SERVER] Personality System initialized.")

    # 4. Spotify Manager (OAuth + token refresh)
    try:
        spotify_manager = SpotifyManager(data_dir=data_dir)
        st = spotify_manager.status()
        print(
            "[SERVER] Spotify Manager initialized. "
            f"configured={st.get('configured')} connected={st.get('connected')}"
        )
        if st.get("connected"):
            try:
                spotify_manager.refresh_access_token()
            except Exception as e:
                print(f"[SERVER] Spotify token refresh skipped/failed at startup: {e}")
    except Exception as e:
        spotify_manager = None
        print(f"[SERVER] Spotify Manager init failed: {e}")

    # 5. Minecraft Bot Manager
    global minecraft_bot_manager
    try:
        # Load Minecraft bot configuration from .env file
        minecraft_bot_env_path = os.path.join(os.path.dirname(__file__), "minecraft-bot", ".env")
        mc_config = dotenv_values(minecraft_bot_env_path)
        
        mc_host = mc_config.get("MC_HOST", "localhost")
        mc_port = int(mc_config.get("MC_PORT", "25565"))
        mc_username = mc_config.get("MC_USERNAME", "strawberryglass")
        mc_auth = mc_config.get("MC_AUTH", "offline")
        mc_version = mc_config.get("MC_VERSION", "1.20.4")
        
        minecraft_bot_manager = MinecraftBotManager(
            host=mc_host,
            port=mc_port,
            username=mc_username,
            auth=mc_auth,
            version=mc_version
        )
        
        print(
            "[SERVER] Minecraft Bot Manager initialized. "
            f"host={mc_host}:{mc_port} username={mc_username}"
        )
        
        # Register perception callback  
        async def on_minecraft_perception(event):
            print(f"[PERCEPTION] Received event: type={event.event_type}, has_session={'Yes' if (audio_loop and audio_loop.session) else 'No'}")
            
            # Send to frontend
            _schedule_emit_to_frontend('minecraft_perception', {
                'event_type': event.event_type,
                'data': event.data,
                'timestamp': event.timestamp
            })
            
            # Send important events to Monika via Gemini
            if not audio_loop or not audio_loop.session:
                print(f"[PERCEPTION] Skipping: audio_loop={audio_loop is not None}, session_exists={audio_loop.session is not None if audio_loop else 'N/A'}")
                return
            
            try:
                if event.event_type == "chat":
                    # Chat messages from other players
                    data = event.data or {}
                    username = data.get("username", "Unknown")
                    message = data.get("message", "")
                    if message:
                        msg = f"[Minecraft Chat] {username}: {message}"
                        print(f"[PERCEPTION] Sending to Monika: {msg}")
                        await audio_loop.session.send(input=msg, end_of_turn=False)
                
                elif event.event_type == "action_result":
                    # Results from bot actions
                    data = event.data or {}
                    action = data.get("action", "unknown")
                    success = data.get("success", False)
                    result_msg = data.get("message", "No message")
                    
                    if action and not success:
                        msg = f"[Minecraft] Action '{action}' failed: {result_msg}"
                        print(f"[PERCEPTION] Sending to Monika: {msg}")
                        await audio_loop.session.send(input=msg, end_of_turn=False)
                
                elif event.event_type == "error":
                    # Bot errors
                    data = event.data or {}
                    error_msg = data.get("message", "Unknown error")
                    msg = f"[Minecraft] Error: {error_msg}"
                    print(f"[PERCEPTION] Sending to Monika: {msg}")
                    await audio_loop.session.send(input=msg, end_of_turn=False)
            
            except Exception as e:
                print(f"[PERCEPTION] Failed to send minecraft event to Monika: {e}")
                import traceback
                traceback.print_exc()
        
        minecraft_bot_manager.register_perception_callback(on_minecraft_perception)
    except Exception as e:
        minecraft_bot_manager = None
        print(f"[SERVER] Minecraft Bot Manager init failed: {e}")

    global telegram_service, telegram_task
    telegram_service = TelegramBotService.from_env(
        lambda: SETTINGS,
        calendar_manager=calendar_manager,
        reminder_manager=reminder_manager,
        spotify_manager=spotify_manager,
        personality=personality_system,
    )
    if telegram_service:
        telegram_task = asyncio.create_task(telegram_service.run())
        print("[SERVER] Telegram bot service started.")

    try:
        yield
    finally:
        # Stop Minecraft bot
        if minecraft_bot_manager:
            try:
                await minecraft_bot_manager.stop()
            except Exception as e:
                print(f"[SERVER] Minecraft bot stop failed: {e}")
        
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

# Create a Socket.IO server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*', max_http_buffer_size=25 * 1024 * 1024)
app = FastAPI(lifespan=lifespan)
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
    print(f"\n[SERVER] Caught signal {sig}. Exiting gracefully...")
    # Clean up audio loop
    if audio_loop:
        try:
            print("[SERVER] Stopping Audio Loop...")
            audio_loop.stop() 
        except:
            pass
    # Force kill
    print("[SERVER] Force exiting...")
    os._exit(0)

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
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = BASE_DIR.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"
STUDY_DIR = DATA_DIR / "study"
last_start_params = {}
telegram_service = None
telegram_task = None


def _safe_study_path(rel_path: str) -> Path:
    raw = (rel_path or "").replace("\\", "/").lstrip("/")
    candidate = (STUDY_DIR / raw).resolve()
    if STUDY_DIR not in candidate.parents and candidate != STUDY_DIR:
        raise HTTPException(status_code=400, detail="Invalid study path.")
    return candidate

DEFAULT_SETTINGS = {
    "face_auth_enabled": False, # Default OFF as requested
    "show_internal_thoughts": False, # UI Toggle state
    "tool_permissions": {
        "cancel_reminder": True,
        "control_light": True,
        "clear_work_memory": True,
        "notes_set": True,
        "run_web_agent": True,
        "run_openclaw_agent": True,
        "manage_agent_job": True,
        "list_openclaw_skills": False,
        "list_skills": False,
        "get_openclaw_skill": False,
        "get_skill": False,
        "refresh_openclaw_skills": False,
        "refresh_skills": False,
        "run_openclaw_skill_command": True,
        "run_skill_command": True,
        "spotify_get_auth_url": False,
        "spotify_get_status": False,
        "spotify_get_now_playing": False,
        "spotify_list_playlists": False,
        "spotify_recently_played": False,
        "write_file": True
    },# List of {host, port, name, type}
    "kasa_devices": [], # List of {ip, alias, model}
    "camera_flipped": False, # Invert cursor horizontal direction
    "camera_source": "frontend", # "frontend" uses UI stream; "backend" uses OpenCV
    "video_mode": "none", # none | screen | camera
    "camera_capture": { # backend camera capture (if enabled)
        "fps": 2.0,
        "max_size": 1024,
        "jpeg_quality": 80
    },
    "screen_capture": { # backend screen capture (if enabled)
        "fps": 6.0,
        "max_size": 1280,
        "jpeg_quality": 70,
        "monitor": 1,
        "format": "jpeg",
        "region": None,
        "mode": "continuous"
    },
    "proactivity": {
        "idle_nudges": {
            "enabled": True,
            "threshold_sec": 900,
            "cooldown_sec": 1800,
            "min_ai_quiet_sec": 60,
            "max_per_session": 3,
            "max_per_hour": 4,
            "topic_memory_size": 6,
            "score_threshold": 0.98,
            "quiet_hours_enabled": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "06:00",
            "adaptive_enabled": True,
            "adaptive_backoff_step": 0.7,
            "adaptive_max_multiplier": 4.0,
            "recent_user_memory_size": 3,
            "recent_user_max_chars": 160,
            "question_min_interval_sec": 1800.0,
            "question_backoff_1_sec": 2700.0,
            "question_backoff_2_sec": 3600.0,
            "startup_grace_sec": 600.0,
            "min_user_messages_before_nudge": 2
        },
        "reasoning": {
            "enabled": True,
            "interval_sec": 120.0
        }
    }
}

SETTINGS = DEFAULT_SETTINGS.copy()
STUDY_READER = StudyReader()

SCREEN_OCR_MIN_INTERVAL_SEC = 0.8
SCREEN_OCR_DEBOUNCE_DELAY_SEC = 0.6
_LAST_SCREEN_OCR_TS = 0.0
_SCREEN_OCR_DEBOUNCE_TASK = None


def _should_run_screen_ocr(text: str) -> bool:
    if not text:
        return False
    t = str(text).lower()
    if len(t) < 3:
        return False
    keywords = [
        "co pisze",
        "co jest napisane",
        "co jest na ekranie",
        "jaki napis",
        "jakie napisy",
        "przeczytaj",
        "odczytaj",
        "napis",
        "napisy",
        "tekst",
        "dialog",
        "napisy",
        "subtitle",
        "subtitles",
        "caption",
        "what does it say",
        "what's it say",
        "what is written",
        "what's written",
        "read the text",
        "read the dialog",
        "dialog says",
        "quest",
        "objective",
        "mission",
        "hint",
        "tooltip",
    ]
    return any(k in t for k in keywords)


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


def _get_latest_screen_bytes():
    payload = getattr(audio_loop, "_latest_image_payload", None)
    if not payload or not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not data:
        return None
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    try:
        return base64.b64decode(data)
    except Exception:
        return None


async def _send_system_notice(msg: str):
    if not audio_loop or not getattr(audio_loop, "session", None):
        return
    try:
        if hasattr(audio_loop, "send_system_message"):
            await audio_loop.send_system_message(msg, end_of_turn=False)
        else:
            await audio_loop.session.send(input=msg, end_of_turn=False)
    except Exception:
        pass


async def _maybe_send_screen_ocr(text: str) -> bool:
    global _LAST_SCREEN_OCR_TS
    if not audio_loop or not getattr(audio_loop, "session", None):
        return False
    if getattr(audio_loop, "video_mode", None) != "screen":
        return False
    if not _should_run_screen_ocr(text):
        return False
    now = time.time()
    if (now - _LAST_SCREEN_OCR_TS) < SCREEN_OCR_MIN_INTERVAL_SEC:
        return False
    _LAST_SCREEN_OCR_TS = now

    try:
        await audio_loop.refresh_latest_frame(min_age_sec=0.05)
    except Exception:
        pass

    raw = _get_latest_screen_bytes()
    if not raw:
        await _send_system_notice("System Notification: [Screen OCR] No screen frame available for OCR.")
        return False

    lang = (os.getenv("SCREEN_OCR_LANG") or "en").strip().lower()
    engine = (os.getenv("SCREEN_OCR_ENGINE") or "local").strip().lower()
    use_gpu_env = os.getenv("SCREEN_OCR_USE_GPU", "").strip().lower()
    use_gpu = use_gpu_env in ("1", "true", "yes", "y", "on")

    try:
        text_out, err = await asyncio.to_thread(
            ocr_image_bytes,
            raw,
            lang=lang,
            use_gpu=use_gpu,
            engine=engine,
        )
    except Exception as e:
        await _send_system_notice(f"System Notification: [Screen OCR] Failed: {e}")
        return False

    if not text_out:
        if err:
            if err == "paddleocr_no_text":
                await _send_system_notice("System Notification: [Screen OCR] No readable text found on screen.")
            else:
                await _send_system_notice(f"System Notification: [Screen OCR] Unavailable: {err}")
        return False

    cleaned = " ".join(str(text_out).split())
    snippet = cleaned[:1200] + ("..." if len(cleaned) > 1200 else "")
    await _send_system_notice(f"System Notification: [Screen OCR] Extracted text snippet: {snippet}")
    return True


def _schedule_screen_ocr_from_transcription():
    global _SCREEN_OCR_DEBOUNCE_TASK
    if _SCREEN_OCR_DEBOUNCE_TASK and not _SCREEN_OCR_DEBOUNCE_TASK.done():
        try:
            _SCREEN_OCR_DEBOUNCE_TASK.cancel()
        except Exception:
            pass
    _SCREEN_OCR_DEBOUNCE_TASK = asyncio.create_task(_debounced_screen_ocr())


async def _debounced_screen_ocr():
    await asyncio.sleep(SCREEN_OCR_DEBOUNCE_DELAY_SEC)
    if not audio_loop:
        return
    try:
        buf = getattr(audio_loop, "chat_buffer", {}) or {}
        if buf.get("sender") != "Ty":
            return
        text = buf.get("text") or ""
    except Exception:
        return
    await _maybe_send_screen_ocr(text)

def load_settings():
    global SETTINGS
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                loaded = json.load(f)
                # Merge with defaults to ensure new keys exist
                # Deep merge for tool_permissions would be better but shallow merge of top keys + tool_permissions check is okay for now
                for k, v in loaded.items():
                    if k == "tool_permissions" and isinstance(v, dict):
                         SETTINGS["tool_permissions"].update(v)
                    elif k == "proactivity" and isinstance(v, dict):
                        for pk, pv in v.items():
                            if pk == "idle_nudges" and isinstance(pv, dict):
                                SETTINGS["proactivity"]["idle_nudges"].update(pv)
                            else:
                                SETTINGS["proactivity"][pk] = pv
                    else:
                        SETTINGS[k] = v
            print(f"Loaded settings: {SETTINGS}")
        except Exception as e:
            print(f"Error loading settings: {e}")

def save_settings():
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(SETTINGS, f, indent=4)
        print("Settings saved.")
    except Exception as e:
        print(f"Error saving settings: {e}")

# Load on startup
load_settings()

authenticator = None
kasa_agent = KasaAgent(known_devices=SETTINGS.get("kasa_devices"))
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


@app.get("/study/catalog")
async def study_catalog():
    if not STUDY_DIR.exists():
        return {"folders": []}
    folders = []
    for folder in sorted([p for p in STUDY_DIR.iterdir() if p.is_dir()]):
        files = []
        for f in sorted(folder.glob("*.pdf")):
            name = f.name
            is_answer_key = "answer key" in name.lower()
            rel = f.relative_to(STUDY_DIR).as_posix()
            files.append({
                "name": name,
                "path": rel,
                "is_answer_key": is_answer_key,
            })
        if files:
            folders.append({"name": folder.name, "files": files})
    return {"folders": folders}


@app.get("/study/file")
async def study_file(path: str):
    safe_path = _safe_study_path(path)
    if not safe_path.exists() or safe_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=404, detail="File not found")
    if "answer key" in safe_path.name.lower():
        raise HTTPException(status_code=403, detail="Answer key is restricted")
    headers = {
        "Content-Disposition": f'inline; filename="{safe_path.name}"',
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Range, Content-Type, Authorization",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
    }
    return FileResponse(
        str(safe_path),
        media_type="application/pdf",
        headers=headers,
    )


@app.options("/study/file")
async def study_file_options():
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Type, Authorization",
            "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
        },
    )

@sio.event
async def connect(sid, environ):
    global ACTIVE_FRONTEND_SID
    ACTIVE_FRONTEND_SID = sid
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
    global ACTIVE_FRONTEND_SID
    if ACTIVE_FRONTEND_SID == sid:
        ACTIVE_FRONTEND_SID = None
    print(f"Client disconnected: {sid}")

@sio.event
async def start_audio(sid, data=None):
    global audio_loop, loop_task, last_start_params, ACTIVE_FRONTEND_SID
    ACTIVE_FRONTEND_SID = sid
    
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
                    _schedule_screen_ocr_from_transcription()
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
            if "sprite" not in data:
                data["sprite"] = _determine_sprite(data)
            _schedule_emit_to_frontend('personality_status', data)
        except Exception as e:
            print(f"[SERVER] Failed to emit personality_status: {e}")

    # Callback for Internal Thoughts
    def on_internal_thought(thought):
        print(f"[SYSTEM NOTIFICATION] Internal Thought: {thought}")
        _schedule_emit_to_frontend('internal_thought', {'thought': thought})
        
        # Always emit to chat log so frontend can toggle visibility retroactively
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

    # Initialize MonikAI
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
        
        # Set Minecraft bot manager reference
        audio_loop.minecraft_bot_manager = minecraft_bot_manager
        
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
async def list_reminders(sid, data=None):
    """Frontend requests current reminder list."""
    await sio.emit('reminders_list', {'reminders': _serialize_reminders()}, room=sid)


@sio.event
async def list_calendar(sid, data=None):
    """Frontend requests current calendar events."""
    events = []
    if calendar_manager:
        events = [e.__dict__ for e in calendar_manager.get_all_events()]
    await sio.emit('calendar_data', events, room=sid)

@sio.event
async def get_personality_status(sid):
    """Frontend requests current personality status."""
    if personality_system:
        data = asdict(personality_system.state)
        data["sprite"] = _determine_sprite(data)
        aff = max(0.0, min(100.0, float(data.get("affection", 0))))
        score = aff / 10.0
        full = int(score)
        hearts = "❤️" * full + "🤍" * (10 - full)
        data["affection_hearts"] = f"{hearts} ({score:.1f}/10)"
        await sio.emit('personality_status', data, room=sid)

@sio.event
async def delete_event(sid, data):
    """Frontend deletes a calendar event."""
    eid = (data or {}).get('id')
    if not eid:
        return
    if calendar_manager:
        calendar_manager.delete_event(eid)

@sio.event
async def update_reminder(sid, data):
    rid = data.get('id')
    msg = data.get('message')
    if reminder_manager and rid:
        reminder_manager.update(rid, message=msg)
        await sio.emit('reminders_list', {'reminders': _serialize_reminders()}, room=sid)

@sio.event
async def update_event(sid, data):
    eid = data.get('id')
    summary = data.get('summary')
    if calendar_manager and eid:
        calendar_manager.update_event(eid, summary=summary)
        # emit calendar_data
        events = [e.__dict__ for e in calendar_manager.get_all_events()]
        await sio.emit('calendar_data', events, room=sid)

@sio.event
async def cancel_reminder(sid, data):
    """Frontend cancels a reminder by id."""
    rid = (data or {}).get('id')
    if not rid:
        await sio.emit('error', {'msg': 'cancel_reminder: Missing id'}, room=sid)
        return

    if not reminder_manager:
        await sio.emit('error', {'msg': 'Reminders not available'}, room=sid)
        return

    ok = reminder_manager.cancel(rid)
    await sio.emit('reminders_list', {'reminders': _serialize_reminders()}, room=sid)
    if ok:
        await sio.emit('status', {'msg': 'Reminder cancelled'}, room=sid)
    else:
        await sio.emit('status', {'msg': 'Reminder not found'}, room=sid)


@sio.event
async def create_reminder(sid, data):
    """Optional: Frontend can create a reminder (same semantics as the model tool)."""
    if not reminder_manager:
        await sio.emit('error', {'msg': 'Reminders not available'}, room=sid)
        return

    data = data or {}
    message = (data.get('message') or '').strip()
    at = data.get('at')
    in_minutes = data.get('in_minutes')
    in_seconds = data.get('in_seconds')
    speak = data.get('speak', True)
    alert = data.get('alert', True)

    if not message:
        await sio.emit('error', {'msg': 'create_reminder: Missing message'}, room=sid)
        return

    try:
        rem = reminder_manager.create(message=message, at=at, in_minutes=in_minutes, in_seconds=in_seconds, speak=speak, alert=alert)
        await sio.emit('status', {'msg': f"Reminder created ({rem.id})"}, room=sid)

        # Let the model know (so it can reference it later)
        try:
            if getattr(audio_loop, 'session', None):
                kind = 'timer' if (in_seconds is not None or in_minutes is not None) and (at is None) else 'reminder'
                when_desc = rem.when_iso
                await audio_loop.session.send(
                    input=(
                        f"System Notification: User manually created a {kind}. \
Message: {rem.message}. \
When: {when_desc}. \
Speak: {bool(rem.speak)}. Alert: {bool(getattr(rem, 'alert', True))}."
                    ),
                    end_of_turn=False
                )
        except Exception as e:
            print(f"[SERVER] Failed to notify model about reminder: {e}")
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to create reminder: {e}"}, room=sid)

    await sio.emit('reminders_list', {'reminders': _serialize_reminders()}, room=sid)

@sio.event
async def create_event(sid, data):
    """Frontend creates a calendar event."""
    if not calendar_manager:
        await sio.emit('error', {'msg': 'Calendar not available'}, room=sid)
        return

    data = data or {}
    summary = data.get('summary')
    start_iso = data.get('start_iso')
    end_iso = data.get('end_iso')
    description = data.get('description')

    if not summary or not start_iso or not end_iso:
        await sio.emit('error', {'msg': 'create_event: Missing summary, start_iso, or end_iso'}, room=sid)
        return

    try:
        event = calendar_manager.create_event(summary=summary, start_iso=start_iso, end_iso=end_iso, description=description)
        await sio.emit('status', {'msg': f"Event created ({event.id})"}, room=sid)
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to create event: {e}"}, room=sid)

    # Emit update
    if calendar_manager:
        events = [e.__dict__ for e in calendar_manager.get_all_events()]
        await sio.emit('calendar_data', events, room=sid)

@sio.event
async def confirm_tool(sid, data):
    # data: { "id": "...", "confirmed": True/False }
    request_id = data.get('id')
    confirmed = data.get('confirmed', False)
    
    print(f"[SERVER DEBUG] Received confirmation response for {request_id}: {confirmed}")
    
    if audio_loop:
        audio_loop.resolve_tool_confirmation(request_id, confirmed)
    else:
        print("Audio loop not active, cannot resolve confirmation.")

@sio.event
async def shutdown(sid, data=None):
    """Gracefully shutdown the server when the application closes."""
    global audio_loop, loop_task, authenticator
    
    print("[SERVER] ========================================")
    print("[SERVER] SHUTDOWN SIGNAL RECEIVED FROM FRONTEND")
    print("[SERVER] ========================================")
    
    # Stop audio loop
    if audio_loop:
        print("[SERVER] Stopping Audio Loop...")
        audio_loop.stop()
        audio_loop = None
    
    # Cancel the loop task if running
    if loop_task and not loop_task.done():
        print("[SERVER] Cancelling loop task...")
        loop_task.cancel()
        loop_task = None
    
    # Stop authenticator if running
    if authenticator:
        print("[SERVER] Stopping Authenticator...")
        authenticator.stop()
    
    print("[SERVER] Graceful shutdown complete. Terminating process...")
    asyncio.create_task(_force_exit_after_delay())
    return {"ok": True}

@sio.event
async def user_input(sid, data):
    text = data.get('text')
    attachments = data.get('attachments') or []
    print(f"[SERVER DEBUG] User input received: '{text}'")
    
    if not audio_loop:
        print("[SERVER DEBUG] [Error] Audio loop is None. Cannot send text.")
        return

    if not audio_loop.session:
        print("[SERVER DEBUG] [Error] Session is None. Cannot send text.")
        return

    if text or attachments:
        if text:
            print(f"[SERVER DEBUG] Sending message to model: '{text}'")
        if attachments:
            print(f"[SERVER DEBUG] Received {len(attachments)} attachment(s).")

        sent_visual = False
        sent_screen_ocr = False
        max_visual_age_sec = 2.0
        latest_age = None
        study_payload = None
        study_meta = {}

        # Mark user activity (prevents idle nudges + updates topic memory)
        try:
            audio_loop_mark_user_activity(audio_loop, text)
        except Exception:
            pass

        # Scene switching based on user text (text chat)
        try:
            if text:
                global _vn_user_buf, _vn_user_last_ts, _vn_scene_task
                _vn_user_buf = (_vn_user_buf + " " + text).strip()[-400:]
                _vn_user_last_ts = time.time()
                if _vn_scene_task is None or _vn_scene_task.done():
                    _vn_scene_task = asyncio.create_task(_debounced_vn_scene_check())
        except Exception:
            pass
        
        # Log User Input to Session History
        if audio_loop and getattr(audio_loop, "session_manager", None):
            audio_loop.session_manager.log_chat("User", text)
            
        # INJECT VIDEO FRAME IF AVAILABLE (VAD-style logic for Text Input)
        # Refresh screen frame for lowest latency
        if audio_loop and getattr(audio_loop, "video_mode", None) == "screen":
            try:
                await audio_loop.refresh_latest_frame(min_age_sec=0.05)
            except Exception:
                pass

        # If camera is frontend-based, request a fresh frame from UI
        if audio_loop and getattr(audio_loop, "video_mode", None) == "camera":
            try:
                if getattr(audio_loop, "camera_source", "frontend") == "frontend":
                    await sio.emit("request_camera_frame", to=sid)
                    await asyncio.sleep(0.08)
            except Exception:
                pass

        # Send attachments (if any) before the text
        if attachments:
            try:
                summary = []
                for a in attachments:
                    name = a.get("name") or "unnamed"
                    mime_type = a.get("mime_type") or "application/octet-stream"
                    size = a.get("size")
                    size_str = f"{size} bytes" if isinstance(size, int) else "unknown size"
                    summary.append(f"{name} ({mime_type}, {size_str})")
                await audio_loop.session.send(
                    input=("System Notification: User attached files: " + "; ".join(summary)),
                    end_of_turn=False,
                )
            except Exception as e:
                print(f"[SERVER DEBUG] Failed to send attachment summary: {e}")

            for a in attachments:
                try:
                    payload = {
                        "mime_type": a.get("mime_type") or "application/octet-stream",
                        "data": a.get("data"),
                    }
                    if payload["data"]:
                        await audio_loop.session.send(input=payload, end_of_turn=False)
                        if str(payload["mime_type"]).startswith("image/"):
                            sent_visual = True
                except Exception as e:
                    print(f"[SERVER DEBUG] Failed to send attachment payload: {e}")

        study_payload, study_meta = STUDY_READER.get_latest_image(max_age_sec=45.0)

        page_request = False
        private_web_task_request = False
        if text:
            norm_text = str(text).lower()
            if re.search(r"\bcan you see (this )?current page\??\b", norm_text):
                page_request = True
            private_web_task_request = _is_private_web_task_request(norm_text)

        if page_request:
            try:
                reminder = (
                    'System Notification: The user is asking if you can see the current study page. '
                    'You must tell them: "Send me the current page", and explain you can only read it '
                    "after they send it via the chat button."
                )
                await audio_loop.session.send(input=reminder, end_of_turn=False)
            except Exception:
                pass

        if private_web_task_request:
            try:
                web_task_nudge = (
                    "System Notification: [Private Service Routing] The user asked for help with a private web service "
                    "(e.g., email inbox). Choose approach adaptively: if a relevant Skill is available and "
                    "eligible, you may use `run_openclaw_skill_command`; otherwise use `run_openclaw_agent` (or "
                    "`manage_agent_job` action=start for longer flows). For browser flows, guide step by step. "
                    "If login/2FA is required, ask the user to complete it manually in browser. "
                    "Never ask for or store passwords."
                )
                await audio_loop.session.send(input=web_task_nudge, end_of_turn=False)
            except Exception:
                pass

        if not study_payload and audio_loop and getattr(audio_loop, "video_mode", None) == "screen":
            try:
                await audio_loop.refresh_latest_frame(min_age_sec=0.5)
            except Exception:
                pass

        if study_payload and not sent_visual:
            try:
                page = study_meta.get("page")
                page_label = study_meta.get("page_label")
                folder = study_meta.get("folder")
                file = study_meta.get("file")
                label_note = f" (book page {page_label})" if page_label else ""
                meta_msg = (
                    "System Notification: [Study] "
                    f"Use the attached study page image for the user's question. "
                    f"Current page: {page}{label_note} from {folder}/{file}. "
                    "Do not use prior knowledge about the textbook. "
                    "Do not guess; if the image is unreadable, say you cannot read it."
                )
                await audio_loop.session.send(input=meta_msg, end_of_turn=False)
                await audio_loop.session.send(input=study_payload, end_of_turn=False)
                sent_visual = True

                ocr_text, ocr_meta = STUDY_READER.get_latest_text(max_age_sec=45.0)
                if ocr_text and ocr_meta:
                    if ocr_meta.get("page") == page and ocr_meta.get("file") == file:
                        ocr_msg = f"System Notification: [Study OCR] Text snippet for this page: {ocr_text}"
                        await audio_loop.session.send(input=ocr_msg, end_of_turn=False)

                tiles, tiles_meta = STUDY_READER.get_latest_tiles(max_age_sec=45.0)
                if tiles and tiles_meta:
                    if tiles_meta.get("page") == page and tiles_meta.get("file") == file:
                        tiles_msg = (
                            "System Notification: [Study] Zoom tiles are attached for small text. "
                            "Use them to read precise content. Do not guess."
                        )
                        await audio_loop.session.send(input=tiles_msg, end_of_turn=False)
                        for payload in tiles:
                            await audio_loop.session.send(input=payload, end_of_turn=False)
            except Exception as e:
                print(f"[SERVER DEBUG] Failed to send study page image: {e}")

        if not sent_visual and audio_loop and getattr(audio_loop, "_latest_image_payload", None):
            if getattr(audio_loop, "_latest_image_ts", None):
                latest_age = time.time() - audio_loop._latest_image_ts
            if latest_age is None or latest_age <= max_visual_age_sec:
                print(f"[SERVER DEBUG] Piggybacking video frame with text input.")
                try:
                    await audio_loop.session.send(input=audio_loop._latest_image_payload, end_of_turn=False)
                    sent_visual = True
                except Exception as e:
                    print(f"[SERVER DEBUG] Failed to send piggyback frame: {e}")
            else:
                print(f"[SERVER DEBUG] Skipping stale visual frame (age {latest_age:.2f}s).")

        if text:
            try:
                sent_screen_ocr = await _maybe_send_screen_ocr(text)
            except Exception:
                sent_screen_ocr = False

        if not sent_visual and not sent_screen_ocr and audio_loop and getattr(audio_loop, "video_mode", None) in ("screen", "camera"):
            note = "System Notification: No visual frame was sent with this turn. If you did not receive an image, say you cannot see the user's screen/camera."
            if latest_age is not None:
                note += f" Last visual frame age: {latest_age:.2f}s."
            try:
                await audio_loop.session.send(input=note, end_of_turn=False)
            except Exception:
                pass

        # Therapy guidance (auto) for session mode
        if text and audio_loop and getattr(audio_loop, "send_therapy_guidance", None) and getattr(audio_loop, "session_mode", False):
            try:
                await audio_loop.send_therapy_guidance(text, force=False)
            except Exception:
                pass

        # Inject memory context (global memory engine)
        if text and audio_loop and getattr(audio_loop, "build_memory_context", None):
            try:
                mem_ctx = audio_loop.build_memory_context(text)
                if mem_ctx:
                    await audio_loop.session.send(input=mem_ctx, end_of_turn=False)
            except Exception:
                pass
                
        if text:
            try:
                await audio_loop.session.send(input=text, end_of_turn=True)
                print(f"[SERVER DEBUG] Message sent to model successfully.")
            except Exception as e:
                print(f"[SERVER DEBUG] Failed to send message to model: {e}")
                await _emit_to_frontend('status', {'msg': 'Connection lost. Reconnecting...'})
        else:
            try:
                await audio_loop.session.send(
                    input="System Notification: User sent attachments without additional text.",
                    end_of_turn=True,
                )
                print(f"[SERVER DEBUG] Attachments-only message sent to model.")
            except Exception as e:
                print(f"[SERVER DEBUG] Failed to send attachments-only message: {e}")
                await _emit_to_frontend('status', {'msg': 'Connection lost. Reconnecting...'})

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

@sio.event
async def save_memory(sid, data):
    try:
        messages = data.get('messages', [])
        if not messages:
            print("No messages to save.")
            return

        # Ensure directory exists
        memory_dir = DATA_DIR / "long_term_memory"
        memory_dir.mkdir(exist_ok=True)

        # Generate filename
        # Use provided filename if available, else timestamp
        provided_name = data.get('filename')
        
        if provided_name:
            # Simple sanitization
            if not provided_name.endswith('.txt'):
                provided_name += '.txt'
            # Prevent directory traversal
            filename = memory_dir / Path(provided_name).name 
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = memory_dir / f"memory_{timestamp}.txt"

        # Write to file
        with open(filename, 'w', encoding='utf-8') as f:
            for msg in messages:
                sender = msg.get('sender', 'Unknown')
                text = msg.get('text', '')
                f.write(f"{sender}: {text}\n")
        print(f"Conversation saved to {filename}")
        await sio.emit('status', {'msg': 'Memory Saved Successfully'}, room=sid)

    except Exception as e:
        print(f"Error saving memory: {e}")
        await sio.emit('error', {'msg': f"Failed to save memory: {str(e)}"}, room=sid)

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
async def notes_get(sid):
    text = _read_notes_text()
    await sio.emit('notes_data', {'text': text, 'scope': 'global'}, room=sid)

@sio.event
async def notes_set(sid, data):
    try:
        content = (data or {}).get("content", "")
        _write_notes_text(content)
        await sio.emit('notes_data', {'text': content, 'scope': 'global'}, room=sid)
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to save notes: {e}"}, room=sid)

@sio.event
async def notes_append(sid, data):
    try:
        content = (data or {}).get("content", "")
        _append_notes_text(content)
        text = _read_notes_text()
        await sio.emit('notes_data', {'text': text, 'scope': 'global'}, room=sid)
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to append notes: {e}"}, room=sid)

@sio.event
async def notes_clear(sid):
    try:
        _write_notes_text("")
        await sio.emit('notes_data', {'text': "", 'scope': 'global'}, room=sid)
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to clear notes: {e}"}, room=sid)

@sio.event
async def journal_get_today(sid):
    text, date_key = _read_journal_today()
    await sio.emit('journal_today', {'text': text, 'date': date_key}, room=sid)

@sio.event
async def journal_add(sid, data):
    try:
        if not audio_loop or not getattr(audio_loop, "memory_engine", None):
            await sio.emit('error', {'msg': "Memory engine not available."}, room=sid)
            return
        content = (data or {}).get("content", "")
        topics = (data or {}).get("topics") or []
        mood = (data or {}).get("mood")
        tags = (data or {}).get("tags") or []

        entry_id = audio_loop.memory_engine.journal_add_entry(
            content=content,
            topics=topics,
            mood=mood,
            tags=tags,
        )
        await sio.emit('journal_saved', {'id': entry_id}, room=sid)
        text, date_key = _read_journal_today()
        await sio.emit('journal_today', {'text': text, 'date': date_key}, room=sid)
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to add journal entry: {e}"}, room=sid)

@sio.event
async def journal_finalize(sid, data):
    try:
        if not audio_loop or not getattr(audio_loop, "memory_engine", None):
            await sio.emit('error', {'msg': "Memory engine not available."}, room=sid)
            return
        summary = (data or {}).get("summary", "")
        reflections = (data or {}).get("reflections")
        session_id = (data or {}).get("session_id")
        result = audio_loop.memory_engine.journal_finalize_session(
            summary=summary,
            reflections=reflections,
            session_id=session_id,
        )
        await sio.emit('journal_finalized', {'status': result}, room=sid)
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to finalize session: {e}"}, room=sid)

@sio.event
async def session_mode_set(sid, data):
    try:
        from session_modes import get_session_mode_message, DEFAULT_KIND

        active = bool((data or {}).get("active", False))
        # Always keep session mode in AUTO so Monika can decide depth/pace.
        kind = DEFAULT_KIND
        if audio_loop and getattr(audio_loop, "set_session_mode", None):
            audio_loop.set_session_mode(active=active, kind=kind)
        await sio.emit('session_mode', {'active': active, 'kind': kind}, room=sid)

        if audio_loop and audio_loop.session:
            if active:
                msg = get_session_mode_message(kind)
            else:
                msg = (
                    "System Notification: Session mode disabled. "
                    "Please write an internal session summary and reflections. "
                    "Call journal_finalize_session with summary + reflections. "
                    "Do NOT show the summary to the user."
                )
            if hasattr(audio_loop, "send_system_message"):
                await audio_loop.send_system_message(msg, end_of_turn=False)
            else:
                await audio_loop.session.send(input=msg, end_of_turn=False)
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to set session mode: {e}"}, room=sid)

@sio.event
async def session_exercise_submit(sid, data):
    try:
        if not audio_loop or not getattr(audio_loop, "memory_engine", None):
            await sio.emit('error', {'msg': "Memory engine not available."}, room=sid)
            return
        exercise_id = (data or {}).get("exercise_id") or "exercise"
        title = (data or {}).get("title") or exercise_id
        fields = (data or {}).get("fields") or {}
        notes = (data or {}).get("notes") or ""

        lines = [f"Exercise: {title}", ""]
        for k, v in fields.items():
            if v is None:
                continue
            lines.append(f"- {k}: {v}")
        if notes:
            lines.extend(["", f"Notes: {notes}"])
        content = "\n".join(lines).strip()

        entry_id, _ = audio_loop.memory_engine.add_entry(
            type="reflection",
            content=content,
            tags=["exercise", exercise_id],
            entities=["user"],
            origin="real",
            confidence=0.7,
            stability="medium",
            data={"exercise_id": exercise_id, "title": title, "fields": fields, "notes": notes},
        )

        # Append to today's journal page
        try:
            journal_path, _ = _journal_today_path()
            block = [
                f"## Exercise: {title} ({datetime.now().strftime('%H:%M')})",
                *[f"- {k}: {v}" for k, v in fields.items() if v is not None and str(v).strip()],
            ]
            if notes:
                block.append(f"- Notes: {notes}")
            audio_loop.memory_engine.append_page(str(journal_path), "\n".join(block) + "\n")
        except Exception:
            pass

        await sio.emit('session_exercise_saved', {'id': entry_id}, room=sid)

        if audio_loop and audio_loop.session:
            try:
                if hasattr(audio_loop, "send_system_message"):
                    await audio_loop.send_system_message(
                        f"System Notification: The user completed an exercise '{title}'. You can respond briefly and empathetically.",
                        end_of_turn=False,
                    )
                else:
                    await audio_loop.session.send(
                        input=f"System Notification: The user completed an exercise '{title}'. You can respond briefly and empathetically.",
                        end_of_turn=False,
                    )
            except Exception:
                pass
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to save exercise: {e}"}, room=sid)

@sio.event
async def session_sketch_save(sid, data):
    try:
        if not audio_loop or not getattr(audio_loop, "memory_engine", None):
            await sio.emit('error', {'msg': "Memory engine not available."}, room=sid)
            return
        image_data = (data or {}).get("image")
        label = (data or {}).get("label") or "feeling_sketch"
        if not image_data or "base64," not in image_data:
            await sio.emit('error', {'msg': "Invalid image data."}, room=sid)
            return

        header, b64 = image_data.split("base64,", 1)
        ext = "png"
        if "image/jpeg" in header:
            ext = "jpg"

        date_dir = datetime.now().strftime("%Y-%m-%d")
        out_dir = DATA_DIR / "memory" / "pages" / "journal" / "sketches" / date_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"sketch_{datetime.now().strftime('%H%M%S')}.{ext}"
        path = out_dir / filename

        import base64 as _b64
        path.write_bytes(_b64.b64decode(b64))

        entry_id, _ = audio_loop.memory_engine.add_entry(
            type="reflection",
            content=f"Feeling sketch saved: {label}",
            tags=["sketch", "session"],
            entities=["user"],
            origin="real",
            confidence=0.6,
            stability="low",
            data={"file": str(path), "label": label},
        )

        try:
            journal_path, _ = _journal_today_path()
            rel = path.relative_to(DATA_DIR)
            audio_loop.memory_engine.append_page(
                str(journal_path),
                f"## Feeling Sketch ({datetime.now().strftime('%H:%M')})\n- file: {rel.as_posix()}\n- label: {label}\n",
            )
        except Exception:
            pass

        await sio.emit('session_sketch_saved', {'id': entry_id, 'file': str(path)}, room=sid)
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to save sketch: {e}"}, room=sid)


@sio.event
async def study_select(sid, data):
    try:
        folder = (data or {}).get("folder") or ""
        file = (data or {}).get("file") or ""
        rel_path = (data or {}).get("path") or ""
        if not rel_path:
            return

        safe_path = _safe_study_path(rel_path)
        if not safe_path.exists():
            return

        answer_keys = []
        try:
            for f in safe_path.parent.glob("*.pdf"):
                if "answer key" in f.name.lower():
                    answer_keys.append(f)
        except Exception:
            answer_keys = []

        if audio_loop and getattr(audio_loop, "session", None):
            ak_list = ", ".join([str(p) for p in answer_keys]) if answer_keys else "(none found)"
            msg = (
                "System Notification: [Study] "
                f"User opened: {folder}/{file}. "
                f"Answer key files (for your use only): {ak_list}. "
                "Do not reveal the answer key unless the user explicitly asks. "
                "You can create answer fields with the study_set_fields tool and change pages with study_set_page. "
                "When asked about page contents, rely on the provided page text snippet and/or attached page image; if none is available, say you cannot see that page."
            )
            if hasattr(audio_loop, "send_system_message"):
                await audio_loop.send_system_message(msg, end_of_turn=False)
            else:
                await audio_loop.session.send(input=msg, end_of_turn=False)
    except Exception as e:
        await sio.emit('error', {'msg': f"Study select failed: {e}"}, room=sid)


@sio.event
async def study_answers_submit(sid, data):
    try:
        if not audio_loop or not getattr(audio_loop, "session", None):
            return
        folder = (data or {}).get("folder") or ""
        file = (data or {}).get("file") or ""
        fields = (data or {}).get("fields") or {}
        notes = (data or {}).get("notes") or ""
        lines = [f"Study answers for: {folder}/{file}"]
        if isinstance(fields, dict) and fields:
            for k, v in fields.items():
                if v is None or str(v).strip() == "":
                    continue
                lines.append(f"- {k}: {v}")
        if notes:
            lines.append("")
            lines.append(f"Notes: {notes}")
        msg = "System Notification: [Study] " + "\n".join(lines)
        if hasattr(audio_loop, "send_system_message"):
            await audio_loop.send_system_message(msg, end_of_turn=False)
        else:
            await audio_loop.session.send(input=msg, end_of_turn=False)
    except Exception as e:
        await sio.emit('error', {'msg': f"Study submit failed: {e}"}, room=sid)


@sio.event
async def study_page_user(sid, data):
    try:
        if not audio_loop or not getattr(audio_loop, "session", None):
            return
        folder = (data or {}).get("folder") or ""
        file = (data or {}).get("file") or ""
        page = (data or {}).get("page")
        page_label = (data or {}).get("page_label") or ""
        text = (data or {}).get("text") or ""
        if not page:
            return
        print(f"[SERVER DEBUG] [Study] Page update: {folder}/{file} page={page} label={page_label} text_len={len(text or '')}")
        snippet = ""
        if text:
            cleaned = " ".join(str(text).split())
            snippet = cleaned[:1200] + ("..." if len(cleaned) > 1200 else "")
        STUDY_READER.update_page_text(
            text=snippet or "",
            meta={"folder": folder, "file": file, "page": page, "page_label": page_label},
        )
        label_note = f" (book page {page_label})" if page_label else ""
        msg = f"System Notification: [Study] User is viewing page {page} of {folder}/{file}{label_note}."
        if snippet:
            msg += f" Page text snippet: {snippet}"
        else:
            msg += " Page text snippet: (unavailable)"
        if hasattr(audio_loop, "send_system_message"):
            await audio_loop.send_system_message(msg, end_of_turn=False)
        else:
            await audio_loop.session.send(input=msg, end_of_turn=False)
    except Exception as e:
        await sio.emit('error', {'msg': f"Study page update failed: {e}"}, room=sid)


@sio.event
async def study_page_image(sid, data):
    try:
        if not audio_loop or not getattr(audio_loop, "session", None):
            return
        folder = (data or {}).get("folder") or ""
        file = (data or {}).get("file") or ""
        page = (data or {}).get("page")
        page_label = (data or {}).get("page_label") or ""
        mime_type = (data or {}).get("mime_type") or "image/jpeg"
        b64 = (data or {}).get("data") or ""
        if not page or not b64:
            return
        payload = {"mime_type": mime_type, "data": b64}
        STUDY_READER.update_page_image(
            payload=payload,
            meta={"folder": folder, "file": file, "page": page, "page_label": page_label},
        )
        print(f"[SERVER DEBUG] [Study] Page image received: {folder}/{file} page={page} label={page_label} mime={mime_type} bytes={len(b64)}")
        label_note = f" (book page {page_label})" if page_label else ""
        msg = (
            f"System Notification: [Study] Image of page {page} from {folder}/{file}{label_note}. "
            "Use this image to answer questions about this page only. "
            "Do not use prior knowledge. Do not guess if unreadable."
        )
        if hasattr(audio_loop, "send_system_message"):
            await audio_loop.send_system_message(msg, end_of_turn=False)
        else:
            await audio_loop.session.send(input=msg, end_of_turn=False)
        await audio_loop.session.send(input=payload, end_of_turn=False)

        # OCR in background (image-only PDFs)
        try:
            last_text, last_meta = STUDY_READER.get_latest_text(max_age_sec=20.0)
            if last_meta.get("page") == page and last_meta.get("file") == file and last_text:
                return
        except Exception:
            pass

        async def _run_ocr():
            try:
                import base64 as _b64
                raw = _b64.b64decode(b64)
                text, err = await asyncio.to_thread(ocr_image_bytes, raw)
                if not text:
                    if err:
                        print(f"[SERVER DEBUG] [Study OCR] Unavailable: {err}")
                    return
                cleaned = " ".join(str(text).split())
                snippet = cleaned[:2000] + ("..." if len(cleaned) > 2000 else "")
                STUDY_READER.update_page_text(
                    text=snippet,
                    meta={"folder": folder, "file": file, "page": page, "page_label": page_label},
                )
                ocr_msg = f"System Notification: [Study OCR] Extracted text snippet: {snippet}"
                if hasattr(audio_loop, "send_system_message"):
                    await audio_loop.send_system_message(ocr_msg, end_of_turn=False)
                else:
                    await audio_loop.session.send(input=ocr_msg, end_of_turn=False)
            except Exception as e:
                print(f"[SERVER DEBUG] [Study OCR] Failed: {e}")

        asyncio.create_task(_run_ocr())
    except Exception as e:
        await sio.emit('error', {'msg': f"Study page image failed: {e}"}, room=sid)


@sio.event
async def study_page_share(sid, data):
    """
    Explicit user action: share current page with Monika for deep reading + notes/exercises.
    Sends hi-res image, triggers OCR, and nudges model to create notes + exercises.
    """
    try:
        if not audio_loop or not getattr(audio_loop, "session", None):
            return
        folder = (data or {}).get("folder") or ""
        file = (data or {}).get("file") or ""
        page = (data or {}).get("page")
        page_label = (data or {}).get("page_label") or ""
        mime_type = (data or {}).get("mime_type") or "image/jpeg"
        b64 = (data or {}).get("data") or ""
        if not page or not b64:
            return
        payload = {"mime_type": mime_type, "data": b64}
        STUDY_READER.update_page_image(
            payload=payload,
            meta={"folder": folder, "file": file, "page": page, "page_label": page_label},
        )
        print(f"[SERVER DEBUG] [Study] Page shared: {folder}/{file} page={page} label={page_label} mime={mime_type} bytes={len(b64)}")
        label_note = f" (book page {page_label})" if page_label else ""
        msg = (
            "System Notification: [Study Share] The user explicitly shared this page for deep reading. "
            f"Current page: {page}{label_note} from {folder}/{file}. "
            "Read ONLY the attached image. Do not guess if unreadable. "
            "Then produce: (1) concise notes (4-8 bullets), (2) key vocabulary/phrases (jp + romaji + meaning if visible), "
            "and (3) 3-6 short exercises. Use study_set_notes to fill the scratchpad, and study_set_fields to create answer inputs. "
            "If text is unclear, ask the user to zoom/share again."
        )
        if hasattr(audio_loop, "send_system_message"):
            await audio_loop.send_system_message(msg, end_of_turn=False)
        else:
            await audio_loop.session.send(input=msg, end_of_turn=False)
        await audio_loop.session.send(input=payload, end_of_turn=False)

        async def _run_ocr_share():
            try:
                import base64 as _b64
                raw = _b64.b64decode(b64)
                text, err = await asyncio.to_thread(ocr_image_bytes, raw)
                if not text:
                    if err:
                        print(f"[SERVER DEBUG] [Study OCR] Unavailable: {err}")
                    return
                cleaned = " ".join(str(text).split())
                snippet = cleaned[:2000] + ("..." if len(cleaned) > 2000 else "")
                STUDY_READER.update_page_text(
                    text=snippet,
                    meta={"folder": folder, "file": file, "page": page, "page_label": page_label},
                )
                ocr_msg = f"System Notification: [Study OCR] Extracted text snippet: {snippet}"
                if hasattr(audio_loop, "send_system_message"):
                    await audio_loop.send_system_message(ocr_msg, end_of_turn=False)
                else:
                    await audio_loop.session.send(input=ocr_msg, end_of_turn=False)
            except Exception as e:
                print(f"[SERVER DEBUG] [Study OCR] Failed: {e}")

        asyncio.create_task(_run_ocr_share())
    except Exception as e:
        await sio.emit('error', {'msg': f"Study page share failed: {e}"}, room=sid)


@sio.event
async def study_page_tiles(sid, data):
    try:
        if not audio_loop or not getattr(audio_loop, "session", None):
            return
        folder = (data or {}).get("folder") or ""
        file = (data or {}).get("file") or ""
        page = (data or {}).get("page")
        page_label = (data or {}).get("page_label") or ""
        tiles = (data or {}).get("tiles") or []
        if not page or not tiles:
            return
        payloads = []
        for tile in tiles:
            mime = tile.get("mime_type") or "image/png"
            b64 = tile.get("data") or ""
            if not b64:
                continue
            payloads.append({"mime_type": mime, "data": b64})
        if not payloads:
            return
        STUDY_READER.update_page_tiles(
            payloads=payloads,
            meta={"folder": folder, "file": file, "page": page, "page_label": page_label},
        )
        label_note = f" (book page {page_label})" if page_label else ""
        msg = (
            f"System Notification: [Study] Received {len(payloads)} zoom tiles for page {page} "
            f"from {folder}/{file}{label_note}. Use them to read small text."
        )
        if hasattr(audio_loop, "send_system_message"):
            await audio_loop.send_system_message(msg, end_of_turn=False)
        else:
            await audio_loop.session.send(input=msg, end_of_turn=False)
        for payload in payloads:
            await audio_loop.session.send(input=payload, end_of_turn=False)
    except Exception as e:
        await sio.emit('error', {'msg': f"Study page tiles failed: {e}"}, room=sid)

@sio.event
async def memory_get_page(sid, data):
    try:
        path = (data or {}).get("path") or "notes.md"
        p = _resolve_memory_page(path)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("", encoding="utf-8")
        text = p.read_text(encoding="utf-8", errors="ignore")
        await sio.emit('memory_page', {'path': str(p), 'text': text}, room=sid)
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to read memory page: {e}"}, room=sid)

@sio.event
async def memory_list_pages(sid, data=None):
    try:
        pages = _list_memory_pages()
        await sio.emit('memory_pages', {'pages': pages}, room=sid)
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to list memory pages: {e}"}, room=sid)

@sio.event
async def memory_create_page(sid, data):
    try:
        path = (data or {}).get("path") or "notes.md"
        title = (data or {}).get("title") or ""
        p = _resolve_memory_page(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            if title:
                p.write_text(f"# {title}\n\n", encoding="utf-8")
            else:
                p.write_text("", encoding="utf-8")
        text = p.read_text(encoding="utf-8", errors="ignore")
        await sio.emit('memory_page', {'path': str(p), 'text': text}, room=sid)
        await sio.emit('memory_pages', {'pages': _list_memory_pages()}, room=sid)
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to create memory page: {e}"}, room=sid)

@sio.event
async def memory_set_page(sid, data):
    try:
        path = (data or {}).get("path") or "notes.md"
        content = (data or {}).get("content", "")
        p = _resolve_memory_page(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content or "", encoding="utf-8")
        await sio.emit('memory_page', {'path': str(p), 'text': content or ""}, room=sid)
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to write memory page: {e}"}, room=sid)

@sio.event
async def memory_delete_page(sid, data):
    try:
        path = (data or {}).get("path") or ""
        if not path:
            return
        p = _resolve_memory_page(path)
        if p.exists():
            p.unlink()
        await sio.emit('memory_pages', {'pages': _list_memory_pages()}, room=sid)
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to delete memory page: {e}"}, room=sid)

@sio.event
async def memory_rename_page(sid, data):
    try:
        path = (data or {}).get("path") or ""
        new_path = (data or {}).get("new_path") or ""
        title = (data or {}).get("title") or ""
        if not path:
            return
        src = _resolve_memory_page(path)
        if not src.exists():
            await sio.emit('error', {'msg': "Memory page not found."}, room=sid)
            return
        dest = _resolve_memory_page(new_path or path)
        if dest.exists() and dest != src:
            await sio.emit('error', {'msg': "Target note already exists."}, room=sid)
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest != src:
            src.rename(dest)
        text = dest.read_text(encoding="utf-8", errors="ignore")
        if title and dest.suffix.lower() == ".md":
            lines = text.splitlines()
            replaced = False
            for idx, line in enumerate(lines):
                if line.strip():
                    if line.lstrip().startswith("#"):
                        lines[idx] = f"# {title}"
                        replaced = True
                    break
            if not replaced:
                lines = [f"# {title}", ""] + lines
            text = "\n".join(lines)
            if text and not text.endswith("\n"):
                text += "\n"
            dest.write_text(text, encoding="utf-8")
        await sio.emit('memory_page', {'path': str(dest), 'text': text}, room=sid)
        await sio.emit('memory_pages', {'pages': _list_memory_pages()}, room=sid)
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to rename memory page: {e}"}, room=sid)

@sio.event
async def memory_append_page(sid, data):
    try:
        path = (data or {}).get("path") or "notes.md"
        content = (data or {}).get("content", "")
        p = _resolve_memory_page(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            if content and not content.startswith("\n"):
                f.write("\n")
            f.write(content)
            if content and not content.endswith("\n"):
                f.write("\n")
        text = p.read_text(encoding="utf-8", errors="ignore")
        await sio.emit('memory_page', {'path': str(p), 'text': text}, room=sid)
    except Exception as e:
        await sio.emit('error', {'msg': f"Failed to append memory page: {e}"}, room=sid)

@sio.event
async def upload_memory(sid, data):
    print(f"Received memory upload request")
    try:
        memory_text = data.get('memory', '')
        if not memory_text:
            print("No memory data provided.")
            return

        if not audio_loop:
             print("[SERVER DEBUG] [Error] Audio loop is None. Cannot load memory.")
             await sio.emit('error', {'msg': "System not ready (Audio Loop inactive)"}, room=sid)
             return
        
        if not audio_loop.session:
             print("[SERVER DEBUG] [Error] Session is None. Cannot load memory.")
             await sio.emit('error', {'msg': "System not ready (No active session)"}, room=sid)
             return

        # Send to model
        print("Sending memory context to model...")
        context_msg = f"System Notification: The user has uploaded a long-term memory file. Please load the following context into your understanding. The format is a text log of previous conversations:\n\n{memory_text}"
        
        await audio_loop.session.send(input=context_msg, end_of_turn=True)
        print("Memory context sent successfully.")
        await sio.emit('status', {'msg': 'Memory Loaded into Context'}, room=sid)

    except Exception as e:
        print(f"Error uploading memory: {e}")
        await sio.emit('error', {'msg': f"Failed to upload memory: {str(e)}"}, room=sid)

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
        
        # Merge with existing to preserve any manual overrides? 
        # For now, just overwrite with latest scan result + previously known if we want to be fancy,
        # but user asked for "Any new devices that are scanned are added there".
        # A simple full persistence of current state is safest.
        SETTINGS["kasa_devices"] = saved_devices
        save_settings()
        print(f"[SERVER] Saved {len(saved_devices)} Kasa devices to settings.")
        
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


# --------------------------------------------------------------------------------------
# Minecraft Bot Event Handlers
# --------------------------------------------------------------------------------------

@sio.event
async def minecraft_connect(sid, data=None):
    """Frontend requests to start the Minecraft bot."""
    global minecraft_bot_manager
    if not minecraft_bot_manager:
        await sio.emit('error', {'msg': 'Minecraft bot manager not initialized'}, room=sid)
        return
    
    try:
        print("[SERVER] [Minecraft] Starting bot connection...")
        success = await minecraft_bot_manager.start()
        if not success:
            await sio.emit('error', {'msg': 'Failed to start bot'}, room=sid)
            return
        
        status = minecraft_bot_manager.get_status()
        position = {'x': 0, 'y': 0, 'z': 0}
        if status.position:
            position = {'x': status.position.x, 'y': status.position.y, 'z': status.position.z}
        
        await sio.emit('minecraft_status', {
            'connected': True,
            'health': status.health,
            'hunger': status.hunger,
            'position': position,
            'dimension': status.dimension,
        }, room=sid)
        print("[SERVER] [Minecraft] Bot connected successfully.")
        
        # Notify model
        if audio_loop and audio_loop.session:
            try:
                await audio_loop.session.send(
                    input="System Notification: [Minecraft] The bot is now connected to the server. You can use minecraft_* tools to interact.",
                    end_of_turn=False
                )
            except Exception:
                pass
    except Exception as e:
        print(f"[SERVER] [Minecraft] Connection failed: {e}")
        await sio.emit('error', {'msg': f'Minecraft connection failed: {e}'}, room=sid)


@sio.event
async def minecraft_disconnect(sid, data=None):
    """Frontend requests to stop the Minecraft bot."""
    global minecraft_bot_manager
    if not minecraft_bot_manager:
        await sio.emit('error', {'msg': 'Minecraft bot manager not initialized'}, room=sid)
        return
    
    try:
        print("[SERVER] [Minecraft] Stopping bot...")
        await minecraft_bot_manager.stop()
        await sio.emit('minecraft_status', {'connected': False}, room=sid)
        print("[SERVER] [Minecraft] Bot disconnected.")
        
        # Notify model
        if audio_loop and audio_loop.session:
            try:
                await audio_loop.session.send(
                    input="System Notification: [Minecraft] The bot has disconnected from the server.",
                    end_of_turn=False
                )
            except Exception:
                pass
    except Exception as e:
        print(f"[SERVER] [Minecraft] Disconnection error: {e}")
        await sio.emit('error', {'msg': f'Minecraft disconnection error: {e}'}, room=sid)


@sio.event
async def minecraft_action(sid, data):
    """Frontend sends a minecraft action to execute."""
    global minecraft_bot_manager
    if not minecraft_bot_manager:
        await sio.emit('error', {'msg': 'Minecraft bot manager not initialized'}, room=sid)
        return
    
    action_name = (data or {}).get('action')
    params = (data or {}).get('params') or {}
    
    if not action_name:
        await sio.emit('error', {'msg': 'Missing action name'}, room=sid)
        return
    
    try:
        print(f"[SERVER] [Minecraft] Executing action: {action_name} with params {params}")
        result = await minecraft_bot_manager.send_action(action_name, params)
        success = bool(result.get('success')) if isinstance(result, dict) else bool(result)
        await sio.emit('minecraft_action_result', {
            'action': action_name,
            'success': success,
            'result': result.get('message') if isinstance(result, dict) else ('Action sent to bot' if success else None),
            'data': result.get('data') if isinstance(result, dict) else None,
            'error': result.get('error') if isinstance(result, dict) else (None if success else 'Failed to send action to bot subprocess'),
        }, room=sid)
    except Exception as e:
        print(f"[SERVER] [Minecraft] Action failed: {e}")
        await sio.emit('minecraft_action_result', {
            'action': action_name,
            'success': False,
            'error': str(e),
        }, room=sid)


@sio.event
async def minecraft_query_status(sid, data=None):
    """Frontend requests current bot status."""
    global minecraft_bot_manager
    if not minecraft_bot_manager:
        await sio.emit('error', {'msg': 'Minecraft bot manager not initialized'}, room=sid)
        return
    
    try:
        status = minecraft_bot_manager.get_status()
        perception = minecraft_bot_manager.get_perception_snapshot()
        
        position = {'x': 0, 'y': 0, 'z': 0}
        if status.position and isinstance(status.position, dict):
            position = {
                'x': status.position.get('x', 0),
                'y': status.position.get('y', 0),
                'z': status.position.get('z', 0)
            }
        
        await sio.emit('minecraft_status', {
            'connected': status.is_connected,
            'health': status.health,
            'hunger': status.hunger,
            'position': position,
            'dimension': status.dimension,
            'inventory': status.inventory,
            'perception': perception,
        }, room=sid)
    except Exception as e:
        print(f"[SERVER] [Minecraft] Status query failed: {e}")
        await sio.emit('error', {'msg': f'Minecraft status query failed: {e}'}, room=sid)


@sio.event
async def minecraft_connect_to_server(sid, data=None, callback=None):
    """Frontend sends a request to connect to a different Minecraft server."""
    global minecraft_bot_manager
    if not minecraft_bot_manager:
        result = {'success': False, 'message': 'Minecraft bot manager not initialized'}
        if callback:
            callback(result)
        return
    
    host = (data or {}).get('host')
    port = (data or {}).get('port', 25565)
    
    if not host:
        result = {'success': False, 'message': 'Missing host parameter'}
        if callback:
            callback(result)
        return
    
    try:
        print(f"[SERVER] [Minecraft] Connecting to {host}:{port}...")
        
        # Stop current connection
        await minecraft_bot_manager.stop()
        await asyncio.sleep(0.5)
        
        # Update connection parameters
        minecraft_bot_manager.host = host
        minecraft_bot_manager.port = port
        
        # Reconnect to new server
        success = await minecraft_bot_manager.start()
        
        if success:
            result = {'success': True, 'message': f'Connected to {host}:{port}'}
            print(f"[SERVER] [Minecraft] Successfully connected to {host}:{port}")
            
            # Notify model
            if audio_loop and audio_loop.session:
                try:
                    await audio_loop.session.send(
                        input=f"System Notification: [Minecraft] Connected to server {host}:{port}. You can now play!",
                        end_of_turn=False
                    )
                except Exception:
                    pass
        else:
            result = {'success': False, 'message': f'Failed to connect to {host}:{port}. Check server is running and version matches.'}
            print(f"[SERVER] [Minecraft] Failed to connect to {host}:{port}")
        
        if callback:
            callback(result)
            
    except Exception as e:
        result = {'success': False, 'message': f'Connection error: {str(e)}'}
        print(f"[SERVER] [Minecraft] Connection to {host}:{port} failed: {e}")
        if callback:
            callback(result)


if __name__ == "__main__":
    uvicorn.run(
        "server:app_socketio", 
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
