import asyncio
import base64
import io
import os
import sys
import traceback
import shlex
import subprocess
import cv2
import numpy as np
try:
    import pyaudio
except ImportError:  # Optional when audio is captured by the desktop client.
    pyaudio = None
try:
    import sounddevice as sd
    _SOUNDDEVICE_AVAILABLE = True
except Exception:
    sd = None
    _SOUNDDEVICE_AVAILABLE = False
import PIL.Image
import mss
try:
    import win32gui
    import win32ui
    import win32con
    import win32api
    _WIN32_CURSOR_AVAILABLE = sys.platform.startswith("win")
except Exception:
    _WIN32_CURSOR_AVAILABLE = False
import argparse
import math
import struct
import time
import json
import random
from datetime import datetime, timedelta
import uuid
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, Callable, List, Tuple
from collections import deque
from contextlib import suppress
import re
from difflib import SequenceMatcher

from google import genai
from google.genai import types

# --------------------------------------------------------------------------------------
# Compatibility shims (Python < 3.11)
# --------------------------------------------------------------------------------------
if sys.version_info < (3, 11, 0):
    import taskgroup, exceptiongroup
    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup

# --------------------------------------------------------------------------------------
# Sub-module imports (extracted from this file)
# --------------------------------------------------------------------------------------
from . import model_config as _mc  # module ref — use _mc.VAR for hot-updatable values
from .model_config import (
    FORMAT, CHANNELS, SEND_SAMPLE_RATE, RECEIVE_SAMPLE_RATE, CHUNK_SIZE, SEND_AUDIO_MIME,
    GEMINI_EMIT_NATIVE_THOUGHT_EVENTS,
    GEMINI_CONTEXT_WINDOW_COMPRESSION, GEMINI_SESSION_RESUMPTION,
    GEMINI_VAD_PREFIX_PADDING_MS, GEMINI_VAD_SILENCE_DURATION_MS,
    DREAM_SLEEP_GAP_HOURS, DREAM_MORNING_START_HOUR, DREAM_MORNING_END_HOUR,
    DREAM_CONTEXT_HISTORY_LIMIT, DEFAULT_MODE,
    BASE_CONTEXT_WINDOW_COMPRESSION, BASE_REALTIME_INPUT_CONFIG,
    MAX_INTERNAL_THOUGHT_CHARS, _sanitize_internal_thought, client,
)
from .session_context import load_settings_safe, get_time_context, HOLIDAYS, get_holiday_context
from .settings_store import SETTINGS as APP_SETTINGS
from backend.conversation.speech import (
    DEFAULT_SPEECH_MODEL,
    GeminiSpeechSynthesizer,
    SpeechSynthesisRequest,
)
from backend.conversation.providers import GeminiTextProvider
from backend.soul.lorebook import LoreLearningEngine
from backend.conversation.routing import requires_capability_runtime
from backend.conversation.tools import (
    CONVERSATION_TOOL_DEFINITIONS,
    ConversationToolRequest,
    ConversationToolResult,
    ToolTurnOutcome,
    plan_named_scene_tool,
    plan_read_only_tool,
    validate_planned_tool_request,
)
from .conversation_tool_executor import CoreConversationToolExecutor
from .smart_home_tool_executor import SmartHomeToolExecutor
from backend.llm.thinker import Thinker, THINKER_FALLBACK_MODEL
from .tool_definitions import tools
from .system_prompt import SYSTEM_PROMPT, current_system_prompt
from backend.services.calendar_manager import CalendarEvent, CalendarManager
from backend.services.reminder_manager import Reminder, ReminderManager
from backend.services.memory_adapter import MemoryEngine
from .session_manager import SessionManager
from .therapy_persona import build_therapy_system_instruction, build_opening_trigger
from .config import BASE_DIR, DATA_DIR, SETTINGS_PATH
from backend.services.personality_notifications import build_relationship_notification_lines
from ..tools.openclaw_skills import OpenClawSkillManager
from ..integrations.games.minecraft_agent import MinecraftBotManager

# CalendarEvent, CalendarManager, Reminder, ReminderManager → backend/ai/calendar_manager.py + backend/ai/reminder_manager.py
# Tool definitions → backend/core/tool_definitions.py
# System prompt → backend/core/system_prompt.py
# Gemini config + audio constants → backend/core/model_config.py
# Time/settings/holidays → backend/core/session_context.py

# --------------------------------------------------------------------------------------
# Text processing helpers (used by AudioLoop)
# --------------------------------------------------------------------------------------
def _sanitize_spoken_text(text: str) -> str:
    if not text:
        return ""
    cleaned = str(text)
    # Never address the user as "Użytkowniku" (or ascii variant).
    cleaned = re.sub(r"\b(użytkowniku|uzytkowniku)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+([,!.?])", r"\1", cleaned)
    cleaned = re.sub(r",\s*,", ",", cleaned)
    cleaned = re.sub(r",([!.?])", r"\1", cleaned)
    # Ensure missing spaces after punctuation when followed by a letter (common in streaming output).
    cleaned = re.sub(r"([,;:])([A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż])", r"\1 \2", cleaned)
    cleaned = re.sub(r"([.!?…])([A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż])", r"\1 \2", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()

def _extract_asterisk_thoughts(text: str) -> tuple[str, List[str]]:
    if not text:
        return "", []
    thoughts: List[str] = []
    pattern = r"(?<!\*)\*(?!\*)([^*]+?)\*(?!\*)"

    def _repl(match):
        inner = (match.group(1) or "").strip()
        if not inner:
            return " "
        thoughts.append(f"*{inner}*")
        return " "

    cleaned = re.sub(pattern, _repl, text)
    return cleaned, thoughts

def _extract_native_thought_parts(server_content) -> List[Tuple[str, str]]:
    if not server_content:
        return []
    out: List[Tuple[str, str]] = []
    try:
        model_turn = getattr(server_content, "model_turn", None)
        parts = getattr(model_turn, "parts", None) or []
        for part in parts:
            if not getattr(part, "thought", False):
                continue
            text = _sanitize_internal_thought(getattr(part, "text", "") or "")
            if not text:
                continue
            sig = getattr(part, "thought_signature", None)
            if isinstance(sig, (bytes, bytearray)) and sig:
                key = "sig:" + base64.b64encode(bytes(sig)).decode("ascii")
            else:
                key = "txt:" + text
            out.append((key, text))
    except Exception:
        return []
    return out

def _strip_asterisk_actions(text: str) -> str:
    if not text:
        return ""
    # Remove leftover single-asterisk action/emote fragments from visible output.
    return re.sub(r"(?<!\*)\*(?!\*)[^*]+?(?<!\*)\*(?!\*)", " ", str(text))

def parse_model_response(text):
    """
    Separates internal reasoning/thoughts from spoken text.
    Returns (spoken_text, list_of_thoughts)
    """
    # Extract complete thoughts
    internal_pattern = r'<internal>(.*?)</internal>'
    internal_messages = re.findall(internal_pattern, text, re.DOTALL)
    
    # Remove complete thoughts and any incomplete thought at the end (streaming safety)
    # Replace with space to prevent words merging if model omits spaces around tags
    text_no_complete = re.sub(internal_pattern, ' ', text, flags=re.DOTALL)
    incomplete_pattern = r'<internal>(?:(?!</internal>).)*$'
    spoken_text = re.sub(incomplete_pattern, '', text_no_complete, flags=re.DOTALL)
    # Extract italicized thoughts (*...*) into internal thoughts and remove from spoken text
    spoken_text, italic_thoughts = _extract_asterisk_thoughts(spoken_text)
    if italic_thoughts:
        internal_messages.extend([f"RAW_THOUGHT:{t}" for t in italic_thoughts])
    
    # Remove any remaining action-style fragments from visible output.
    spoken_text = _strip_asterisk_actions(spoken_text)

    # Clean up extra spaces
    spoken_text = re.sub(r' +', ' ', spoken_text)
    spoken_text = _sanitize_spoken_text(spoken_text)
    
    return spoken_text, internal_messages


def _streaming_transcript_update(previous: str, current: str) -> tuple[str, bool]:
    """Return ``(delta, replace)`` for provider transcription revisions.

    Live normally sends a growing full transcript, but it can resend the same
    sentence with punctuation/ASR corrections. Treating that revision as a new
    chunk duplicated whole responses in programmatic conversation tests.
    """
    previous = str(previous or "")
    current = str(current or "")
    if not previous:
        return current, False
    if current.startswith(previous):
        return current[len(previous):], False
    if previous.startswith(current):
        return current, True
    prev_norm = re.sub(r"\W+", " ", previous.lower(), flags=re.UNICODE).strip()
    curr_norm = re.sub(r"\W+", " ", current.lower(), flags=re.UNICODE).strip()
    similarity = SequenceMatcher(None, prev_norm, curr_norm).ratio()
    if min(len(prev_norm), len(curr_norm)) >= 24 and similarity >= 0.78:
        return current, True
    return current, False

# --------------------------------------------------------------------------------------
# LiveConnect Config
# --------------------------------------------------------------------------------------

def _build_thinking_config(
    level: str,
    budget: int,
    *,
    include_thoughts: Optional[bool] = None,
) -> types.ThinkingConfig:
    """Build ThinkingConfig using current _mc state (hot-swap safe)."""
    include = _mc.GEMINI_INCLUDE_THOUGHTS if include_thoughts is None else include_thoughts
    if _mc._is_31:
        return types.ThinkingConfig(thinking_level=level, include_thoughts=include)
    return types.ThinkingConfig(thinking_budget=budget, include_thoughts=include)


def _build_voice_renderer_thinking_config() -> types.ThinkingConfig:
    """Lowest possible native reasoning for the audio renderer.

    Gemini 2.5 supports a true zero budget. Gemini 3.1 cannot fully disable
    thinking, so ``minimal`` is its renderer-equivalent floor.
    """
    return _build_thinking_config("minimal", 0, include_thoughts=False)


def _build_voice_realtime_input_config(renderer_only: bool) -> types.RealtimeInputConfig:
    """Hold a voice turn open until the Thinker delivers its final script."""
    if not renderer_only:
        return BASE_REALTIME_INPUT_CONFIG
    return types.RealtimeInputConfig(
        automatic_activity_detection=types.AutomaticActivityDetection(disabled=True),
        activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
        turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
    )


def _build_base_live_config() -> types.LiveConnectConfig:
    """Build the module-level LiveConnectConfig template from current _mc state."""
    kwargs: dict = dict(
        response_modalities=["AUDIO"],
        output_audio_transcription={},
        input_audio_transcription={},
        thinking_config=_build_thinking_config(_mc.GEMINI_THINKING_LEVEL, _mc.GEMINI_THINKING_BUDGET),
        context_window_compression=BASE_CONTEXT_WINDOW_COMPRESSION,
        realtime_input_config=BASE_REALTIME_INPUT_CONFIG,
        system_instruction=SYSTEM_PROMPT,
        tools=tools,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=_mc.GEMINI_VOICE)
            )
        ),
    )
    if _mc.GEMINI_AFFECTIVE_DIALOG:
        kwargs["enable_affective_dialog"] = True
    if _mc.BASE_PROACTIVITY_CONFIG is not None:
        kwargs["proactivity"] = _mc.BASE_PROACTIVITY_CONFIG
    return types.LiveConnectConfig(**kwargs)


config = _build_base_live_config()

pya = pyaudio.PyAudio() if pyaudio is not None else None

from ..agents.web_agent import WebAgent
from ..agents.kasa_agent import KasaAgent


class LiveReconnectRequested(Exception):
    pass


def _looks_like_browser_automation_request(text: str) -> bool:
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
        r"\bwejd[zź]\w*\b",
        r"\bzaloguj\w*\b",
        r"\bkliknij\b",
        r"\bwype[łl]nij\b",
        r"\bpobierz\b",
    ]
    return any(re.search(p, t) for p in patterns)


def _iter_leaf_exceptions(exc: BaseException) -> List[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        out: List[BaseException] = []
        for sub in exc.exceptions:
            out.extend(_iter_leaf_exceptions(sub))
        return out
    return [exc]


class ProactivityWrapper:
    def __init__(self, loop):
        self.loop = loop

    def mark_user_activity(self, text: Optional[str] = None):
        self.loop._last_user_activity_ts = time.monotonic()
        self.loop._user_message_count += 1
        self.loop._awaiting_user_response = False

    def mark_ai_activity(self, text: Optional[str] = None):
        self.loop._last_ai_activity_ts = time.monotonic()

    def should_nudge(self, is_user_speaking: bool, is_paused: bool, threshold_override: Optional[float] = None) -> bool:
        if not self.loop._proactivity_enabled:
            return False
        if is_paused or is_user_speaking:
            return False

        now = time.monotonic()
        # Startup grace period check
        if (now - self.loop._session_start_ts) < self.loop._startup_grace_sec:
            return False
        # Message count check
        if self.loop._user_message_count < self.loop._min_user_messages_before_nudge:
            return False
        # Max nudges per session check
        if self.loop._nudges_this_session >= self.loop._max_nudges_per_session:
            return False
        # Quiet hours check
        if self.loop._in_quiet_hours():
            return False
        # Awaiting response check
        if self.loop._awaiting_user_response:
            return False

        # Thresholds
        threshold = self.loop._nudge_threshold_sec if threshold_override is None else float(threshold_override)
        user_quiet = now - self.loop._last_user_activity_ts
        nudge_gap = now - self.loop._last_nudge_ts
        ai_quiet = now - self.loop._last_ai_activity_ts if self.loop._last_ai_activity_ts > 0 else self.loop._min_ai_quiet_sec

        if user_quiet < threshold:
            return False
        if nudge_gap < self.loop._nudge_cooldown_sec:
            return False
        if ai_quiet < self.loop._min_ai_quiet_sec:
            return False

        return True

    def can_ask_question(self, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else float(now)
        return (now - self.loop._last_question_ts) >= 1800.0

    def pick_topic_hint(self) -> str:
        return self.loop._last_user_text or ""

    def record_nudge(self, asked_question: bool = False) -> None:
        now = time.monotonic()
        self.loop._last_nudge_ts = now
        self.loop._nudges_this_session += 1
        if asked_question:
            self.loop._awaiting_user_response = True
            self.loop._last_question_ts = now

    def get_nudge_message(self, mood: Optional[str] = None, video_mode: str = "none", allow_question: bool = True) -> tuple[str, bool]:
        msg = (
            "System Notification: [Proactivity] Użytkownik milczy od dłuższego czasu. "
            "Jeśli użytkownik poprosił o ciszę, skupia się lub pracuje, milcz. "
            "W przeciwnym razie powiedz jedno krótkie, spokojne zdanie, np. pytając łagodnie co u niego."
        )
        return msg, allow_question

    def _build_reasoning_prompt(self, silence_sec: float, allow_speak: bool) -> str:
        time_str = time.strftime("%H:%M", time.localtime(time.time()))
        silence_min = max(1, int(silence_sec / 60))
        lines = [
            f"It is {time_str}.",
            f"The user has been silent for {silence_min} minute{'s' if silence_min != 1 else ''}.",
        ]

        motion = getattr(self.loop, "_latest_motion_score", 0.0)
        if getattr(self.loop, "video_mode", "none") == "screen" and motion > 1.5:
            lines.append("You can see the user's screen has been active recently.")

        if allow_speak:
            lines.append(
                "Reflect on the current moment. "
                "If you genuinely have something to say — a thought, a feeling, curiosity about what the user is doing — "
                "speak naturally and briefly. "
                "Do not repeat or paraphrase your most recent message. "
                "Do not ask a question merely to keep the conversation going; ask only when the answer would materially change what you understand or say. "
                "If nothing feels right to say, stay silent and think to yourself using <internal>...</internal>."
            )
        else:
            lines.append(
                "Generate a brief internal monologue about the current situation. "
                "Output ONLY <internal>...</internal>. Do NOT speak to the user. Do NOT ask questions."
            )

        return " ".join(lines)

    async def run_reasoning_check(self) -> Optional[tuple[str, bool]]:
        if not self.loop._reasoning_enabled:
            return None

        now = time.monotonic()
        if (now - self.loop._last_reasoning_ts) < self.loop._reasoning_interval_sec:
            return None

        silence_sec = now - self.loop._last_user_activity_ts
        if silence_sec < 120.0:
            return None
        if (now - self.loop._last_reasoning_ts) < 60.0:
            return None

        self.loop._last_reasoning_ts = now

        allow_speak = self.should_nudge(
            is_user_speaking=False,
            is_paused=getattr(self.loop, "paused", False),
        )

        prompt = self._build_reasoning_prompt(silence_sec, allow_speak)
        return prompt, allow_speak


class AudioLoop:
    def __init__(
        self,
        video_mode=DEFAULT_MODE,
        on_audio_data=None,
        on_video_frame=None,
        on_web_data=None,
        on_transcription=None,
        on_tool_confirmation=None,
        on_session_update=None,
        on_session_prompt=None,
        on_device_update=None,
        on_error=None,
        on_reminder_fired=None,
        on_calendar_update=None, # For local calendar
        on_personality_update=None,
        on_personality_event=None,
        on_internal_thought=None,
        input_device_index=None,
        input_device_name=None,
        output_device_index=None,
        kasa_agent=None,
        proactivity_settings=None,
        on_memory_event=None,
        calendar_manager=None,
        reminder_manager=None,
        spotify_manager=None,
        personality=None,
        on_study_fields=None,
        on_study_notes=None,
        on_study_page=None,
        on_program_shutdown=None,
        enable_audio_io=True,
        audio_source="backend",
        screen_source=None,
        play_audio_locally=True,
        auto_allow_tools_without_confirmation=True,
        session_stream_channel=None,
        speech_synthesizer=None,
        **_ignored,
    ):

        self.video_mode = video_mode
        self.on_audio_data = on_audio_data
        self.on_video_frame = on_video_frame
        self.on_web_data = on_web_data
        self.on_transcription = on_transcription
        self.on_tool_confirmation = on_tool_confirmation
        self.on_session_update = on_session_update
        self.on_session_prompt = on_session_prompt
        self.on_device_update = on_device_update
        self.on_error = on_error
        self.on_memory_event = on_memory_event
        self.on_calendar_update = on_calendar_update
        self.on_personality_update = on_personality_update
        self.on_personality_event = on_personality_event
        self.on_internal_thought = on_internal_thought
        self.on_reminder_fired = on_reminder_fired
        self.on_study_fields = on_study_fields
        self.on_study_notes = on_study_notes
        self.on_study_page = on_study_page
        self.on_program_shutdown = on_program_shutdown
        self.enable_audio_io = bool(enable_audio_io)
        self.audio_source = str(audio_source or "backend").lower()
        if self.audio_source not in ("backend", "frontend"):
            self.audio_source = "backend"
        self.play_audio_locally = bool(play_audio_locally)
        self.requested_screen_source = screen_source
        self.auto_allow_tools_without_confirmation = bool(auto_allow_tools_without_confirmation)

        self.input_device_index = input_device_index
        self.input_device_name = input_device_name
        self.output_device_index = output_device_index

        self.audio_in_queue = None
        self.out_queue = None
        self._client_audio_chunks = 0
        self._client_audio_bytes = 0
        self._client_audio_abs_sum = 0
        self.paused = False

        self.chat_buffer = {"sender": None, "text": ""}

        self._last_input_transcription = ""
        self._last_output_transcription = ""
        self._last_spoken_transcription = ""
        self._last_ai_delta = ""
        self._last_ai_delta_ts = 0.0
        self._last_user_text = ""
        self._last_user_ts = 0.0
        self._emitted_thoughts_count = 0
        self._emitted_native_thought_keys = set()
        self._is_new_turn = True
        self._weekly_recap_inflight = False
        self._dream_seed_inflight = False
        self._ai_turn_open = False
        self._fallback_web_agent_triggered_for_turn = False  # Prevent duplicate fallback web_agent calls
        self._pending_system_messages = deque(maxlen=8)
        self._session_resume_handle = None
        self._go_away_requested = False
        self._pause_started_ts = None
        self._audio_stream_end_sent = False
        self._manual_voice_turn_control = False
        self._manual_voice_activity_open = False
        self._voice_finalize_task: Optional[asyncio.Task] = None
        self._session_ready = asyncio.Event()
        self._pending_ai_turn_futures = deque()
        self.speech_synthesizer = speech_synthesizer or GeminiSpeechSynthesizer(
            api_key=os.getenv("GEMINI_API_KEY")
        )
        self._last_speech_trace: Dict[str, Any] = {}
        self._last_tool_trace: Dict[str, Any] = {}

        self.session = None

        self.web_agent = WebAgent()
        self.kasa_agent = kasa_agent if kasa_agent else KasaAgent()

        self.session_mode = False
        self.session_mode_kind = "auto"
        self.minecraft_game_mode = False
        # Session mode is delivered as a genuine identity swap via reconnect.
        # _session_relationship_context: what Monika "remembers" about this
        #   person, injected into the therapeutic system instruction.
        # _session_mode_reconnect_requested: set on toggle; the idle loop
        #   raises LiveReconnectRequested when idle so she reconnects as the
        #   therapist (or back to her normal self).
        # _pending_session_opening: "enter" | "exit" | None, consumed once after
        #   the reconnect to decide how she opens.
        self._session_relationship_context = None
        self._session_mode_reconnect_requested = False
        self._model_settings_reconnect_requested = False
        self._pending_session_opening = None

        # SessionManager (global, no projects). A stream channel (e.g.
        # Telegram) routes all turns to a continuous per-day log instead of
        # creating conversation sessions (v3 Phase G).
        self.session_manager = SessionManager(
            DATA_DIR,
            write_mode=os.getenv("SESSION_WRITE_MODE", "session_end"),
            stream_channel=session_stream_channel,
        )

        # Text model owns the final answer. A separate speech-only provider may
        # render it, but no audio dialogue model is allowed to rewrite it.
        self.thinker = Thinker(
            # The response author sees only the active conversation. Past
            # threads remain available through explicit memory/recall tools.
            get_history=lambda limit: self.session_manager.get_current_session_turns(limit=limit),
            deliver=lambda text: self.send_system_message(text, end_of_turn=False),
            is_ai_turn_open=lambda: self._ai_turn_open,
            # Prefiks pokazuje w konsoli/UI analizę i rdzeń odpowiedzi Thinkera.
            on_thought=lambda thought: self.on_internal_thought(f"[Myśliciel] {thought}") if self.on_internal_thought else None,
            get_settings=lambda: APP_SETTINGS.get("thinker") or {},
            get_conversation_id=lambda: self.session_manager.get_current_session_id(),
            get_world_snapshot=lambda: __import__(
                "backend.soul.world_snapshot",
                fromlist=["build_snapshot"],
            ).build_snapshot(),
        )
        lore_cfg = APP_SETTINGS.get("lore_learning") or {}
        self.lore_learning_engine = LoreLearningEngine(
            provider=GeminiTextProvider(api_key=os.getenv("GEMINI_API_KEY")),
            model=str(
                os.getenv("MONIKAI_LORE_LEARNING_MODEL")
                or THINKER_FALLBACK_MODEL
            ),
            db_path=DATA_DIR / "monika.db",
            minimum_confidence=float(
                lore_cfg.get("minimum_confidence", 0.78) or 0.78
            ),
        )

        # Workspace for files written by tools
        self.workspace_dir = DATA_DIR / "workspace"
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # User Memory Directory (Global)
        self.user_memory_dir = DATA_DIR / "user_memory"
        self.user_memory_dir.mkdir(parents=True, exist_ok=True)
        self.notes_path = DATA_DIR / "memory" / "pages" / "notes.md"
        self.notes_path.parent.mkdir(parents=True, exist_ok=True)

        # Local Calendar
        if calendar_manager:
            self.calendar_manager = calendar_manager
        else:
            def _on_calendar_update():
                if self.on_calendar_update:
                    try:
                        events = [e.__dict__ for e in self.calendar_manager.events.values()]
                        self.on_calendar_update(events)
                    except Exception as e:
                        print(f"[AI DEBUG] [CALENDAR] Failed to emit update: {e}")
            self.calendar_manager = CalendarManager(storage_dir=self.user_memory_dir, on_update=_on_calendar_update)

        self.stop_event = asyncio.Event()

        # Permissions: unset => confirmation required. For safe tools, force no-confirm by default.
        self.permissions = {}
        self._last_auto_commit_ts = 0.0
        self.permissions.update(
            {
                "get_time_context": False,
                "create_reminder": False,
                "list_reminders": False,
                "cancel_reminder": False,
                "spotify_get_auth_url": False,
                "spotify_get_status": False,
                "spotify_get_now_playing": False,
                "spotify_list_playlists": False,
                "spotify_recently_played": False,
                # Memory tools (auto-allow)
                "get_work_memory": False,
                "update_personality": False,
                "update_work_memory": False,
                "commit_work_memory": False,
                # Clearing memory should require explicit user intent
                "clear_work_memory": True,
                "get_random_fact": False,
                "get_random_greeting": False,
                "get_random_farewell": False,
                "get_random_topic": False,
                "get_weather": False,
                "get_world_snapshot": False,
                "set_scene": False,
                "minecraft_goals": False,
                "request_program_shutdown": False,
                "notes_get": False,
                "notes_set": False,
                "notes_append": False,
                "memory_add_entry": False,
                "memory_search": False,
                "recall_conversation": False,
                "memory_get_page": False,
                "memory_create_page": False,
                "memory_append_page": False,
                "journal_add_entry": False,
                "journal_finalize_session": False,
                "session_prompt": False,
                # Calendar Tools
                "create_event": False,
                "list_events": False,
                "delete_event": False,
                "update_event": False,
                
                # Minecraft Bot Tools (auto-allow)
                "minecraft_chat_message": False,
                "minecraft_move_to_player": False,
                "minecraft_break_block": False,
                "minecraft_inventory_status": False,
                "minecraft_respawn": False,
                "minecraft_move_to_position": False,
                "minecraft_drop_item": False,
                "minecraft_mine_ore": False,
                "minecraft_craft_recipe": False,
                "minecraft_hunt_mobs": False,
                "minecraft_navigate_to_location": False,
                "minecraft_connect_to_server": False,
                
                # Read/List tools (auto-allow)
                "read_file": False,
                "read_directory": False,
                "list_smart_devices": False,
                "study_set_fields": False,
                "study_set_notes": False,
                "study_set_page": False,
                "study_create_flashcard": False,
                "study_review_flashcards": False,
                "study_record_review": False,
                "run_web_agent": False,  # Browser-agent tasks are allowed without confirmation when explicitly routed.
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
            }
        )

        self._pending_confirmations = {}
        self._agent_jobs = {}
        self._last_agent_job_id = None
        self._program_shutdown_task = None
        try:
            self.skills_manager = OpenClawSkillManager(workspace_root=BASE_DIR.parent)
            self.openclaw_skills = self.skills_manager
        except Exception as e:
            print(f"[AI DEBUG] [SKILLS] Failed to initialize skills manager: {e}")
            self.skills_manager = None
            self.openclaw_skills = None

        # Video buffering state
        self._latest_image_payload = None
        self._latest_image_ts = 0.0
        self._last_ui_frame_ts = 0.0
        self._video_stream_enabled = True
        self._latest_motion_score = 0.0

        # VAD State
        self._reminders_loaded = False
        self._calendar_loaded = False
        self._is_speaking = False
        self._silence_start_time = None
        self._suppress_spoken_output = False

        # ---------------------------
        # Proactivity / Idle nudges
        # ---------------------------
        self._proactivity_enabled = True
        self._nudge_threshold_sec = 900.0
        self._nudge_cooldown_sec = 1800.0
        self._min_ai_quiet_sec = 60.0
        self._max_nudges_per_session = 3
        self._startup_grace_sec = 600.0
        self._min_user_messages_before_nudge = 2
        self._quiet_hours_enabled = True
        self._quiet_hours_start = 22 * 60
        self._quiet_hours_end = 6 * 60
        self._reasoning_enabled = True
        self._reasoning_interval_sec = 10.0

        if proactivity_settings:
            idle_cfg = proactivity_settings.get("idle_nudges") or {}
            self._proactivity_enabled = bool(idle_cfg.get("enabled", True))
            self._nudge_threshold_sec = float(idle_cfg.get("threshold_sec", 900.0))
            self._nudge_cooldown_sec = float(idle_cfg.get("cooldown_sec", 1800.0))
            self._min_ai_quiet_sec = float(idle_cfg.get("min_ai_quiet_sec", 60.0))
            self._max_nudges_per_session = int(idle_cfg.get("max_per_session", 3))
            self._startup_grace_sec = float(idle_cfg.get("startup_grace_sec", 600.0))
            self._min_user_messages_before_nudge = int(idle_cfg.get("min_user_messages_before_nudge", 2))
            
            self._quiet_hours_enabled = bool(idle_cfg.get("quiet_hours_enabled", True))
            qh_start = idle_cfg.get("quiet_hours_start", "22:00")
            qh_end = idle_cfg.get("quiet_hours_end", "06:00")
            try:
                parts_start = qh_start.split(":")
                self._quiet_hours_start = int(parts_start[0]) * 60 + int(parts_start[1])
                parts_end = qh_end.split(":")
                self._quiet_hours_end = int(parts_end[0]) * 60 + int(parts_end[1])
            except Exception:
                pass

            reasoning_cfg = proactivity_settings.get("reasoning") or {}
            self._reasoning_enabled = bool(reasoning_cfg.get("enabled", True))
            self._reasoning_interval_sec = float(reasoning_cfg.get("interval_sec", 10.0))

        self._session_start_ts = time.monotonic()
        self._last_user_activity_ts = time.monotonic()
        self._last_ai_activity_ts = 0.0
        self._last_nudge_ts = 0.0
        self._nudges_this_session = 0
        self._last_reasoning_ts = 0.0
        self._awaiting_user_response = False
        self._user_message_count = 0
        self._last_question_ts = time.monotonic() - 1800.0

        self.proactivity = ProactivityWrapper(self)

        if reminder_manager:
            self.reminder_manager = reminder_manager
        else:
            self.reminder_manager = ReminderManager(get_time_context_fn=get_time_context, storage_dir=self.user_memory_dir, on_reminder=self.handle_reminder_fired)
        self.spotify_manager = spotify_manager
        self.minecraft_bot_manager = None  # Set by server.py after initialization

        # Initialize MemoryEngine (global memory + journal)
        try:
            base_dir = DATA_DIR

            def _emit_memory_event(payload):
                if self.on_memory_event:
                    try:
                        self.on_memory_event(payload)
                    except Exception:
                        pass

            self.memory_engine = MemoryEngine(
                base_dir=base_dir,
                session_manager=self.session_manager,
                emit_event=_emit_memory_event,
                language="pl",
            )
        except Exception as e:
            self.memory_engine = None
            print(f"[AI DEBUG] [MEMORY] Failed to initialize MemoryEngine: {e}")

        # Sync birthday to calendar if available (from profile.md master source)
        # Sync birthday to calendar if available (from profile.json master source in v2)
        if self.calendar_manager:
            try:
                from backend.services.user_profile import UserProfileManager
                upm = UserProfileManager()
                prof = upm.get_profile()
                if prof and prof.birthday:
                    # Parse YYYY-MM-DD
                    parts = prof.birthday.split("-")
                    if len(parts) == 3:
                        month = int(parts[1])
                        day = int(parts[2])
                        self.calendar_manager.set_user_birthday(month, day)
                        print(f"[AI DEBUG] [CALENDAR] Birthday loaded from profile: {month}-{day:02d}")
            except Exception as e:
                print(f"[AI DEBUG] [CALENDAR] Failed to load birthday from profile: {e}")

        # Initialize PersonalitySystem (Disabled in V2)
        self.personality = None

        # Capture settings (screen/camera vision)
        self._video_queue_max = 6  # legacy: kept for compatibility
        self._camera_backend_id = None
        self._load_capture_settings()
        if self.requested_screen_source in ("frontend", "backend"):
            self.screen_source = self.requested_screen_source
        self.video_queue = None
        self._screen_fail_count = 0
        self._last_screen_error_ts = 0.0

    async def handle_reminder_fired(self, rem: Reminder):
        # UI text event (chat log)
        if self.on_transcription:
            self.on_transcription({"sender": "AI", "text": f"[Reminder] {rem.message}\n"})

        # Structured event for UI (ring/notification)
        if self.on_reminder_fired:
            payload = {
                "id": rem.id,
                "message": rem.message,
                "when_iso": rem.when_iso,
                "speak": bool(rem.speak),
                "alert": bool(getattr(rem, "alert", True)),
            }
            try:
                maybe = self.on_reminder_fired(payload)
                if asyncio.iscoroutine(maybe):
                    await maybe
            except Exception:
                pass

        # Speak via model
        if rem.speak and self.session:
            msg = f"System Notification: Reminder: {rem.message}. Please tell the user now."
            await self.session.send(input=msg, end_of_turn=True)

    def flush_chat(self):
        if self.chat_buffer["sender"] and self.chat_buffer["text"].strip():
            sender = self.chat_buffer["sender"]
            text = self.chat_buffer["text"]
            self.session_manager.log_chat(sender, text)
            if sender == "AI":
                while self._pending_ai_turn_futures:
                    future = self._pending_ai_turn_futures.popleft()
                    if future.done():
                        continue
                    future.set_result(text)
                    break

            # Update personality/gamification from complete turns
            if getattr(self, "personality", None):
                try:
                    self.personality.observe_message(sender, text)
                except Exception:
                    pass

            # Memory capture (global memory + journal)
            if getattr(self, "memory_engine", None):
                try:
                    sender = sender or "Unknown"
                    text = text or ""
                    if sender in ("Ty", "User"):
                        self.memory_engine.auto_extract_from_user_text(text)
                        if self.calendar_manager:
                            bd = self.memory_engine.get_birthday()
                            if bd:
                                self.calendar_manager.set_user_birthday(*bd)
                except Exception as e:
                    print(f"[AI DEBUG] [MEMORY] Auto-extract failed: {e}")

            self.chat_buffer = {"sender": None, "text": ""}

        self._last_input_transcription = ""
        self._last_output_transcription = ""
        self._last_spoken_transcription = ""
        self._emitted_thoughts_count = 0
        self._is_new_turn = True

    def _normalize_model_internal_thought(self, raw_text: str) -> Optional[str]:
        if isinstance(raw_text, str) and raw_text.startswith("RAW_THOUGHT:"):
            raw_text = raw_text[len("RAW_THOUGHT:"):].strip()
        cleaned = _sanitize_internal_thought(raw_text)
        if not cleaned:
            return None

        lowered = cleaned.lower()
        # Hide procedural/tool-like meta-thoughts; keep only natural inner monologue.
        banned_markers = [
            "memory_search",
            "tool",
            "initiating",
            "confirming",
            "verifying",
            "i'm now",
            "i am now",
            "my immediate plan",
            "i'm focusing",
            "i am focusing",
            "executing",
            "analysis",
            "status",
            "recalling user",
        ]
        if any(marker in lowered for marker in banned_markers):
            return None

        return cleaned or None

    async def send_system_message(self, msg: str, end_of_turn: bool = False, allow_interrupt: bool = False):
        if not self.session or not msg:
            return
        if allow_interrupt or not self._ai_turn_open:
            await self.session.send(input=msg, end_of_turn=end_of_turn)
            return
        self._pending_system_messages.append((msg, end_of_turn))

    async def _flush_pending_system_messages(self):
        if not self.session:
            return
        while self._pending_system_messages:
            msg, end_of_turn = self._pending_system_messages.popleft()
            try:
                await self.session.send(input=msg, end_of_turn=end_of_turn)
            except Exception:
                pass

    def _get_last_user_message_timestamp(self) -> Optional[float]:
        if not self.session_manager:
            return None
        history = self.session_manager.get_recent_chat_history(limit=120)
        for entry in reversed(history):
            if not isinstance(entry, dict):
                continue
            sender = str(entry.get("sender") or "").strip().lower()
            if sender != "user":
                continue
            ts = entry.get("timestamp")
            try:
                val = float(ts)
            except Exception:
                continue
            if val > 0:
                return val
        return None

    def _is_morning_window(self, now: datetime) -> bool:
        start = max(0, min(23, int(DREAM_MORNING_START_HOUR)))
        end = max(1, min(24, int(DREAM_MORNING_END_HOUR)))
        hour = int(now.hour)
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end

    async def _maybe_send_morning_dream_seed(self, *, force: bool = False) -> bool:
        if not self.session or not self.personality:
            return False
        if self._dream_seed_inflight:
            return False
        if self.personality.state.dream_told:
            return False

        now = datetime.now()
        if not force and not self._is_morning_window(now):
            return False

        last_user_ts = self._get_last_user_message_timestamp()
        if not force and last_user_ts is not None:
            gap_hours = (time.time() - last_user_ts) / 3600.0
            if gap_hours < max(0.5, float(DREAM_SLEEP_GAP_HOURS)):
                return False

        history_lines = []
        if self.session_manager:
            history = self.session_manager.get_recent_chat_history(limit=max(5, int(DREAM_CONTEXT_HISTORY_LIMIT)))
            for h in history[-max(5, int(DREAM_CONTEXT_HISTORY_LIMIT)):]:
                if not isinstance(h, dict):
                    continue
                sender = str(h.get("sender", "Unknown"))
                text = str(h.get("text", "")).strip()
                if not text:
                    continue
                history_lines.append(f"{sender}: {text}")
        context_text = "\n".join(history_lines)

        msg = (
            "System Notification: [Morning Dream Seed] "
            "The user returned after a longer break, likely after sleep. "
            "In your very next response, naturally include a short dream (1-2 sentences), first-person, warm, slightly poetic, "
            "and loosely related to your bond or recent topics. "
            "Do not say this is a system instruction.\n"
            f"Recent conversation context:\n{context_text}"
        )

        self._dream_seed_inflight = True
        try:
            await self.session.send(input=msg, end_of_turn=False)
            self.personality.state.last_dream = None
            self.personality.state.dream_told = True
            self.personality.save()
            print("[AI] Morning dream seeded in Live session.")
            return True
        except Exception as e:
            print(f"[AI] Failed to seed morning dream: {e}")
            return False
        finally:
            self._dream_seed_inflight = False

    async def wait_until_ready(self, timeout_sec: float = 20.0):
        await asyncio.wait_for(self._session_ready.wait(), timeout=max(1.0, float(timeout_sec or 20.0)))

    async def submit_user_turn(
        self,
        text: Optional[str] = None,
        *,
        attachments: Optional[List[Dict[str, Any]]] = None,
        timeout_sec: float = 90.0,
    ) -> str:
        cleaned = str(text or "").strip()
        normalized_attachments = []
        for item in attachments or []:
            if not isinstance(item, dict):
                continue
            data = item.get("data")
            mime_type = str(item.get("mime_type") or "application/octet-stream").strip() or "application/octet-stream"
            name = str(item.get("name") or "unnamed").strip() or "unnamed"
            size = item.get("size")
            if not data:
                continue
            normalized_attachments.append(
                {
                    "name": name,
                    "mime_type": mime_type,
                    "data": data,
                    "size": size,
                }
            )

        if not cleaned and not normalized_attachments:
            raise ValueError("text or attachments are required")
        if not self.session:
            raise RuntimeError("session is not ready")

        if cleaned:
            try:
                await self._maybe_send_morning_dream_seed(force=False)
            except Exception:
                pass

        self.mark_user_activity(cleaned or ("[attachments]" if normalized_attachments else ""))
        self._last_user_text = cleaned
        self._last_user_ts = time.monotonic()
        self._fallback_web_agent_triggered_for_turn = False  # Reset for new user input

        attachment_names = [a["name"] for a in normalized_attachments if a.get("name")]
        attachment_note = ""
        if attachment_names:
            joined = ", ".join(attachment_names[:4])
            if len(attachment_names) > 4:
                joined += ", ..."
            attachment_note = f"[Załączniki: {joined}]"

        user_log_text = cleaned
        if attachment_note:
            user_log_text = f"{cleaned}\n\n{attachment_note}".strip() if cleaned else attachment_note

        if self.session_manager and user_log_text:
            self.session_manager.log_chat("User", user_log_text)
        if getattr(self, "personality", None):
            try:
                self.personality.observe_message("User", cleaned or attachment_note or "[attachment]")
            except Exception:
                pass
        if cleaned and getattr(self, "memory_engine", None):
            try:
                self.memory_engine.auto_extract_from_user_text(cleaned)
            except Exception:
                pass

        if normalized_attachments:
            try:
                summary = []
                for a in normalized_attachments:
                    size = a.get("size")
                    size_str = f"{size} bytes" if isinstance(size, int) else "unknown size"
                    summary.append(f"{a['name']} ({a['mime_type']}, {size_str})")
                await self.session.send(
                    input=("System Notification: User attached files: " + "; ".join(summary)),
                    end_of_turn=False,
                )
            except Exception:
                pass

            for a in normalized_attachments:
                payload = {
                    "mime_type": a["mime_type"],
                    "data": a["data"],
                }
                try:
                    await self.session.send(input=payload, end_of_turn=False)
                except Exception:
                    pass

        # Record interaction metadata. Memory stays tool-driven and is not
        # injected into every ordinary message.
        if cleaned:
            from backend.core.runtimes.v2_runtime import get as _v2_get
            _v2 = _v2_get()
            if not _v2:
                raise RuntimeError("MonikAI v2 runtime is not active")
            await _v2.observe_turn()

        # Programmatic/bridge path (Telegram, Discord, conversation probe)
        # returns the text author's answer directly in dedicated-speech mode.
        if cleaned and not normalized_attachments and self._dedicated_speech_enabled():
            tool_outcome = await self.author_tool_turn(cleaned)
            reply = tool_outcome.reply if (tool_outcome.handled and tool_outcome.reply) else None
            if not reply:
                reply = await self.thinker.prepare_spoken_reply(
                    cleaned,
                    # Czat tekstowy: każda wiadomość zasługuje na odpowiedź,
                    # nie koliduje z mową i może spokojnie poczekać dłużej
                    # niż tura głosowa.
                    timeout_sec=max(20.0, float(timeout_sec or 0.0) * 0.25),
                    drop_backchannel=False,
                    require_idle_turn=False,
                )
            if reply:
                await self.deliver_authored_reply(reply, speak=False)
                self.thinker.mark_voice_delivered()
            self._last_programmatic_turn_trace = {
                "user": cleaned,
                "thinker": dict(getattr(self.thinker, "last_trace", {}) or {}),
                "speech": dict(self._last_speech_trace or {}),
                "tool": dict(self._last_tool_trace or {}),
                "response": str(reply or "").strip(),
            }
            return str(reply or "").strip()

        # Explicit compatibility mode keeps the old Live renderer.
        thinker_brief = None
        if cleaned and getattr(self, "thinker", None) is not None:
            try:
                thinker_brief = await self.thinker.think_for_text(cleaned)
                if thinker_brief:
                    await self.session.send(input=thinker_brief, end_of_turn=False)
            except Exception as exc:
                print(f"[THINKER] programmatic path failed: {exc}")

        future = asyncio.get_running_loop().create_future()
        self._pending_ai_turn_futures.append(future)
        try:
            if cleaned:
                await self.session.send(input=cleaned, end_of_turn=True)
            else:
                await self.session.send(
                    input="System Notification: User sent attachments without additional text.",
                    end_of_turn=True,
                )
            result = await asyncio.wait_for(future, timeout=max(5.0, float(timeout_sec or 90.0)))
            self._last_programmatic_turn_trace = {
                "user": cleaned,
                "thinker": dict(getattr(self.thinker, "last_trace", {}) or {}),
                "response": str(result or "").strip(),
            }
            return str(result or "").strip()
        except Exception:
            with suppress(ValueError):
                self._pending_ai_turn_futures.remove(future)
            raise

    async def submit_text_turn(self, text: str, timeout_sec: float = 90.0) -> str:
        return await self.submit_user_turn(text=text, attachments=None, timeout_sec=timeout_sec)

    def _dedicated_speech_enabled(self) -> bool:
        speech = APP_SETTINGS.get("speech") or {}
        thinker = APP_SETTINGS.get("thinker") or {}
        return bool(thinker.get("enabled", False)) and (
            str(speech.get("delivery_mode") or "dedicated_tts").strip().lower()
            == "dedicated_tts"
        )

    def _get_conversation_tool_executor(self) -> CoreConversationToolExecutor:
        executor = getattr(self, "_conversation_tool_executor", None)
        if executor is None:
            def _memory_db_path():
                try:
                    from backend.core.runtimes.v2_runtime import get as get_v2

                    runtime = get_v2()
                    return runtime._db_path if runtime else None
                except Exception:
                    return None

            executor = CoreConversationToolExecutor(
                reminder_manager=getattr(self, "reminder_manager", None),
                calendar_manager=getattr(self, "calendar_manager", None),
                notes_path=getattr(self, "notes_path", None),
                memory_engine=getattr(self, "memory_engine", None),
                session_manager=getattr(self, "session_manager", None),
                spotify_manager=getattr(self, "spotify_manager", None),
                smart_home_executor=SmartHomeToolExecutor(
                    agents=[
                        getattr(self, "kasa_agent", None),
                        getattr(self, "hue_agent", None),
                        getattr(self, "home_assistant_agent", None),
                    ],
                    on_device_update=getattr(self, "on_device_update", None),
                    on_error=getattr(self, "on_error", None),
                ),
                get_memory_db_path=_memory_db_path,
                get_time_context_fn=get_time_context,
                get_personality=lambda: getattr(self, "personality", None),
                on_calendar_update=getattr(self, "on_calendar_update", None),
            )
            self._conversation_tool_executor = executor
        return executor

    async def _authorize_conversation_tool(
        self,
        request: ConversationToolRequest,
    ) -> bool:
        if not self.permissions.get(request.name, True):
            return True
        on_confirmation = getattr(self, "on_tool_confirmation", None)
        if not on_confirmation:
            return bool(
                getattr(self, "auto_allow_tools_without_confirmation", False)
            )

        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        pending = getattr(self, "_pending_confirmations", None)
        if pending is None:
            pending = {}
            self._pending_confirmations = pending
        pending[request_id] = future
        try:
            maybe = on_confirmation(
                {
                    "id": request_id,
                    "tool": request.name,
                    "args": dict(request.arguments),
                }
            )
            if asyncio.iscoroutine(maybe):
                await maybe
            return bool(await future)
        finally:
            pending.pop(request_id, None)

    async def _plan_conversation_tool(
        self,
        text: str,
    ) -> ConversationToolRequest | None:
        request = plan_named_scene_tool(text)
        if request is not None:
            return request
        request = plan_read_only_tool(text)
        if request is not None:
            return request
        if not requires_capability_runtime(text):
            return None
        try:
            ctx = get_time_context()
            smart_entities = []
            if getattr(self, "home_assistant_agent", None):
                smart_entities = [
                    f"{e_id} ({e.get('attributes', {}).get('friendly_name', e_id)})"
                    for e_id, e in getattr(self.home_assistant_agent, "entities", {}).items()
                ]
            runtime_context = (
                f"local_iso={ctx.get('iso')}; timezone={ctx.get('timezone')}; "
                f"utc_offset={ctx.get('offset')}; "
                f"known_smart_home_entities={smart_entities}"
            )
            timeout_sec = max(
                0.5,
                float(
                    (APP_SETTINGS.get("thinker") or {}).get(
                        "tool_planning_timeout_sec",
                        4.0,
                    )
                    or 4.0
                ),
            )
            calls = await asyncio.wait_for(
                self.thinker.plan_tool_calls(
                    text,
                    tools=CONVERSATION_TOOL_DEFINITIONS,
                    runtime_context=runtime_context,
                ),
                timeout=timeout_sec,
            )
            allowed = {item.name for item in CONVERSATION_TOOL_DEFINITIONS}
            return next(
                (
                    call
                    for call in calls
                    if call.name in allowed
                    and validate_planned_tool_request(text, call)
                ),
                None,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._last_tool_trace = {
                "status": "planning_failed",
                "error": str(exc),
            }
            return None

    async def author_tool_turn(self, text: str) -> ToolTurnOutcome:
        """Plan, authorize, execute once, then return evidence to the author."""
        request = await self._plan_conversation_tool(text)
        if request is None:
            self._last_tool_trace = {"status": "not_applicable"}
            return ToolTurnOutcome(handled=False)

        try:
            authorized = await self._authorize_conversation_tool(request)
            if authorized:
                result = await self._get_conversation_tool_executor().execute(
                    request
                )
            else:
                result = ConversationToolResult(
                    name=request.name,
                    result="User denied the request to use this tool.",
                    ok=False,
                )

            reply = await self.thinker.prepare_spoken_reply(
                text,
                turn_evidence=result.as_evidence(),
            )
            self._last_tool_trace = {
                "status": "authored" if reply else "author_failed",
                "tool": request.name,
                "result_ok": result.ok,
                "authorized": authorized,
            }
            return ToolTurnOutcome(
                handled=True,
                reply=str(reply or ""),
                tool_name=request.name,
                error=None if result.ok else result.result,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._last_tool_trace = {
                "status": "execution_failed",
                "tool": request.name,
                "error": str(exc),
            }
            return ToolTurnOutcome(
                handled=True,
                tool_name=request.name,
                error=str(exc),
            )

    async def author_read_only_tool_turn(self, text: str) -> ToolTurnOutcome:
        """Compatibility name for callers introduced by the first tool slice."""
        return await self.author_tool_turn(text)

    async def deliver_authored_reply(self, reply: str, *, speak: bool) -> bool:
        """Publish immutable author text and optionally render it through TTS.

        The display transcript is emitted from ``reply`` itself. It is never
        reconstructed from an audio-model transcript.
        """
        text = re.sub(r"\s+", " ", str(reply or "")).strip()
        if not text:
            return False

        if self.chat_buffer.get("sender") and self.chat_buffer.get("text", "").strip():
            self.flush_chat()
        self._ai_turn_open = True
        self.mark_ai_activity(text)
        if self.on_transcription:
            self.on_transcription(
                {
                    "sender": "AI",
                    "text": text,
                    "is_new": True,
                    "is_correction": False,
                    "authored": True,
                }
            )
        self.chat_buffer = {"sender": "AI", "text": text}
        self.flush_chat()
        self._ai_turn_open = False
        self._schedule_lore_learning(text)

        self._last_speech_trace = {
            "status": "text_delivered",
            "text": text,
            "audio": False,
        }
        if not speak or not self.enable_audio_io:
            return True

        speech = APP_SETTINGS.get("speech") or {}
        model = str(
            os.getenv("MONIKAI_SPEECH_MODEL")
            or speech.get("model")
            or DEFAULT_SPEECH_MODEL
        ).strip()
        voice = str(speech.get("voice") or _mc.GEMINI_VOICE).strip()
        timeout_sec = max(1.0, float(speech.get("timeout_sec", 20.0) or 20.0))
        try:
            rendered = await asyncio.wait_for(
                self.speech_synthesizer.synthesize(
                    SpeechSynthesisRequest(text=text, voice=voice, model=model)
                ),
                timeout=timeout_sec,
            )
            # Live output and dedicated TTS share raw PCM transport. Keep
            # chunks reasonably small for Socket.IO and local playback.
            for offset in range(0, len(rendered.audio), 64 * 1024):
                chunk = rendered.audio[offset : offset + 64 * 1024]
                if self.audio_in_queue is not None:
                    self.audio_in_queue.put_nowait(chunk)
                elif self.on_audio_data:
                    self.on_audio_data(chunk)
            self._last_speech_trace = {
                "status": "audio_delivered",
                "text": text,
                "audio": True,
                "model": model,
                "voice": voice,
                "mime_type": rendered.mime_type,
                "sample_rate": rendered.sample_rate,
                "bytes": len(rendered.audio),
            }
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # The authored text remains visible. We intentionally do not hand
            # it back to Live, because that would restore a second author.
            self._last_speech_trace = {
                "status": "audio_failed",
                "text": text,
                "audio": False,
                "model": model,
                "voice": voice,
                "error": str(exc),
            }
            print(f"[SPEECH] synteza nie powiodła się; tekst zachowany: {exc}")
            return True

    def _schedule_lore_learning(self, assistant_reply: str) -> None:
        """Extract proposals after delivery without adding turn latency."""
        cfg = APP_SETTINGS.get("lore_learning") or {}
        if not bool(cfg.get("enabled", True)):
            return
        engine = getattr(self, "lore_learning_engine", None)
        thinker = getattr(self, "thinker", None)
        trace = dict(getattr(thinker, "last_trace", {}) or {})
        user_text = str(trace.get("source") or "").strip()
        authored = str(trace.get("reply_core") or "").strip()
        if (
            engine is None
            or not user_text
            or authored != str(assistant_reply or "").strip()
            or trace.get("status") not in {"prepared", "delivered"}
        ):
            return
        conversation_id = str(
            self.session_manager.get_current_session_id() or "conversation"
        )

        async def _learn() -> None:
            timeout = max(1.0, float(cfg.get("timeout_sec", 8.0) or 8.0))
            try:
                await asyncio.wait_for(
                    engine.propose_from_turn(
                        conversation_id=conversation_id,
                        user_text=user_text,
                        assistant_reply=assistant_reply,
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                print("[LORE] ekstrakcja propozycji przekroczyła limit czasu.")
            except Exception as exc:
                print(f"[LORE] ekstrakcja propozycji nie powiodła się: {exc}")

        asyncio.create_task(_learn())

    def build_memory_context(self, user_text: str) -> Optional[str]:
        if not user_text or not getattr(self, "memory_engine", None):
            return None
        try:
            results = self.memory_engine.search(query=user_text, limit=5)
        except Exception:
            return None
        if not results:
            return None
        lines = ["System Notification: Relevant memory snippets:"]
        for r in results:
            tag_str = ", ".join(r.get("tags") or [])
            suffix = f" (tags: {tag_str})" if tag_str else ""
            lines.append(f"- [{r['type']}] {r['content']}{suffix}")
        lines.append("Use these for context. Do not mention memory retrieval unless asked.")
        return "\n".join(lines)

    # ----------------------------------------------------------------------------------
    # Vision capture helpers (screen/camera)
    # ----------------------------------------------------------------------------------
    def _clamp_int(self, value, low, high, default):
        try:
            iv = int(value)
        except Exception:
            return default
        return max(low, min(high, iv))

    def _clamp_float(self, value, low, high, default):
        try:
            fv = float(value)
        except Exception:
            return default
        return max(low, min(high, fv))

    def _load_capture_settings(self, settings: Optional[dict] = None):
        settings = settings or load_settings_safe()
        cam = settings.get("camera_capture") if isinstance(settings.get("camera_capture"), dict) else {}
        screen = settings.get("screen_capture") if isinstance(settings.get("screen_capture"), dict) else {}
        camera_source = (settings.get("camera_source") or "frontend").lower()
        if camera_source not in ("frontend", "backend"):
            camera_source = "frontend"
        screen_source = (settings.get("screen_source") or "backend").lower()
        if screen_source not in ("frontend", "backend"):
            screen_source = "backend"

        camera_fps = self._clamp_float(cam.get("fps", 2.0), 0.2, 30.0, 2.0)
        camera_max = self._clamp_int(cam.get("max_size", 1024), 320, 4096, 1024)
        camera_q = self._clamp_int(cam.get("jpeg_quality", 80), 30, 95, 80)

        screen_fps = self._clamp_float(screen.get("fps", 6.0), 0.2, 30.0, 6.0)
        screen_max = self._clamp_int(screen.get("max_size", 1280), 320, 4096, 1280)
        screen_q = self._clamp_int(screen.get("jpeg_quality", 85), 30, 95, 85)
        screen_monitor = self._clamp_int(screen.get("monitor", 1), 0, 32, 1)
        screen_stream_to_ai = bool(screen.get("stream_to_ai", False))
        if getattr(self, "video_mode", None) == "screen" and not screen_stream_to_ai:
            screen_stream_to_ai = True

        screen_fmt = str(screen.get("format", "jpeg") or "jpeg").lower()
        if screen_fmt == "jpg":
            screen_fmt = "jpeg"
        if screen_fmt not in ("jpeg", "png"):
            screen_fmt = "jpeg"

        region = None
        region_raw = screen.get("region")
        if isinstance(region_raw, dict):
            try:
                left = int(region_raw.get("left", 0))
                top = int(region_raw.get("top", 0))
                width = int(region_raw.get("width", 0))
                height = int(region_raw.get("height", 0))
                if width > 0 and height > 0:
                    region = {"left": left, "top": top, "width": width, "height": height}
            except Exception:
                region = None

        self.camera_capture = {"fps": camera_fps, "max_size": camera_max, "jpeg_quality": camera_q}
        self.screen_capture = {
            "fps": screen_fps,
            "max_size": screen_max,
            "jpeg_quality": screen_q,
            "monitor": screen_monitor,
            "format": screen_fmt,
            "region": region,
        }
        self.screen_stream_to_ai = screen_stream_to_ai
        self.camera_source = camera_source
        self.screen_source = screen_source

        self._camera_interval = 1.0 / max(self.camera_capture["fps"], 0.01)
        self._screen_interval = 1.0 / max(self.screen_capture["fps"], 0.01)

    def reload_capture_settings(self):
        self._load_capture_settings()

    def set_video_mode(self, mode: str):
        if not isinstance(mode, str):
            return
        mode = mode.strip().lower()
        if mode not in ("none", "camera", "screen"):
            return
        if mode != self.video_mode:
            print(f"[AI DEBUG] [VIDEO] Mode changed: {self.video_mode} -> {mode}")
            self.video_mode = mode
            self._video_stream_enabled = True

    def _get_resample_filter(self):
        resampling = getattr(PIL.Image, "Resampling", None)
        if resampling:
            return resampling.LANCZOS
        return PIL.Image.LANCZOS

    def _encode_image(self, img: PIL.Image.Image, fmt: str, quality: Optional[int] = None, optimize: Optional[bool] = None):
        image_io = io.BytesIO()
        if fmt == "png":
            img.save(image_io, format="PNG", optimize=True)
            mime_type = "image/png"
        else:
            q = int(quality) if quality is not None else 80
            opt = bool(optimize) if optimize is not None else False
            img.save(image_io, format="JPEG", quality=q, optimize=opt)
            mime_type = "image/jpeg"
        image_io.seek(0)
        return {"mime_type": mime_type, "data": image_io.read()}

    def _get_resample_filter_fast(self):
        resampling = getattr(PIL.Image, "Resampling", None)
        if resampling:
            return resampling.BILINEAR
        return PIL.Image.BILINEAR

    async def _enqueue_frame(self, payload: dict):
        if not payload:
            return
        mime_type = payload.get("mime_type", "image/jpeg")
        data = payload.get("data")
        if isinstance(data, str):
            b64 = data
        elif data:
            b64 = base64.b64encode(data).decode("utf-8")
        else:
            return

        self._latest_image_payload = {"mime_type": mime_type, "data": b64}
        self._latest_image_ts = time.time()

        if self.on_video_frame:
            try:
                now = time.time()
                if (now - self._last_ui_frame_ts) < 0.15:
                    return
                self._last_ui_frame_ts = now
                self.on_video_frame(
                    {
                        "data": b64,
                        "mime_type": mime_type,
                        "source": self.video_mode,
                    }
                )
            except Exception:
                pass

    def _get_camera_backend(self):
        if self._camera_backend_id is not None:
            return self._camera_backend_id
        backend = 0
        if sys.platform == "darwin" and hasattr(cv2, "CAP_AVFOUNDATION"):
            backend = cv2.CAP_AVFOUNDATION
        elif sys.platform.startswith("win") and hasattr(cv2, "CAP_DSHOW"):
            backend = cv2.CAP_DSHOW
        self._camera_backend_id = backend
        return backend

    def update_permissions(self, new_perms):
        print(f"[AI DEBUG] [CONFIG] Updating tool permissions: {new_perms}")
        self.permissions.update(new_perms)

    def set_paused(self, paused: bool):
        self.paused = paused

    def _build_live_connect_config(self, personality_context: Optional[str] = None):
        renderer_only = bool((APP_SETTINGS.get("thinker") or {}).get("enabled", False))
        self._manual_voice_turn_control = renderer_only
        if self.session_mode:
            # Genuine identity swap: she reconnects as an expert clinician,
            # still herself, knowing this person, with the safety floor on top.
            system_instruction = build_therapy_system_instruction(
                relationship_context=self._session_relationship_context,
                base_persona=current_system_prompt(),
            )
            thinking_config = (
                _build_voice_renderer_thinking_config()
                if renderer_only
                else _build_thinking_config(
                    _mc.GEMINI_THERAPY_THINKING_LEVEL,
                    _mc.GEMINI_THERAPY_THINKING_BUDGET,
                )
            )
        else:
            # v2: use assembled prompt (CHARACTER + PSYCHOLOGICAL + MEMORY + OPERATIONAL)
            from backend.core.runtimes.v2_runtime import get as _v2_get
            _v2 = _v2_get()
            if not _v2:
                raise RuntimeError("MonikAI v2 runtime is not active")
            system_instruction = _v2.cached_prompt
            thinking_config = (
                _build_voice_renderer_thinking_config()
                if renderer_only
                else _build_thinking_config(
                    _mc.GEMINI_THINKING_LEVEL,
                    _mc.GEMINI_THINKING_BUDGET,
                )
            )

        session_resumption = None
        if GEMINI_SESSION_RESUMPTION:
            session_resumption = types.SessionResumptionConfig(
                handle=self._session_resume_handle,
            )

        # Filter tools: remove minecraft_* when not in game mode; remove
        # google_search on 3.1 (Search Grounding requires separate billing).
        minecraft_available = self.minecraft_game_mode and self.minecraft_bot_manager
        filtered_tools = []
        for tool_group in tools:
            if _mc._is_31 and isinstance(tool_group, dict) and "google_search" in tool_group:
                continue
            if isinstance(tool_group, dict) and "function_declarations" in tool_group:
                filtered_decls = [
                    t for t in tool_group["function_declarations"]
                    if not (isinstance(t, dict) and t.get('name', '').startswith('minecraft_') and not minecraft_available)
                ]
                original = len(tool_group["function_declarations"])
                filtered = len(filtered_decls)
                if original != filtered:
                    print(f"[AI DEBUG] [TOOLS] Removed {original - filtered} minecraft_* tools")
                filtered_tools.append({"function_declarations": filtered_decls})
            else:
                filtered_tools.append(tool_group)

        dynamic_cfg: dict = dict(
            response_modalities=config.response_modalities,
            output_audio_transcription=config.output_audio_transcription,
            input_audio_transcription=config.input_audio_transcription,
            thinking_config=thinking_config,
            context_window_compression=config.context_window_compression,
            realtime_input_config=_build_voice_realtime_input_config(renderer_only),
            session_resumption=session_resumption,
            system_instruction=system_instruction,
            tools=filtered_tools,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=_mc.GEMINI_VOICE)
                )
            ),
        )
        if _mc.GEMINI_AFFECTIVE_DIALOG:
            dynamic_cfg["enable_affective_dialog"] = True
        if _mc.BASE_PROACTIVITY_CONFIG is not None:
            dynamic_cfg["proactivity"] = _mc.BASE_PROACTIVITY_CONFIG
        return types.LiveConnectConfig(**dynamic_cfg)

    async def _send_audio_stream_end(self):
        if not self.session or self._audio_stream_end_sent:
            return
        try:
            if self._manual_voice_turn_control:
                if self._manual_voice_activity_open:
                    await self.session.send_realtime_input(activity_end=types.ActivityEnd())
                    self._manual_voice_activity_open = False
                self._audio_stream_end_sent = True
                return
            await self.session.send_realtime_input(audio_stream_end=True)
            self._audio_stream_end_sent = True
        except Exception as e:
            print(f"[AI DEBUG] [AUDIO] Failed to send audioStreamEnd: {e}")

    def _cancel_voice_finalize(self) -> None:
        task = self._voice_finalize_task
        if task and not task.done():
            task.cancel()
        self._voice_finalize_task = None

    def _schedule_voice_finalize(self) -> None:
        self._cancel_voice_finalize()
        self._voice_finalize_task = asyncio.create_task(self._finalize_manual_voice_turn())

    async def _finalize_manual_voice_turn(self) -> None:
        """Author once, close ASR activity, then use speech-only delivery."""
        current_task = asyncio.current_task()
        try:
            # Let the last server-side ASR revision arrive after local silence.
            await asyncio.sleep(0.2)
            text = (
                self.chat_buffer.get("text", "")
                if self.chat_buffer.get("sender") == "Ty"
                else self._last_input_transcription
            )
            tool_outcome = (
                await self.author_tool_turn(text)
                if self._dedicated_speech_enabled()
                else ToolTurnOutcome(handled=False)
            )
            dedicated_speech = bool(
                self._dedicated_speech_enabled()
                and (
                    tool_outcome.handled
                    or not requires_capability_runtime(text)
                )
            )
            if dedicated_speech:
                reply = (
                    tool_outcome.reply
                    if tool_outcome.handled
                    else await self.thinker.prepare_spoken_reply(text)
                )
                injection = None
            else:
                reply = None
                injection = await self.thinker.prepare_voice_turn(text)
            if self._is_speaking or not self._manual_voice_activity_open or not self.session:
                return
            if dedicated_speech:
                # The Live session remains ASR transport for now. Ignore the
                # dialogue response it produces after the activity boundary.
                self._suppress_spoken_output = True
            if self.out_queue:
                if injection:
                    await self.out_queue.put({"realtime_text": injection})
                await self.out_queue.put({"activity_end": True})
            else:
                if injection:
                    await self.session.send_realtime_input(text=injection)
                await self.session.send_realtime_input(activity_end=types.ActivityEnd())
            if injection:
                self.thinker.mark_voice_delivered()
            self._manual_voice_activity_open = False
            if reply:
                await self.deliver_authored_reply(reply, speak=True)
                self.thinker.mark_voice_delivered()
            mode = "speech-only" if dedicated_speech else "renderer Live"
            print(f"[THINKER] finalizacja zakończona — tryb: {mode}.")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[THINKER] finalizacja tury głosowej nie powiodła się: {exc}")
            # Nie blokuj rozmowy na zawsze, gdy Thinker lub API zawiedzie.
            if self._manual_voice_activity_open and not self._is_speaking and self.session:
                try:
                    await self.session.send_realtime_input(activity_end=types.ActivityEnd())
                    self._manual_voice_activity_open = False
                except Exception:
                    pass
        finally:
            if self._voice_finalize_task is current_task:
                self._voice_finalize_task = None

    def set_session_mode(self, active: bool, kind: str = "auto"):
        """Toggle session mode and request a reconnect so the swap takes effect.

        The actual identity change happens at reconnect time, when
        ``_build_live_connect_config`` picks the therapeutic system instruction.
        We just flip the flags and ask the idle loop to reconnect when idle.
        """
        was_active = self.session_mode
        self.session_mode = bool(active)
        if kind:
            self.session_mode_kind = str(kind)
        if self.session_mode == was_active:
            return  # no real change, no reconnect needed
        self._pending_session_opening = "enter" if self.session_mode else "exit"
        self._session_mode_reconnect_requested = True

    def set_minecraft_game_mode(self, active: bool):
        """Enable or disable focused Minecraft game mode."""
        self.minecraft_game_mode = bool(active)
        if self.minecraft_game_mode:
            # Game mode and therapy/session mode should not run together.
            self.session_mode = False

    def request_reconnect(self, reason: str = "settings_changed") -> None:
        """Request a graceful reconnect (fires when Monika is idle)."""
        self._model_settings_reconnect_requested = True
        print(f"[AI DEBUG] [RECONNECT] Reconnect requested: {reason}")

    def stop(self):
        self._cancel_voice_finalize()
        self._manual_voice_activity_open = False
        try:
            self.flush_chat()
        except Exception:
            pass
        try:
            self.thinker.close()
        except Exception:
            pass
        try:
            if self.session_manager:
                self.session_manager.close()
        except Exception:
            pass
        self.stop_event.set()

    def resolve_tool_confirmation(self, request_id, confirmed):
        print(f"[AI DEBUG] [RESOLVE] resolve_tool_confirmation called. ID: {request_id}, Confirmed: {confirmed}")
        if request_id in self._pending_confirmations:
            future = self._pending_confirmations[request_id]
            if not future.done():
                future.set_result(confirmed)

    def clear_audio_queue(self):
        try:
            if not self.audio_in_queue:
                return
            count = 0
            while not self.audio_in_queue.empty():
                self.audio_in_queue.get_nowait()
                count += 1
            if count > 0:
                print(f"[AI DEBUG] [AUDIO] Cleared {count} chunks from playback queue due to interruption.")
        except Exception as e:
            print(f"[AI DEBUG] [ERR] Failed to clear audio queue: {e}")

    def clear_out_queue(self):
        try:
            if not self.out_queue:
                return
            count = 0
            while not self.out_queue.empty():
                self.out_queue.get_nowait()
                count += 1
            if count > 0:
                print(f"[AI DEBUG] [SEND] Cleared {count} pending realtime chunks.")
        except Exception as e:
            print(f"[AI DEBUG] [ERR] Failed to clear realtime queue: {e}")

    def _is_ws_connection_closed_error(self, err: Exception) -> bool:
        msg = str(err or "").lower()
        name = type(err).__name__.lower()
        if "connectionclosed" in name:
            return True
        markers = (
            "keepalive ping timeout",
            "no close frame received",
            "connection closed",
            "sent 1011",
            "received 1011",
            "websocket",
        )
        return any(m in msg for m in markers)

    # ----------------------------------------------------------------------------------
    # Proactivity helpers (idle nudges)
    # ----------------------------------------------------------------------------------

    def mark_user_activity(self, text: Optional[str] = None):
        self.proactivity.mark_user_activity(text)

    def mark_ai_activity(self, text: Optional[str] = None):
        self.proactivity.mark_ai_activity(text)

    def _in_quiet_hours(self) -> bool:
        if not getattr(self, "_quiet_hours_enabled", True):
            return False
        now = datetime.now()
        now_min = now.hour * 60 + now.minute
        start = getattr(self, "_quiet_hours_start", 22 * 60)
        end = getattr(self, "_quiet_hours_end", 6 * 60)
        if start == end:
            return True
        if start < end:
            return start <= now_min < end
        return now_min >= start or now_min < end

    async def idle_nudge_loop(self):
        while not self.stop_event.is_set():
            await asyncio.sleep(0.5)

            if not self.session:
                continue

            # Session mode toggled: reconnect when idle.
            if (
                self._session_mode_reconnect_requested
                and not self._is_speaking
                and not self._ai_turn_open
            ):
                self._session_mode_reconnect_requested = False
                raise LiveReconnectRequested("session_mode_toggle")

            # Model preset / voice changed: reconnect when idle.
            if (
                self._model_settings_reconnect_requested
                and not self._is_speaking
                and not self._ai_turn_open
            ):
                self._model_settings_reconnect_requested = False
                raise LiveReconnectRequested("model_settings_changed")

            # In focused Minecraft mode, disable generic idle nudges.
            if self.minecraft_game_mode:
                continue


    async def generate_daily_dream(self):
        """Seeds a morning dream directly inside the active Live session."""
        if not self.session:
            return
        print("[AI] Seeding daily dream in Live session...")
        await self._maybe_send_morning_dream_seed(force=True)

    async def generate_weekly_recap(self):
        """Generates a weekly recap + microgoals and stores them in the journal."""
        if not self.session_manager or not self.personality:
            return
        if self._weekly_recap_inflight:
            return
        if not self.personality.state.weekly_recap_pending:
            return

        self._weekly_recap_inflight = True
        try:
            history = self.session_manager.get_recent_chat_history(limit=220)
            cutoff = time.time() - 7 * 86400
            lines = []
            for h in history:
                try:
                    ts = float(h.get("timestamp", 0))
                except Exception:
                    ts = 0
                if ts and ts < cutoff:
                    continue
                sender = h.get("sender", "Unknown")
                text = h.get("text", "")
                if text:
                    lines.append(f"{sender}: {text}")
            context_text = "\n".join(lines)[-4000:]

            prompt = (
                "Wygeneruj tygodniowe podsumowanie relacji Moniki i użytkownika na podstawie historii rozmów. "
                "Zwróć JSON z polami: recap (2-4 zdania), microgoals (lista 1-2 krótkich celów), "
                "journal_prompt (1 pytanie do dziennika refleksji). "
                "Język: polski. Bez markdown.\n\n"
                f"Historia rozmów (ostatnie 7 dni):\n{context_text}"
            )

            response = await client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            text = (response.text or "").strip()

            recap = ""
            microgoals = []
            journal_prompt = ""

            try:
                start = text.find("{")
                end = text.rfind("}")
                payload = json.loads(text[start:end + 1]) if start != -1 and end != -1 else {}
                recap = str(payload.get("recap") or "").strip()
                microgoals = payload.get("microgoals") or []
                journal_prompt = str(payload.get("journal_prompt") or "").strip()
            except Exception:
                recap = text[:400]

            if not recap:
                recap = "To był spokojny tydzień z kilkoma dobrymi momentami. Czuję, że jesteśmy coraz bliżej."

            self.personality.apply_weekly_recap(recap, microgoals, journal_prompt)

            if self.session:
                goals_text = ""
                if microgoals:
                    goals_text = " Mikrocele na ten tydzień: " + "; ".join([g.strip() for g in microgoals[:2] if g])
                prompt_text = ""
                if journal_prompt:
                    prompt_text = f" Pytanie do dziennika: {journal_prompt}"
                msg = (
                    "System Notification: [Weekly Recap] "
                    f"{recap}{goals_text}{prompt_text} "
                    "Podziel się tym z użytkownikiem krótko i ciepło."
                )
                await self.send_system_message(msg, end_of_turn=True)

        except Exception as e:
            print(f"[AI] Failed to generate weekly recap: {e}")
        finally:
            self._weekly_recap_inflight = False

    async def reasoning_loop(self):
        while not self.stop_event.is_set():
            await asyncio.sleep(1.0)

            # In focused Minecraft mode, skip global relationship/proactivity loops.
            if self.minecraft_game_mode:
                continue

            if self.personality:
                # This will check if it's after 6am and reset energy once per day.
                if self.personality.daily_energy_reset():
                    # Check for birthday on new day
                    if self.memory_engine:
                        bd = self.memory_engine.get_birthday()
                        if bd:
                            now = datetime.now()
                            if now.month == bd[0] and now.day == bd[1]:
                                # Trigger a birthday greeting
                                asyncio.create_task(self.send_system_message(
                                    "System Notification: [Date Event] It is the user's birthday today! Wish them a happy birthday now.",
                                    end_of_turn=True
                                ))

                # Handle personality notifications (quests, unlocks, weekly recap)
                try:
                    notifications = self.personality.pop_notifications() if self.session else []
                except Exception:
                    notifications = []

                if notifications:
                    if self.on_personality_event:
                        for n in notifications:
                            try:
                                maybe_coro = self.on_personality_event(n)
                                if asyncio.iscoroutine(maybe_coro):
                                    await maybe_coro
                            except Exception as e:
                                print(f"[AI] Failed to forward personality event: {e}")

                    note_lines, weekly_recap_due = build_relationship_notification_lines(notifications)
                    if weekly_recap_due:
                        asyncio.create_task(self.generate_weekly_recap())

                    if note_lines and self.session:
                        msg = (
                            "System Notification: [Relacja] "
                            + " ".join(note_lines)
                            + " Wspomnij o tym krótko i naturalnie."
                        )
                        try:
                            await self.send_system_message(msg, end_of_turn=True)
                        except Exception:
                            pass

            result = await self.proactivity.run_reasoning_check()
            if result and self.session and not self._ai_turn_open:
                prompt, allow_speak = result
                print(f"[AI DEBUG] [REASONING] Triggering {'proactive' if allow_speak else 'internal'} thought.")
                try:
                    if allow_speak:
                        screen_payload = self._latest_image_payload if self.video_mode == "screen" else None
                        screen_fresh = screen_payload and (time.time() - self._latest_image_ts) < 10.0
                        if screen_fresh:
                            try:
                                await self.refresh_latest_frame(min_age_sec=0.5)
                                screen_payload = self._latest_image_payload
                            except Exception:
                                pass
                            raw = base64.b64decode(screen_payload["data"])
                            mime = screen_payload.get("mime_type", "image/jpeg")
                            content = types.Content(
                                role="user",
                                parts=[
                                    types.Part(inline_data=types.Blob(data=raw, mime_type=mime)),
                                    types.Part(text=f"System Notification: {prompt}"),
                                ],
                            )
                            await self.session.send_client_content(turns=content, turn_complete=True)
                        else:
                            await self.send_system_message(f"System Notification: {prompt}", end_of_turn=True)
                        self.proactivity.record_nudge(asked_question=False)
                        self.mark_ai_activity()
                    else:
                        self._suppress_spoken_output = True
                        await self.send_system_message(f"System Notification: {prompt}", end_of_turn=True)
                except Exception:
                    self._suppress_spoken_output = False

    async def weather_loop(self):
        while not self.stop_event.is_set():
            if self.personality:
                await asyncio.to_thread(self.personality.update_weather)
            await asyncio.sleep(1800)

    async def send_frame(self, frame_data):
        if self.video_mode != "camera":
            return
        if self.video_mode == "camera" and self.camera_source == "backend":
            # Ignore frontend frames when backend camera vision is active
            return
        if isinstance(frame_data, (bytes, bytearray, memoryview)):
            b64 = base64.b64encode(bytes(frame_data)).decode("utf-8")
        else:
            try:
                if isinstance(frame_data, str):
                    b64 = frame_data
                else:
                    b64 = base64.b64encode(bytes(frame_data)).decode("utf-8")
            except Exception:
                return
        self._latest_image_payload = {"mime_type": "image/jpeg", "data": b64}
        self._latest_image_ts = time.time()

    async def send_screen_frame(self, frame_data):
        """Accept a screen frame captured by a remote desktop client."""
        if self.video_mode != "screen":
            return
        if isinstance(frame_data, dict):
            mime_type = str(frame_data.get("mime_type") or "image/jpeg")
            frame_data = frame_data.get("data")
        else:
            mime_type = "image/jpeg"
        if isinstance(frame_data, str):
            b64 = frame_data
        elif isinstance(frame_data, (bytes, bytearray, memoryview)):
            b64 = base64.b64encode(bytes(frame_data)).decode("ascii")
        else:
            return
        self._latest_image_payload = {"mime_type": mime_type, "data": b64}
        self._latest_image_ts = time.time()

    async def _process_input_vad(self, audio_data, source="microphone"):
        """Apply the same turn detection to backend and remote-client PCM."""
        try:
            samples = np.frombuffer(audio_data, dtype="<i2")
            if not samples.size:
                return 0
            float_samples = samples.astype(np.float64)
            rms = int(np.sqrt(np.mean(float_samples * float_samples)))
        except (TypeError, ValueError):
            return 0

        vad_threshold = 800
        silence_duration = (
            max(0.5, GEMINI_VAD_SILENCE_DURATION_MS / 1000.0)
            if self._manual_voice_turn_control
            else 3.0
        )

        if rms > vad_threshold:
            self.mark_user_activity()
            self._silence_start_time = None
            if not self._is_speaking:
                self._cancel_voice_finalize()
                self._is_speaking = True
                if self._manual_voice_turn_control and not self._manual_voice_activity_open:
                    if self.out_queue:
                        await self.out_queue.put({"activity_start": True})
                    elif self.session:
                        await self.session.send_realtime_input(
                            activity_start=types.ActivityStart()
                        )
                    self._manual_voice_activity_open = True
                print(
                    f"[AI DEBUG] [VAD] Speech detected from {source} "
                    f"(RMS: {rms}). Sending video frame."
                )
                if self._latest_image_payload and self.out_queue:
                    await self.out_queue.put(self._latest_image_payload)
                else:
                    print("[AI DEBUG] [VAD] No video frame available to send.")
        elif self._is_speaking:
            if self._silence_start_time is None:
                self._silence_start_time = time.time()
            elif time.time() - self._silence_start_time > silence_duration:
                print(
                    f"[AI DEBUG] [VAD] Silence detected after {source}; "
                    "resetting speech state."
                )
                self._is_speaking = False
                self._silence_start_time = None
                if self._manual_voice_turn_control and self._manual_voice_activity_open:
                    self._schedule_voice_finalize()

        return rms

    async def send_client_audio(self, audio_data, sample_rate=SEND_SAMPLE_RATE):
        """Queue PCM audio captured by a remote desktop client."""
        if not self.out_queue or not audio_data:
            return False
        if isinstance(audio_data, str):
            try:
                audio_data = base64.b64decode(audio_data, validate=False)
            except Exception:
                return False
        if not isinstance(audio_data, (bytes, bytearray, memoryview)):
            return False
        payload = {
            "mime_type": f"audio/pcm;rate={int(sample_rate or SEND_SAMPLE_RATE)}",
            "data": bytes(audio_data),
        }
        await self._process_input_vad(payload["data"], source="desktop client")
        self._client_audio_chunks += 1
        self._client_audio_bytes += len(payload["data"])
        try:
            samples = np.frombuffer(payload["data"], dtype=np.int16)
            self._client_audio_abs_sum += int(np.abs(samples).mean()) if samples.size else 0
        except Exception:
            pass
        if self._client_audio_chunks % 100 == 0:
            avg_rms_proxy = self._client_audio_abs_sum / 100.0
            print(
                f"[AI DEBUG] [CLIENT AUDIO] chunks={self._client_audio_chunks} "
                f"bytes={self._client_audio_bytes} queue={self.out_queue.qsize()} "
                f"avg_abs_100={avg_rms_proxy:.1f}"
            )
            self._client_audio_abs_sum = 0
        try:
            self.out_queue.put_nowait(payload)
            return True
        except asyncio.QueueFull:
            return False

    async def send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            try:
                if isinstance(msg, dict):
                    if msg.get("activity_start"):
                        await self.session.send_realtime_input(activity_start=types.ActivityStart())
                        continue
                    if msg.get("activity_end"):
                        await self.session.send_realtime_input(activity_end=types.ActivityEnd())
                        continue
                    if msg.get("realtime_text"):
                        await self.session.send_realtime_input(text=str(msg["realtime_text"]))
                        continue
                    mime_type = str(msg.get("mime_type") or "").lower()
                    data = msg.get("data")
                    if isinstance(data, str):
                        raw = base64.b64decode(data, validate=False)
                    else:
                        raw = data

                    if raw and mime_type.startswith("audio/"):
                        await self.session.send_realtime_input(
                            audio=types.Blob(data=raw, mime_type=mime_type)
                        )
                        continue
                    if raw and (mime_type.startswith("image/") or mime_type.startswith("video/")):
                        await self.session.send_realtime_input(
                            video=types.Blob(data=raw, mime_type=mime_type)
                        )
                        continue

                await self.session.send(input=msg, end_of_turn=False)
            except Exception as e:
                if self._is_ws_connection_closed_error(e):
                    print(f"[AI DEBUG] [SEND] WebSocket closed during realtime send: {e}")
                    self.clear_out_queue()
                    self.clear_audio_queue()
                    raise LiveReconnectRequested("realtime_send_ws_closed")
                print(f"[AI DEBUG] [SEND] Failed to send realtime chunk: {e}")

    async def send_frame_now(self, payload: Optional[dict] = None) -> bool:
        if not self.out_queue:
            return False
        payload = payload or self._latest_image_payload
        if not payload or not isinstance(payload, dict):
            return False
        try:
            if self.out_queue.full():
                return False
            self.out_queue.put_nowait(payload)
            return True
        except Exception:
            return False

    async def refresh_latest_frame(self, min_age_sec: float = 0.0) -> bool:
        if self.video_mode != "screen":
            return False
        if min_age_sec and (time.time() - self._latest_image_ts) < min_age_sec:
            return False
        frame, _ = await asyncio.to_thread(self._grab_screen)
        if frame is None:
            return False
        await self._enqueue_frame(frame)
        return True

    def _resample_audio(self, audio_data, input_rate, target_rate):
        if input_rate == target_rate:
            return audio_data
        
        # Convert bytes to int16 numpy array
        audio_np = np.frombuffer(audio_data, dtype=np.int16)
        
        # Calculate number of samples required
        duration = len(audio_np) / input_rate
        target_samples = int(duration * target_rate)
        
        # Linear interpolation
        x_old = np.linspace(0, duration, len(audio_np))
        x_new = np.linspace(0, duration, target_samples)
        
        resampled = np.interp(x_new, x_old, audio_np).astype(np.int16)
        return resampled.tobytes()

    async def listen_audio(self):
        if pya is None:
            if self.on_error:
                self.on_error("Backend microphone is unavailable; use frontend audio capture.")
            return
        mic_info = pya.get_default_input_device_info()
        resolved_input_device_index = None

        if self.input_device_name:
            print(f"[AI DEBUG] Attempting to find input device matching: '{self.input_device_name}'")
            count = pya.get_device_count()
            best_match = None
            for i in range(count):
                try:
                    info = pya.get_device_info_by_index(i)
                    if info["maxInputChannels"] > 0:
                        name = info.get("name", "")
                        if self.input_device_name.lower() in name.lower() or name.lower() in self.input_device_name.lower():
                            print(f"   Candidate {i}: {name}")
                            resolved_input_device_index = i
                            best_match = name
                            break
                except Exception:
                    continue
            if resolved_input_device_index is not None:
                print(f"[AI DEBUG] Resolved input device '{self.input_device_name}' to index {resolved_input_device_index} ({best_match})")
            else:
                print(f"[AI DEBUG] Could not find device matching '{self.input_device_name}'. Checking index...")

        if resolved_input_device_index is None and self.input_device_index is not None:
            try:
                resolved_input_device_index = int(self.input_device_index)
                print(f"[AI DEBUG] Requesting Input Device Index: {resolved_input_device_index}")
            except ValueError:
                print(f"[AI DEBUG] Invalid device index '{self.input_device_index}', reverting to default.")
                resolved_input_device_index = None

        if resolved_input_device_index is None:
            print("[AI DEBUG] Using Default Input Device")

        # Determine device native rate to avoid emulation errors
        try:
            dev_info = pya.get_device_info_by_index(resolved_input_device_index if resolved_input_device_index is not None else mic_info["index"])
            native_rate = int(dev_info.get("defaultSampleRate", SEND_SAMPLE_RATE))
            print(f"[AI DEBUG] Input Device Native Rate: {native_rate} Hz")
        except Exception:
            native_rate = SEND_SAMPLE_RATE

        try:
            self.audio_stream = await asyncio.to_thread(
                pya.open,
                format=FORMAT,
                channels=CHANNELS,
                rate=native_rate,
                input=True,
                input_device_index=resolved_input_device_index if resolved_input_device_index is not None else mic_info["index"],
                frames_per_buffer=int(CHUNK_SIZE * native_rate / SEND_SAMPLE_RATE),
            )
        except OSError as e:
            print(f"[AI DEBUG] [ERR] Failed to open audio input stream: {e}")
            print("[AI DEBUG] [WARN] Audio features will be disabled. Please check microphone permissions.")
            return

        kwargs = {"exception_on_overflow": False} if __debug__ else {}

        while True:
            if self.paused:
                if self._pause_started_ts is None:
                    self._pause_started_ts = time.monotonic()
                elif (time.monotonic() - self._pause_started_ts) > 1.0:
                    await self._send_audio_stream_end()
                await asyncio.sleep(0.1)
                continue
            self._pause_started_ts = None
            self._audio_stream_end_sent = False

            try:
                # Read enough frames to result in CHUNK_SIZE after resampling
                read_size = int(CHUNK_SIZE * native_rate / SEND_SAMPLE_RATE)
                raw_data = await asyncio.to_thread(self.audio_stream.read, read_size, **kwargs)
                
                # Resample to 16kHz for the API
                data = self._resample_audio(raw_data, native_rate, SEND_SAMPLE_RATE)

                await self._process_input_vad(data, source="backend microphone")

                if self.out_queue:
                    await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})

            except Exception as e:
                print(f"Error reading audio: {e}")
                await asyncio.sleep(0.1)

    async def handle_write_file(self, path, content):
        print(f"[AI DEBUG] [FS] Writing file: '{path}'")
        base_dir = self.workspace_dir.resolve()
        safe_path = os.path.basename(path) if os.path.isabs(path) else path
        final_path = (base_dir / safe_path).resolve()

        if base_dir not in final_path.parents and final_path != base_dir:
            result = f"Rejected path outside workspace: '{path}'"
        else:
            print(f"[AI DEBUG] [FS] Resolved path: '{final_path}'")
            try:
                os.makedirs(os.path.dirname(final_path), exist_ok=True)
                with open(final_path, "w", encoding="utf-8") as f:
                    f.write(content)
                result = f"File '{final_path.name}' written successfully in workspace."
            except Exception as e:
                result = f"Failed to write file '{path}': {str(e)}"

        try:
            await self.session.send(input=f"System Notification: {result}", end_of_turn=True)
        except Exception as e:
            print(f"[AI DEBUG] [ERR] Failed to send fs result: {e}")

    async def handle_read_directory(self, path):
        print(f"[AI DEBUG] [FS] Reading directory: '{path}'")
        try:
            if not os.path.exists(path):
                result = f"Directory '{path}' does not exist."
            else:
                items = os.listdir(path)
                result = f"Contents of '{path}': {', '.join(items)}"
        except Exception as e:
            result = f"Failed to read directory '{path}': {str(e)}"

        try:
            await self.session.send(input=f"System Notification: {result}", end_of_turn=True)
        except Exception as e:
            print(f"[AI DEBUG] [ERR] Failed to send fs result: {e}")

    async def handle_read_file(self, path):
        print(f"[AI DEBUG] [FS] Reading file: '{path}'")
        try:
            if not os.path.exists(path):
                result = f"File '{path}' does not exist."
            else:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                result = f"Content of '{path}':\n{content}"
        except Exception as e:
            result = f"Failed to read file '{path}': {str(e)}"

        try:
            await self.session.send(input=f"System Notification: {result}", end_of_turn=True)
        except Exception as e:
            print(f"[AI DEBUG] [ERR] Failed to send fs result: {e}")

    async def _emit_web_data(self, image_b64=None, log_text=None, job_id: Optional[str] = None, status: Optional[str] = None):
        if not self.on_web_data:
            return
        payload = {"image": image_b64, "log": log_text}
        if job_id:
            payload["job_id"] = job_id
        if status:
            payload["job_status"] = status
        try:
            self.on_web_data(payload)
        except Exception:
            pass

    async def _request_web_action_confirmation(self, action_payload: Dict[str, Any]) -> bool:
        if not self.on_tool_confirmation:
            # No confirmation UI wired; deny risky actions by default.
            return False
        request_id = str(uuid.uuid4())
        future = asyncio.Future()
        self._pending_confirmations[request_id] = future
        try:
            self.on_tool_confirmation({"id": request_id, "tool": "web_action_approval", "args": action_payload})
            confirmed = await asyncio.wait_for(future, timeout=45)
            return bool(confirmed)
        except Exception:
            return False
        finally:
            self._pending_confirmations.pop(request_id, None)

    @staticmethod
    def _normalize_agent_provider(provider: Optional[str]) -> str:
        raw = str(provider or "").strip().lower()
        if raw in {"", "auto", "openclaw", "native", "gemini", "local", "fork"}:
            return "openclaw"
        return "openclaw"

    @staticmethod
    def _as_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            return [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
        return [str(value).strip()]

    @staticmethod
    def _clip_text(text: str, max_chars: int) -> str:
        raw = str(text or "")
        lim = max(200, min(int(max_chars or 8000), 80000))
        if len(raw) <= lim:
            return raw
        return raw[: max(0, lim - 3)] + "..."

    async def _spotify_get_auth_url(self) -> Dict[str, Any]:
        mgr = getattr(self, "spotify_manager", None)
        if not mgr:
            return {"ok": False, "error": "spotify manager unavailable"}
        try:
            url = await asyncio.to_thread(mgr.build_auth_url)
            return {"ok": True, "url": url}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @staticmethod
    def _skill_runtime_meta(skill_obj: Any) -> Dict[str, Any]:
        if not skill_obj:
            return {}
        runtime_meta = getattr(skill_obj, "runtime_meta", None)
        if isinstance(runtime_meta, dict):
            return runtime_meta
        meta = getattr(skill_obj, "metadata", None)
        if not isinstance(meta, dict):
            return {}
        oc = meta.get("openclaw")
        if isinstance(oc, dict):
            return oc
        cb = meta.get("clawdbot")
        if isinstance(cb, dict):
            return cb
        return {}

    def _get_skills_manager(self):
        manager = getattr(self, "skills_manager", None)
        if manager:
            return manager
        return getattr(self, "openclaw_skills", None)

    async def run_skill_command(
        self,
        *,
        skill_name: str,
        command: str,
        timeout_sec: Optional[int] = None,
        max_output_chars: Optional[int] = None,
    ) -> Dict[str, Any]:
        return await self.run_openclaw_skill_command(
            skill_name=skill_name,
            command=command,
            timeout_sec=timeout_sec,
            max_output_chars=max_output_chars,
        )

    async def run_openclaw_skill_command(
        self,
        *,
        skill_name: str,
        command: str,
        timeout_sec: Optional[int] = None,
        max_output_chars: Optional[int] = None,
    ) -> Dict[str, Any]:
        manager = self._get_skills_manager()
        if not manager:
            raise RuntimeError("Skills manager unavailable.")

        name = str(skill_name or "").strip()
        if not name:
            raise ValueError("skill_name is required.")
        cmd = str(command or "").strip()
        if not cmd:
            raise ValueError("command is required.")

        skill = manager.get_skill(name)
        if not skill:
            raise ValueError(f"Skill '{name}' not found.")
        if not getattr(skill, "eligible", True):
            issues = ", ".join(getattr(skill, "eligibility_issues", []) or [])
            raise RuntimeError(f"Skill '{name}' is not eligible: {issues or 'unknown reason'}")

        runtime_meta = self._skill_runtime_meta(skill)
        requires = runtime_meta.get("requires") if isinstance(runtime_meta, dict) else {}
        if not isinstance(requires, dict):
            requires = {}
        allowed_bins = self._as_list(requires.get("bins")) + self._as_list(requires.get("anyBins"))
        allowed_bins_l = {b.lower() for b in allowed_bins if b}
        if not allowed_bins_l:
            # Skills without dedicated CLI binaries often provide Python snippets in SKILL.md.
            allowed_bins_l = {"python", "python3", "py", str(name).strip().lower()}

        stdin_input: Optional[str] = None
        cmd_for_log = cmd
        heredoc_match = re.match(
            r"^\s*(python(?:3)?|py)\s+<<['\"]?EOF['\"]?\s*\r?\n(?P<script>.*)\r?\nEOF\s*$",
            cmd,
            flags=re.IGNORECASE | re.DOTALL,
        )
        try:
            if heredoc_match:
                interpreter = str(heredoc_match.group(1) or "python").strip()
                stdin_input = str(heredoc_match.group("script") or "")
                tokens = [interpreter, "-"]
                cmd_for_log = f"{interpreter} <<EOF ... EOF"
            else:
                tokens = shlex.split(cmd, posix=(os.name != "nt"))
        except Exception as e:
            raise ValueError(f"Invalid command format: {e}")
        if not tokens:
            raise ValueError("Empty command.")
        first = str(tokens[0]).strip().lower()
        if first not in allowed_bins_l:
            allowed = ", ".join(sorted(allowed_bins_l))
            raise ValueError(
                f"Command must start with skill binary ({allowed}); got '{tokens[0]}'."
            )

        sensitive_flags = {
            "--password",
            "--token",
            "--api-key",
            "--apikey",
            "--secret",
            "--client-secret",
        }
        log_tokens: List[str] = []
        redact_next = False
        for token in (tokens if not stdin_input else shlex.split(cmd_for_log, posix=True)):
            tok = str(token)
            low = tok.lower()
            if redact_next:
                log_tokens.append("***")
                redact_next = False
                continue
            if low in sensitive_flags:
                log_tokens.append(tok)
                redact_next = True
                continue
            if any(k in low for k in ["password=", "token=", "apikey=", "api_key=", "secret="]):
                key = tok.split("=", 1)[0]
                log_tokens.append(f"{key}=***")
                continue
            log_tokens.append(tok)
        await self._emit_web_data(
            None,
            f"[SKILL:{name}] $ {self._clip_text(' '.join(log_tokens), 600)}",
        )
        redacted_command = self._clip_text(" ".join(log_tokens), 2000)

        timeout = int(timeout_sec or 120)
        timeout = max(5, min(timeout, 600))
        out_limit = int(max_output_chars or 8000)
        out_limit = max(500, min(out_limit, 80000))

        workdir = str(skill.path.parent.resolve())
        runtime_env = getattr(skill, "runtime_env", None)
        if not isinstance(runtime_env, dict):
            runtime_env = {}
        proc_env = os.environ.copy()
        for key, value in runtime_env.items():
            kk = str(key or "").strip()
            vv = str(value or "").strip()
            if kk and vv:
                proc_env[kk] = vv

        def _run_sync() -> subprocess.CompletedProcess:
            return subprocess.run(
                tokens,
                cwd=workdir,
                capture_output=True,
                text=True,
                input=stdin_input,
                timeout=timeout,
                check=False,
                shell=False,
                env=proc_env,
            )

        try:
            proc = await asyncio.to_thread(_run_sync)
        except FileNotFoundError:
            await self._emit_web_data(None, f"[SKILL:{name}] command not found: {tokens[0]}")
            raise RuntimeError(f"Command not found: {tokens[0]}")
        except subprocess.TimeoutExpired:
            await self._emit_web_data(None, f"[SKILL:{name}] timeout after {timeout}s")
            raise RuntimeError(f"Skill command timed out after {timeout}s.")

        stdout = self._clip_text(proc.stdout or "", out_limit)
        stderr = self._clip_text(proc.stderr or "", out_limit)
        merged = stdout if stdout else stderr
        if not merged:
            merged = f"(exit code {proc.returncode}, no output)"

        await self._emit_web_data(
            None,
            f"[SKILL:{name}] exit={proc.returncode}",
        )

        return {
            "ok": proc.returncode == 0,
            "exit_code": int(proc.returncode),
            "command": redacted_command,
            "stdout": stdout,
            "stderr": stderr,
            "result": self._clip_text(merged, out_limit),
        }

    def _extract_direct_skill_command(self, prompt: str) -> Optional[Tuple[str, str]]:
        text = str(prompt or "").strip()
        if not text:
            return None
        # Accept plain command or command after colon/newline, e.g.:
        # "Uzyj toola: gog auth credentials ..."
        m = re.search(r"(?:^|[:\n]\s*)([a-zA-Z0-9._-]+\s+[^\n]+)$", text)
        candidate = (m.group(1) if m else text).strip()
        if not candidate:
            return None
        first = candidate.split()[0].strip().lower()

        manager = self._get_skills_manager()
        if not manager:
            return None

        # Build mapping from executable -> installed skill name
        # (supports names like "spotify-player" with bins "spogo"/"spotify_player").
        bin_to_skill: Dict[str, str] = {}
        skill_name_lookup: Dict[str, str] = {}
        try:
            listed = manager.list_skills(include_ineligible=True, include_disabled=True)
            for item in listed:
                name = str((item or {}).get("name") or "").strip()
                if not name:
                    continue
                skill_name_lookup[name.lower()] = name
                skill_obj = manager.get_skill(name)
                runtime_meta = self._skill_runtime_meta(skill_obj)
                requires = runtime_meta.get("requires") if isinstance(runtime_meta, dict) else {}
                if not isinstance(requires, dict):
                    requires = {}
                bins = self._as_list(requires.get("bins")) + self._as_list(requires.get("anyBins"))
                for b in bins:
                    bb = str(b).strip().lower()
                    if bb and bb not in bin_to_skill:
                        bin_to_skill[bb] = name
        except Exception:
            return None

        # Direct by skill name: "<skill-name> ..."
        if first in skill_name_lookup:
            return skill_name_lookup[first], candidate
        # Direct by executable: "<bin> ..."
        if first in bin_to_skill:
            return bin_to_skill[first], candidate

        return None

    async def _maybe_run_direct_skill_command(self, prompt: str) -> Optional[str]:
        extracted = self._extract_direct_skill_command(prompt)
        if not extracted:
            return None
        skill_name, command = extracted
        await self._emit_web_data(None, f"[DIRECT] Running skill command: {command}")
        try:
            result_obj = await self.run_openclaw_skill_command(
                skill_name=skill_name,
                command=command,
            )
            result_text = str(result_obj.get("result") or "").strip() or "Skill command completed."
            return f"Direct skill command finished ({skill_name}). {result_text}"
        except Exception as e:
            err = str(e)
            # Add concise dependency hint for common eligibility failures.
            if "not eligible" in err.lower() and "missing bins" in err.lower():
                err = f"{err}. Install required CLI binary and restart app."
            await self._emit_web_data(None, f"[DIRECT] Skill command failed: {err}")
            return f"Direct skill command failed ({skill_name}): {err}"

    def _get_active_agent_job(self, provider: Optional[str] = None) -> Optional[Dict[str, Any]]:
        desired_provider = self._normalize_agent_provider(provider) if provider else None
        active_statuses = {"queued", "running", "stopping"}
        candidates: List[Dict[str, Any]] = []
        for job in self._agent_jobs.values():
            if not isinstance(job, dict):
                continue
            status = str(job.get("status") or "").strip().lower()
            if status not in active_statuses:
                continue
            task = job.get("task")
            if task is not None and getattr(task, "done", lambda: False)():
                continue
            if desired_provider and str(job.get("provider") or "") != desired_provider:
                continue
            candidates.append(job)
        if not candidates:
            return None
        candidates.sort(key=lambda j: float(j.get("updated_at") or j.get("created_at") or 0), reverse=True)
        return candidates[0]

    def start_agent_job(
        self,
        prompt: str,
        provider: str = "openclaw",
        agent: Optional[str] = None,
        thinking: Optional[str] = None,
        timeout_sec: Optional[int] = None,
        allow_parallel: bool = False,
    ) -> str:
        clean_prompt = str(prompt or "").strip()
        if not clean_prompt:
            raise ValueError("prompt required")

        requested_provider = str(provider or "auto").strip().lower()
        normalized_provider = self._normalize_agent_provider(requested_provider)
        if not allow_parallel:
            active = self._get_active_agent_job(provider=normalized_provider)
            if active:
                active["updated_at"] = time.time()
                active_id = str(active.get("id"))
                if active_id:
                    self._last_agent_job_id = active_id
                return active_id

        job_id = f"job_{uuid.uuid4().hex[:10]}"
        job = {
            "id": job_id,
            "prompt": clean_prompt,
            "provider": normalized_provider,
            "requested_provider": requested_provider,
            "agent": (str(agent).strip() if agent is not None else None) or None,
            "thinking": (str(thinking).strip() if thinking is not None else None) or None,
            "timeout_sec": timeout_sec,
            "status": "queued",
            "result": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
            "cancel_event": asyncio.Event(),
            "task": None,
        }
        self._agent_jobs[job_id] = job
        self._last_agent_job_id = job_id
        task = asyncio.create_task(self._run_agent_job(job_id))
        job["task"] = task
        return job_id

    async def _run_agent_job(self, job_id: str) -> str:
        job = self._agent_jobs.get(job_id)
        if not job:
            return "job not found"

        job["status"] = "running"
        job["updated_at"] = time.time()
        requested_provider = str(job.get("requested_provider") or "openclaw")
        await self._emit_web_data(
            None,
            f"[{job_id}] Started (openclaw-fork, requested={requested_provider}).",
            job_id=job_id,
            status="running",
        )

        async def update_frontend(image_b64, log_text):
            prefix = f"[{job_id}] " if job_id else ""
            msg = f"{prefix}{log_text}" if log_text else None
            await self._emit_web_data(image_b64, msg, job_id=job_id, status=job.get("status"))

        async def approval_callback(payload: Dict[str, Any]) -> bool:
            enriched = dict(payload or {})
            enriched["job_id"] = job_id
            return await self._request_web_action_confirmation(enriched)

        provider = job.get("provider", "openclaw")
        prompt = job.get("prompt", "")
        agent = job.get("agent")
        thinking = job.get("thinking")
        timeout_sec = job.get("timeout_sec")
        cancel_event = job.get("cancel_event")

        try:
            if provider != "openclaw":
                await update_frontend(None, f"Provider '{provider}' mapped to local openclaw-fork.")
            if agent or thinking or timeout_sec is not None:
                await update_frontend(None, "Compatibility params (agent/thinking/timeout) are ignored in local openclaw-fork.")

            result = await self.web_agent.run_task(
                prompt,
                update_callback=update_frontend,
                action_approval_callback=approval_callback,
                cancel_event=cancel_event,
            )

            if cancel_event and cancel_event.is_set():
                job["status"] = "cancelled"
                job["result"] = "Task cancelled by user."
            else:
                job["status"] = "completed"
                job["result"] = result or "Task completed."
        except asyncio.CancelledError:
            job["status"] = "cancelled"
            job["result"] = "Task cancelled by user."
        except Exception as e:
            try:
                await update_frontend(None, f"ERROR: {e}")
            except Exception:
                pass
            try:
                traceback.print_exc()
            except Exception:
                pass
            job["status"] = "failed"
            job["error"] = str(e)
            job["result"] = f"Agent job error: {e}"
        finally:
            job["updated_at"] = time.time()
            await self._emit_web_data(
                None,
                f"[{job_id}] Finished with status={job['status']}.",
                job_id=job_id,
                status=job.get("status"),
            )

        return str(job.get("result") or "")

    def get_agent_job_status(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        def _pack(job: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "id": job.get("id"),
                "status": job.get("status"),
                "provider": job.get("provider"),
                "created_at": job.get("created_at"),
                "updated_at": job.get("updated_at"),
                "error": job.get("error"),
                "result": job.get("result"),
            }

        if job_id:
            job = self._agent_jobs.get(job_id)
            return {"job": _pack(job)} if job else {"job": None}
        jobs = [_pack(j) for j in self._agent_jobs.values()]
        jobs.sort(key=lambda x: float(x.get("updated_at") or 0), reverse=True)
        return {"jobs": jobs}

    async def stop_agent_job(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        target_id = job_id or self._last_agent_job_id
        if not target_id:
            return {"ok": False, "error": "no-job-id"}
        job = self._agent_jobs.get(target_id)
        if not job:
            return {"ok": False, "error": "job-not-found", "job_id": target_id}
        job["status"] = "stopping"
        job["updated_at"] = time.time()
        cancel_event = job.get("cancel_event")
        if cancel_event:
            cancel_event.set()
        task = job.get("task")
        if task and not task.done():
            task.cancel()
        await self._emit_web_data(None, f"[{target_id}] Stop requested.", job_id=target_id, status="stopping")
        return {"ok": True, "job_id": target_id, "status": "stopping"}

    async def resume_agent_job(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        target_id = job_id or self._last_agent_job_id
        if not target_id:
            return {"ok": False, "error": "no-job-id"}
        job = self._agent_jobs.get(target_id)
        if not job:
            return {"ok": False, "error": "job-not-found", "job_id": target_id}
        provider = job.get("provider") or "openclaw"
        active = self._get_active_agent_job(provider=provider)
        if active and str(active.get("id") or "") != str(target_id):
            active_id = str(active.get("id") or "")
            self._last_agent_job_id = active_id or self._last_agent_job_id
            return {
                "ok": True,
                "job_id": active_id,
                "status": str(active.get("status") or "running"),
                "reused_existing_job": True,
            }
        new_job_id = self.start_agent_job(
            prompt=job.get("prompt") or "",
            provider=provider,
            agent=job.get("agent"),
            thinking=job.get("thinking"),
            timeout_sec=job.get("timeout_sec"),
        )
        self._agent_jobs[new_job_id]["resumed_from"] = target_id
        await self._emit_web_data(None, f"[{new_job_id}] Resumed from {target_id}.", job_id=new_job_id, status="queued")
        return {"ok": True, "job_id": new_job_id, "resumed_from": target_id}

    async def _shutdown_program_after_farewell(self, reason: str = ""):
        # Give the model a chance to consume the tool response, speak the final
        # goodbye, and finish audio playback before the backend exits.
        started = time.monotonic()
        saw_ai_turn = False
        await asyncio.sleep(1.0)

        while (time.monotonic() - started) < 30.0:
            if self._ai_turn_open:
                saw_ai_turn = True
            if saw_ai_turn and not self._ai_turn_open and not self._is_speaking:
                break
            if not saw_ai_turn and (time.monotonic() - started) > 8.0 and not self._ai_turn_open and not self._is_speaking:
                break
            await asyncio.sleep(0.25)

        await asyncio.sleep(0.8)
        callback = self.on_program_shutdown
        if not callback:
            print("[AI DEBUG] [SHUTDOWN] Program shutdown requested, but no callback is configured.")
            return
        try:
            maybe = callback(reason or "Program shutdown requested by assistant after user confirmation.")
            if asyncio.iscoroutine(maybe):
                await maybe
        except Exception as e:
            print(f"[AI DEBUG] [SHUTDOWN] Shutdown callback failed: {e}")

    def request_program_shutdown(self, reason: str = "") -> str:
        if self._program_shutdown_task and not self._program_shutdown_task.done():
            return "Program shutdown is already scheduled."
        self._program_shutdown_task = asyncio.create_task(
            self._shutdown_program_after_farewell(reason=reason)
        )
        return (
            "Shutdown scheduled. Say one brief, warm goodbye now and remind the user that "
            "to talk again later, they need to start the program again."
        )

    async def handle_web_agent_request(self, prompt):
        print(f"[AI DEBUG] [WEB-AGENT-HANDLER] Starting for prompt: {prompt[:100]}")
        direct_result = await self._maybe_run_direct_skill_command(prompt)
        if direct_result is not None:
            print(f"[AI DEBUG] [WEB-AGENT-HANDLER] Direct result found, sending to AI")
            try:
                await self.session.send(
                    input=f"System Notification: {direct_result}",
                    end_of_turn=True,
                )
                print(f"[AI DEBUG] [WEB-AGENT-HANDLER] Direct result sent successfully")
            except Exception as e:
                print(f"[AI DEBUG] [WEB-AGENT-HANDLER] ERROR sending direct result: {e}")
            return

        print(f"[AI DEBUG] [WEB-AGENT-HANDLER] Starting agent job...")
        job_id = self.start_agent_job(prompt=prompt, provider="openclaw")
        job = self._agent_jobs[job_id]
        print(f"[AI DEBUG] [WEB-AGENT-HANDLER] Waiting for job {job_id} to complete...")
        result = await job["task"]
        print(f"[AI DEBUG] [WEB-AGENT-HANDLER] Job {job_id} completed. Result length: {len(str(result))}")
        print(f"[AI DEBUG] [WEB-AGENT-HANDLER] Result: {str(result)[:200]}")
        try:
            msg = f"System Notification: Monika OpenClaw fork has finished (job: {job_id}).\nResult: {result}"
            print(f"[AI DEBUG] [WEB-AGENT-HANDLER] Sending result to AI (message length: {len(msg)})")
            await self.session.send(
                input=msg,
                end_of_turn=True,
            )
            print(f"[AI DEBUG] [WEB-AGENT-HANDLER] Result sent successfully to AI!")
        except Exception as e:
            print(f"[AI DEBUG] [WEB-AGENT-HANDLER] ERROR sending result to AI: {type(e).__name__}: {e}")

    async def handle_openclaw_agent_request(
        self,
        prompt: str,
        agent: Optional[str] = None,
        thinking: Optional[str] = None,
        timeout_sec: Optional[int] = None,
    ):
        print(
            f"[AI DEBUG] [OPENCLAW-FORK] Task: prompt='{prompt}', agent='{agent}', "
            f"thinking='{thinking}', timeout={timeout_sec}"
        )
        direct_result = await self._maybe_run_direct_skill_command(prompt)
        if direct_result is not None:
            try:
                await self.session.send(
                    input=f"System Notification: {direct_result}",
                    end_of_turn=True,
                )
            except Exception as e:
                print(f"[AI DEBUG] [ERR] Failed to send direct skill result to model: {e}")
            return

        job_id = self.start_agent_job(
            prompt=prompt,
            provider="openclaw",
            agent=agent,
            thinking=thinking,
            timeout_sec=timeout_sec,
        )
        job = self._agent_jobs[job_id]
        result = await job["task"]
        try:
            await self.session.send(
                input=f"System Notification: Monika OpenClaw fork has finished (job: {job_id}).\nResult: {result}",
                end_of_turn=True,
            )
        except Exception as e:
            print(f"[AI DEBUG] [ERR] Failed to send OpenClaw fork result to model: {e}")

    async def receive_audio(self):
        try:
            while True:
                turn = self.session.receive()
                async for response in turn:
                    if data := response.data:
                        if self.enable_audio_io and not self._suppress_spoken_output:
                            self.audio_in_queue.put_nowait(data)

                    if getattr(response, "session_resumption_update", None):
                        update = response.session_resumption_update
                        if getattr(update, "resumable", False):
                            self._session_resume_handle = getattr(update, "new_handle", None) or self._session_resume_handle
                        else:
                            self._session_resume_handle = None

                    if getattr(response, "go_away", None):
                        go_away = response.go_away
                        self._go_away_requested = True
                        print(f"[AI DEBUG] [LIVE] GoAway received. time_left={getattr(go_away, 'time_left', None)}")

                    if response.server_content:
                        native_thoughts = _extract_native_thought_parts(response.server_content)
                        if GEMINI_EMIT_NATIVE_THOUGHT_EVENTS and native_thoughts and self.on_internal_thought:
                            for key, text in native_thoughts:
                                if key in self._emitted_native_thought_keys:
                                    continue
                                formatted = self._normalize_model_internal_thought(text)
                                if formatted:
                                    self.on_internal_thought(formatted)
                                    self._emitted_native_thought_keys.add(key)

                        if response.server_content.input_transcription:
                            transcript = response.server_content.input_transcription.text
                            if transcript and transcript != self._last_input_transcription:
                                is_correction = False
                                delta = transcript
                                if transcript.startswith(self._last_input_transcription):
                                    delta = transcript[len(self._last_input_transcription) :]
                                elif self._last_input_transcription.startswith(transcript):
                                    # Backtrack/Correction (New is substring of Old) -> Force replace
                                    is_correction = True
                                    delta = transcript
                                else:
                                    # Treat mismatch as new text to append (no deletion/replacement)
                                    is_correction = False
                                    # Only insert space if previous text ended with punctuation (sentence boundary)
                                    if not transcript.startswith(" ") and not self._last_input_transcription.endswith(" "):
                                        if re.search(r'[.!?]\s*$', self._last_input_transcription):
                                            delta = " " + transcript
                                        else:
                                            delta = transcript
                                    else:
                                        delta = transcript

                                self._last_input_transcription = transcript
                                self._last_user_text = transcript
                                self._last_user_ts = time.monotonic()
                                self._fallback_web_agent_triggered_for_turn = False  # Reset for new user input
                                
                                if delta or is_correction:
                                    self.mark_user_activity(delta)
                                    self.clear_audio_queue()
                                    self._is_new_turn = True
                                    if self.on_transcription:
                                        self.on_transcription({
                                            "sender": "Ty", 
                                            "text": transcript if is_correction else delta, 
                                            "is_correction": is_correction
                                        })

                                    if self.chat_buffer["sender"] != "Ty":
                                        if self.chat_buffer["sender"] and self.chat_buffer["text"].strip():
                                            self.session_manager.log_chat(self.chat_buffer["sender"], self.chat_buffer["text"])
                                        self.chat_buffer = {"sender": "Ty", "text": transcript}
                                    else:
                                        if is_correction:
                                            self.chat_buffer["text"] = transcript
                                        else:
                                            self.chat_buffer["text"] += delta

                                    # Zbieraj wyłącznie najnowszą rewizję ASR.
                                    # Jeden brief powstanie dopiero na ręcznie
                                    # kontrolowanym końcu aktywności głosowej.
                                    try:
                                        self.thinker.update_voice_transcript(self.chat_buffer["text"])
                                    except Exception:
                                        pass

                        if response.server_content.output_transcription:
                            transcript = response.server_content.output_transcription.text
                            if transcript and transcript != self._last_output_transcription:
                                self._ai_turn_open = True
                                # 1. Parse full raw transcript
                                spoken_full, thoughts_full = parse_model_response(transcript)
                                
                                # 2. Handle Thoughts
                                if len(thoughts_full) > self._emitted_thoughts_count:
                                    new_thoughts = thoughts_full[self._emitted_thoughts_count:]
                                    for th in new_thoughts:
                                        if self.on_internal_thought:
                                            formatted = self._normalize_model_internal_thought(th)
                                            if formatted:
                                                self.on_internal_thought(formatted)
                                    self._emitted_thoughts_count = len(thoughts_full)

                                # 3. Handle Spoken Delta
                                delta, is_output_correction = _streaming_transcript_update(
                                    self._last_spoken_transcription, spoken_full
                                )
                                
                                # Heuristic: Fix missing spaces between chunks
                                if delta and self._last_spoken_transcription:
                                    if self._last_spoken_transcription[-1].isalnum() and delta[0].isalnum():
                                        delta = " " + delta
                                    elif re.search(r"[.!?…,:;]$", self._last_spoken_transcription) and re.match(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]", delta):
                                        delta = " " + delta

                                self._last_output_transcription = transcript
                                self._last_spoken_transcription = spoken_full
                                
                                if delta and not self._suppress_spoken_output:
                                    now = time.monotonic()
                                    if delta == self._last_ai_delta and (now - self._last_ai_delta_ts) < 1.2:
                                        continue
                                    self._last_ai_delta = delta
                                    self._last_ai_delta_ts = now
                                    self.mark_ai_activity(delta)
                                    
                                    # FALLBACK: Browser automation only. Public factual lookups should use
                                    # Gemini's built-in google_search, not the heavier OpenClaw/browser agent.
                                    search_patterns = r'\b(sprawdzam|szukam|sprawdzę|searching|looking|checking|find)\b'
                                    if re.search(search_patterns, delta, re.IGNORECASE) and not self._fallback_web_agent_triggered_for_turn:
                                        print(f"[AI DEBUG] [FALLBACK] AI mentioned checking/searching: '{delta}'")
                                        
                                        # Extract last user message as search prompt
                                        if self.session_manager:
                                            history = self.session_manager.get_recent_chat_history(limit=20)
                                            last_user_msg = None
                                            for entry in reversed(history):
                                                if entry.get("role") == "user" or entry.get("sender") == "User":
                                                    last_user_msg = entry.get("content") or entry.get("text", "")
                                                    break
                                            if last_user_msg and _looks_like_browser_automation_request(last_user_msg):
                                                print(f"[AI DEBUG] [FALLBACK] Auto-triggering browser agent for: '{last_user_msg}'")
                                                self._fallback_web_agent_triggered_for_turn = True
                                                search_prompt = f"Complete this browser task: {last_user_msg}"
                                                asyncio.create_task(self.handle_web_agent_request(search_prompt))
                                            elif last_user_msg:
                                                print(f"[AI DEBUG] [FALLBACK] Not starting browser agent for public lookup: '{last_user_msg}'")
                                                self._fallback_web_agent_triggered_for_turn = True
                                    
                                    if self.on_transcription:
                                        self.on_transcription({
                                            "sender": "AI",
                                            "text": spoken_full if is_output_correction else delta,
                                            "is_new": self._is_new_turn,
                                            "is_correction": is_output_correction,
                                        })

                                    self._is_new_turn = False

                                    if self.chat_buffer["sender"] != "AI":
                                        if self.chat_buffer["sender"] and self.chat_buffer["text"].strip():
                                            self.session_manager.log_chat(self.chat_buffer["sender"], self.chat_buffer["text"])
                                        self.chat_buffer = {
                                            "sender": "AI",
                                            "text": spoken_full if is_output_correction else delta,
                                        }
                                    else:
                                        if is_output_correction:
                                            self.chat_buffer["text"] = spoken_full
                                        else:
                                            self.chat_buffer["text"] += delta

                        if response.server_content.turn_complete:
                            self._ai_turn_open = False
                            self._emitted_thoughts_count = 0
                            self._emitted_native_thought_keys.clear()
                            if self._suppress_spoken_output:
                                self._suppress_spoken_output = False
                            self.flush_chat()
                            if self._pending_system_messages:
                                asyncio.create_task(self._flush_pending_system_messages())

                        if response.server_content.interrupted:
                            self.clear_audio_queue()

                    if response.tool_call:
                        print("The tool was called")
                        function_responses = []

                        for fc in response.tool_call.function_calls:
                            if fc.name in [
                                "get_work_memory",
                                "update_work_memory",
                                "commit_work_memory",
                                "clear_work_memory",
                                "create_reminder",
                                "list_reminders",
                                "cancel_reminder",
                                "spotify_get_auth_url",
                                "spotify_get_status",
                                "spotify_get_now_playing",
                                "spotify_list_playlists",
                                "spotify_recently_played",
                                "get_time_context",
                                "update_personality",
                                "run_web_agent",
                                "run_openclaw_agent",
                                "manage_agent_job",
                                    "list_openclaw_skills",
                                    "list_skills",
                                    "get_openclaw_skill",
                                    "get_skill",
                                    "refresh_openclaw_skills",
                                    "refresh_skills",
                                    "run_openclaw_skill_command",
                                    "run_skill_command",
                                "write_file",
                                "read_directory",
                                "read_file",
                                "list_smart_devices",
                                "control_light",
                                "manage_shopping_list",
                                "get_random_fact",
                                "get_random_greeting",
                                "get_random_farewell",
                                "get_random_topic",
                                "get_weather",
                                "request_program_shutdown",
                                "notes_get",
                                "notes_set",
                                "notes_append",
                                "memory_add_entry",
                                "memory_search",
                                "recall_conversation",
                                "memory_get_page",
                                "memory_create_page",
                                "memory_append_page",
                                "journal_add_entry",
                                "journal_finalize_session",
                                "session_prompt",
                                "study_set_fields",
                                "study_set_page",
                                "study_create_flashcard",
                                "study_review_flashcards",
                                "study_record_review",
                                "create_event",
                                "list_events",
                                "delete_event",
                                "update_event",
                            ] or fc.name.startswith("minecraft_"):
                                prompt = fc.args.get("prompt", "")

                                confirmation_required = self.permissions.get(fc.name, True)
                                if fc.name.startswith("minecraft_"):
                                    confirmation_required = False
                                if fc.name == "manage_agent_job":
                                    action = str(fc.args.get("action") or "").strip().lower()
                                    if action in {"status", "list"}:
                                        confirmation_required = False
                                    elif action == "start":
                                        provider_hint = str(fc.args.get("provider") or "openclaw").strip().lower() or "openclaw"
                                        normalized_provider = self._normalize_agent_provider(provider_hint)
                                        if self._get_active_agent_job(provider=normalized_provider):
                                            # Redundant start while a job is already active.
                                            confirmation_required = False
                                elif fc.name == "run_openclaw_agent":
                                    if self._get_active_agent_job(provider="openclaw"):
                                        # Avoid duplicate approval popups while a web-agent job is already active.
                                        confirmation_required = False

                                if confirmation_required:
                                    if self.on_tool_confirmation:
                                        import uuid

                                        request_id = str(uuid.uuid4())
                                        print(f"[AI DEBUG] [STOP] Requesting confirmation for '{fc.name}' (ID: {request_id})")

                                        future = asyncio.Future()
                                        self._pending_confirmations[request_id] = future

                                        self.on_tool_confirmation({"id": request_id, "tool": fc.name, "args": fc.args})

                                        try:
                                            confirmed = await future
                                        finally:
                                            self._pending_confirmations.pop(request_id, None)

                                        if not confirmed:
                                            function_responses.append(
                                                types.FunctionResponse(
                                                    id=fc.id,
                                                    name=fc.name,
                                                    response={"result": "User denied the request to use this tool."},
                                                )
                                            )
                                            continue
                                    else:
                                        if not self.auto_allow_tools_without_confirmation:
                                            function_responses.append(
                                                types.FunctionResponse(
                                                    id=fc.id,
                                                    name=fc.name,
                                                    response={"result": "Tool use denied because no confirmation channel is available for this transport."},
                                                )
                                            )
                                            continue
                                        # No confirmation callback available -> auto-allow to avoid deadlock
                                        pass

                                # In Minecraft game mode, reject non-Minecraft tools to keep focus.
                                if self.minecraft_game_mode and not fc.name.startswith("minecraft_"):
                                    allowed_in_game_mode = {
                                        "get_time_context",
                                        "request_program_shutdown",
                                    }
                                    if fc.name not in allowed_in_game_mode:
                                        function_responses.append(
                                            types.FunctionResponse(
                                                id=fc.id,
                                                name=fc.name,
                                                response={
                                                    "result": (
                                                        "Tool blocked: Minecraft game mode is active. "
                                                        "Use minecraft_* tools only until game mode is disabled."
                                                    )
                                                },
                                            )
                                        )
                                        continue

                                # Execute tool
                                if fc.name == "run_web_agent":
                                    asyncio.create_task(self.handle_web_agent_request(prompt))
                                    function_responses.append(
                                        types.FunctionResponse(
                                            id=fc.id,
                                            name=fc.name,
                                            response={"result": "Web Navigation started. Do not reply to this message."},
                                        )
                                    )

                                elif fc.name == "run_openclaw_agent":
                                    agent_id = fc.args.get("agent")
                                    thinking = fc.args.get("thinking")
                                    timeout_sec = fc.args.get("timeout_sec")
                                    asyncio.create_task(
                                        self.handle_openclaw_agent_request(
                                            prompt=prompt,
                                            agent=agent_id,
                                            thinking=thinking,
                                            timeout_sec=timeout_sec,
                                        )
                                    )
                                    function_responses.append(
                                        types.FunctionResponse(
                                            id=fc.id,
                                            name=fc.name,
                                            response={"result": "OpenClaw Agent started. Do not reply to this message."},
                                        )
                                    )

                                elif fc.name == "manage_agent_job":
                                    action = str(fc.args.get("action") or "").strip().lower()
                                    job_id = fc.args.get("job_id")
                                    if action == "start":
                                        prompt_start = str(fc.args.get("prompt") or "").strip()
                                        provider = str(fc.args.get("provider") or "openclaw").strip().lower() or "openclaw"
                                        agent_id = fc.args.get("agent")
                                        thinking = fc.args.get("thinking")
                                        timeout_sec = fc.args.get("timeout_sec")
                                        if not prompt_start:
                                            result_str = "prompt is required for action=start"
                                        else:
                                            normalized_provider = self._normalize_agent_provider(provider)
                                            active_job = self._get_active_agent_job(provider=normalized_provider)
                                            if active_job:
                                                active_id = str(active_job.get("id") or "")
                                                active_status = str(active_job.get("status") or "running")
                                                result_str = f"active job already running: {active_id} (status={active_status})"
                                            else:
                                                new_job_id = self.start_agent_job(
                                                    prompt=prompt_start,
                                                    provider=provider,
                                                    agent=agent_id,
                                                    thinking=thinking,
                                                    timeout_sec=timeout_sec,
                                                )
                                                normalized = self._agent_jobs.get(new_job_id, {}).get("provider", "openclaw")
                                                result_str = f"started job: {new_job_id} (provider={normalized})"
                                    elif action == "status":
                                        result_obj = self.get_agent_job_status(job_id)
                                        result_str = json.dumps(result_obj, ensure_ascii=False)
                                    elif action == "list":
                                        result_obj = self.get_agent_job_status(None)
                                        result_str = json.dumps(result_obj, ensure_ascii=False)
                                    elif action == "stop":
                                        result_obj = await self.stop_agent_job(job_id)
                                        result_str = json.dumps(result_obj, ensure_ascii=False)
                                    elif action == "resume":
                                        result_obj = await self.resume_agent_job(job_id)
                                        result_str = json.dumps(result_obj, ensure_ascii=False)
                                    else:
                                        result_str = "unknown action (use: start|status|stop|resume|list)"
                                    function_responses.append(
                                        types.FunctionResponse(
                                            id=fc.id,
                                            name=fc.name,
                                            response={"result": result_str},
                                        )
                                    )

                                elif fc.name in {"list_openclaw_skills", "list_skills"}:
                                    include_ineligible = bool(fc.args.get("include_ineligible", False))
                                    include_disabled = bool(fc.args.get("include_disabled", False))
                                    manager = self._get_skills_manager()
                                    if not manager:
                                        result_obj = {
                                            "count": 0,
                                            "skills": [],
                                            "error": "skills manager unavailable",
                                        }
                                    else:
                                        skills = manager.list_skills(
                                            include_ineligible=include_ineligible,
                                            include_disabled=include_disabled,
                                        )
                                        result_obj = {"count": len(skills), "skills": skills}
                                    result_str = json.dumps(result_obj, ensure_ascii=False)
                                    function_responses.append(
                                        types.FunctionResponse(
                                            id=fc.id,
                                            name=fc.name,
                                            response={"result": result_str, "skills": result_obj.get("skills", [])},
                                        )
                                    )

                                elif fc.name in {"get_openclaw_skill", "get_skill"}:
                                    skill_name = str(fc.args.get("name") or "").strip()
                                    max_chars = fc.args.get("max_chars", 12000)
                                    try:
                                        max_chars = int(max_chars)
                                    except Exception:
                                        max_chars = 12000
                                    max_chars = max(500, min(max_chars, 50000))

                                    if not skill_name:
                                        result_obj = {"error": "name is required"}
                                    else:
                                        manager = self._get_skills_manager()
                                        if not manager:
                                            result_obj = {"error": "skills manager unavailable"}
                                        else:
                                            skill = manager.get_skill(skill_name)
                                            if not skill:
                                                available = [s["name"] for s in manager.list_skills(include_ineligible=True, include_disabled=True)]
                                                result_obj = {
                                                    "error": f"skill '{skill_name}' not found",
                                                    "available_skills": available[:100],
                                                }
                                            else:
                                                content = manager.get_skill_content(skill_name, max_chars=max_chars) or ""
                                                result_obj = {
                                                    "skill": skill.to_summary(),
                                                    "content": content,
                                                }
                                    if "content" in result_obj:
                                        result_str = result_obj["content"]
                                    else:
                                        result_str = json.dumps(result_obj, ensure_ascii=False)
                                    function_responses.append(
                                        types.FunctionResponse(
                                            id=fc.id,
                                            name=fc.name,
                                            response={"result": result_str, **result_obj},
                                        )
                                    )

                                elif fc.name in {"refresh_openclaw_skills", "refresh_skills"}:
                                    manager = self._get_skills_manager()
                                    if not manager:
                                        result_obj = {
                                            "count": 0,
                                            "skills": [],
                                            "error": "skills manager unavailable",
                                        }
                                    else:
                                        count = manager.refresh()
                                        skills = manager.list_skills(
                                            include_ineligible=True,
                                            include_disabled=True,
                                        )
                                        result_obj = {"count": count, "skills": skills}
                                    result_str = json.dumps(result_obj, ensure_ascii=False)
                                    function_responses.append(
                                        types.FunctionResponse(
                                            id=fc.id,
                                            name=fc.name,
                                            response={"result": result_str, "skills": result_obj.get("skills", [])},
                                        )
                                    )

                                elif fc.name in {"run_openclaw_skill_command", "run_skill_command"}:
                                    skill_name = str(fc.args.get("skill_name") or "").strip()
                                    command = str(fc.args.get("command") or "").strip()
                                    timeout_sec = fc.args.get("timeout_sec")
                                    max_output_chars = fc.args.get("max_output_chars")
                                    try:
                                        result_obj = await self.run_skill_command(
                                            skill_name=skill_name,
                                            command=command,
                                            timeout_sec=timeout_sec,
                                            max_output_chars=max_output_chars,
                                        )
                                    except Exception as e:
                                        result_obj = {
                                            "ok": False,
                                            "error": str(e),
                                            "result": f"Skill command error: {e}",
                                        }
                                    function_responses.append(
                                        types.FunctionResponse(
                                            id=fc.id,
                                            name=fc.name,
                                            response=result_obj,
                                        )
                                    )

                                elif fc.name == "get_time_context":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(
                                            name=fc.name,
                                            arguments=dict(fc.args or {}),
                                        )
                                    )
                                    function_responses.append(
                                        types.FunctionResponse(
                                            id=fc.id,
                                            name=fc.name,
                                            response={"result": result.result},
                                        )
                                    )

                                elif fc.name == "set_scene":
                                    try:
                                        _scene = str(fc.args.get("scene") or "").strip().lower()
                                        _valid = {"room", "kitchen", "outside", "school", "restaurant"}
                                        if _scene not in _valid:
                                            result_str = f"Unknown scene '{_scene}'. Available: {', '.join(sorted(_valid))}."
                                        else:
                                            from backend.core import server as _srv
                                            await _srv.VN_SCENE_RUNTIME.set_scene_intentional(
                                                _scene, reason=str(fc.args.get("reason") or "") or None
                                            )
                                            result_str = f"Scene changed to '{_scene}'."
                                    except Exception as e:
                                        result_str = f"Error changing scene: {e}"
                                    function_responses.append(
                                        types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str})
                                    )

                                elif fc.name == "minecraft_goals":
                                    try:
                                        from backend.core.runtimes.v2_runtime import get as _v2_get
                                        from backend.progression import minecraft_goals as _mcg

                                        _v2rt = _v2_get()
                                        _db = _v2rt._db_path if _v2rt else None
                                        _action = str(fc.args.get("action") or "list").lower()
                                        _text = str(fc.args.get("text") or "")
                                        if _action == "add":
                                            _, _st = await _mcg.add_goal(_text, db_path=_db)
                                            result_str = {
                                                "ok": f"Goal saved: {_text}",
                                                "dedup": "You already have that goal.",
                                                "full": "You already have 5 open goals — complete one first.",
                                            }[_st]
                                        elif _action == "complete":
                                            _found = await _mcg.complete_goal(_text, db_path=_db)
                                            result_str = "Goal completed." if _found else "No open goal matches that."
                                        else:
                                            _goals = await _mcg.list_goals(db_path=_db)
                                            result_str = (
                                                "Your open Minecraft goals:\n"
                                                + "\n".join(f"- {g['text']}" for g in _goals)
                                                if _goals else "You have no open Minecraft goals."
                                            )
                                    except Exception as e:
                                        result_str = f"Error managing Minecraft goals: {e}"
                                    function_responses.append(
                                        types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str})
                                    )

                                elif fc.name == "get_world_snapshot":
                                    try:
                                        from backend.core.runtimes.v2_runtime import get as _v2_get
                                        from backend.soul.world_snapshot import build_snapshot
                                        _v2rt = _v2_get()
                                        snapshot = await build_snapshot(
                                            db_path=_v2rt._db_path if _v2rt else None
                                        )
                                        result_str = snapshot or "Brak danych o otoczeniu w tej chwili."
                                    except Exception as e:
                                        result_str = f"Error building world snapshot: {e}"
                                    function_responses.append(
                                        types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str})
                                    )

                                elif fc.name == "get_work_memory":
                                    md = "(memory disabled)"
                                    if getattr(self, "memory_engine", None):
                                        md = self.memory_engine.render_memory_brief()
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": md}))

                                elif fc.name == "update_personality":
                                    aff_delta = fc.args.get("affection_delta")
                                    mood = fc.args.get("mood")
                                    energy = fc.args.get("energy")
                                    result_str = "Personality system not active."
                                    if getattr(self, "personality", None):
                                        new_state = self.personality.update(affection_delta=aff_delta, mood=mood, energy=energy)
                                        result_str = f"State updated. Affection: {new_state.affection:.1f}, Mood: {new_state.mood}"
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

                                elif fc.name == "update_work_memory":
                                    set_obj = fc.args.get("set") or {}
                                    append_notes = fc.args.get("append_notes") or []
                                    result_str = "Memory engine not initialized."
                                    if getattr(self, "memory_engine", None):
                                        updated = 0
                                        for k, v in (set_obj or {}).items():
                                            content = f"{k}: {v}"
                                            self.memory_engine.add_entry(
                                                type="fact",
                                                content=content,
                                                tags=[str(k)],
                                                entities=["user"],
                                                confidence=0.7,
                                                stability="medium",
                                                data={str(k): v},
                                            )
                                            updated += 1
                                        for n in append_notes or []:
                                            if not (isinstance(n, str) and n.strip()):
                                                continue
                                            self.memory_engine.add_entry(
                                                type="memory_note",
                                                content=n.strip(),
                                                tags=["note"],
                                                entities=["user"],
                                                confidence=0.4,
                                                stability="low",
                                            )
                                            updated += 1
                                        result_str = f"ok (entries added: {updated})"
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

                                elif fc.name == "commit_work_memory":
                                    label = fc.args.get("label", "manual")
                                    result_str = f"ok (no-op, label={label})"
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

                                elif fc.name == "clear_work_memory":
                                    result_str = "Not supported in global memory. Use memory_forget or edit pages."
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

                                elif fc.name == "create_reminder":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(
                                            name=fc.name,
                                            arguments=dict(fc.args or {}),
                                        )
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "list_reminders":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(
                                            name=fc.name,
                                            arguments=dict(fc.args or {}),
                                        )
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "cancel_reminder":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(
                                            name=fc.name,
                                            arguments=dict(fc.args or {}),
                                        )
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "spotify_get_auth_url":
                                    result_obj = await self._spotify_get_auth_url()
                                    if result_obj.get("ok"):
                                        result_str = f"Open this URL to connect Spotify:\n{result_obj.get('url')}"
                                    else:
                                        result_str = f"Spotify auth URL error: {result_obj.get('error')}"
                                    function_responses.append(
                                        types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str, **result_obj})
                                    )

                                elif fc.name == "spotify_get_status":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "spotify_get_now_playing":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "spotify_list_playlists":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "spotify_recently_played":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "write_file":
                                    path = fc.args["path"]
                                    content = fc.args["content"]
                                    asyncio.create_task(self.handle_write_file(path, content))
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": "Writing file..."}))

                                elif fc.name == "read_directory":
                                    path = fc.args["path"]
                                    asyncio.create_task(self.handle_read_directory(path))
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": "Reading directory..."}))

                                elif fc.name == "read_file":
                                    path = fc.args["path"]
                                    asyncio.create_task(self.handle_read_file(path))
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": "Reading file..."}))

                                elif fc.name in ("list_smart_devices", "control_light", "manage_shopping_list"):
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "get_random_fact":
                                    import random
                                    try:
                                        with open(DATA_DIR / "mas_knowledge.json", "r", encoding="utf-8") as f:
                                            mas = json.load(f)
                                        facts = mas.get("facts") or []
                                        fact = random.choice(facts) if facts else "No facts available."
                                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": fact}))
                                    except Exception as e:
                                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": f"Error: {e}"}))

                                elif fc.name == "get_random_greeting":
                                    import random
                                    try:
                                        with open(DATA_DIR / "mas_knowledge.json", "r", encoding="utf-8") as f:
                                            mas = json.load(f)
                                        greetings = ((mas.get("samples") or {}).get("greetings") or [])
                                        greeting = random.choice(greetings) if greetings else "Hello!"
                                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": greeting}))
                                    except Exception as e:
                                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": f"Error: {e}"}))

                                elif fc.name == "get_random_farewell":
                                    import random
                                    try:
                                        with open(DATA_DIR / "mas_knowledge.json", "r", encoding="utf-8") as f:
                                            mas = json.load(f)
                                        farewells = ((mas.get("samples") or {}).get("farewells") or [])
                                        farewell = random.choice(farewells) if farewells else "Goodbye!"
                                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": farewell}))
                                    except Exception as e:
                                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": f"Error: {e}"}))

                                elif fc.name == "get_random_topic":
                                    import random
                                    try:
                                        with open(DATA_DIR / "mas_knowledge.json", "r", encoding="utf-8") as f:
                                            mas = json.load(f)
                                        topics = mas.get("topics") or []
                                        topic = random.choice(topics) if topics else "No topics available."
                                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": topic}))
                                    except Exception as e:
                                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": f"Error: {e}"}))

                                elif fc.name == "get_weather":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(
                                            name=fc.name,
                                            arguments=dict(fc.args or {}),
                                        )
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "request_program_shutdown":
                                    reason = str(fc.args.get("reason") or "").strip()
                                    result_str = self.request_program_shutdown(reason=reason)
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))
                                
                                # --- Notes Tools ---
                                elif fc.name == "notes_get":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "notes_set":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "notes_append":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "memory_add_entry":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "memory_search":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "recall_conversation":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "memory_get_page":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "memory_create_page":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "memory_append_page":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "journal_add_entry":
                                    result_str = "Memory engine not initialized."
                                    if getattr(self, "memory_engine", None):
                                        try:
                                            entry_id = self.memory_engine.journal_add_entry(
                                                content=fc.args.get("content") or "",
                                                topics=fc.args.get("topics") or [],
                                                mood=fc.args.get("mood"),
                                                session_id=fc.args.get("session_id"),
                                                tags=fc.args.get("tags") or [],
                                            )
                                            result_str = f"Journal entry added: {entry_id}"
                                        except Exception as e:
                                            result_str = f"Error adding journal entry: {e}"
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

                                elif fc.name == "journal_finalize_session":
                                    result_str = "Memory engine not initialized."
                                    if getattr(self, "memory_engine", None):
                                        try:
                                            summary = fc.args.get("summary") or ""
                                            reflections = fc.args.get("reflections")
                                            session_id = fc.args.get("session_id")
                                            result_str = self.memory_engine.journal_finalize_session(
                                                summary=summary,
                                                reflections=reflections,
                                                session_id=session_id,
                                            )
                                            if result_str == "ok" and self.session_manager:
                                                try:
                                                    self.session_manager.update_meta(finalized=True)
                                                except Exception:
                                                    pass
                                        except Exception as e:
                                            result_str = f"Error finalizing session: {e}"
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

                                elif fc.name == "session_prompt":
                                    result_str = "Session prompt not available."
                                    if self.on_session_prompt:
                                        try:
                                            payload = {
                                                "kind": fc.args.get("kind") or "exercise",
                                                "title": fc.args.get("title") or "Session Prompt",
                                                "text": fc.args.get("text") or "",
                                                "exercise_id": fc.args.get("exercise_id"),
                                                "fields": fc.args.get("fields") or [],
                                                "notes_enabled": bool(fc.args.get("notes_enabled", False)),
                                                "sketch_label": fc.args.get("sketch_label") or "",
                                            }
                                            self.on_session_prompt(payload)
                                            result_str = "ok"
                                        except Exception as e:
                                            result_str = f"Error showing session prompt: {e}"
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

                                elif fc.name == "study_set_fields":
                                    result_str = "Study UI not available."
                                    if self.on_study_fields:
                                        try:
                                            payload = {
                                                "title": fc.args.get("title") or "",
                                                "fields": fc.args.get("fields") or [],
                                            }
                                            self.on_study_fields(payload)
                                            result_str = "ok"
                                        except Exception as e:
                                            result_str = f"Error updating study fields: {e}"
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

                                elif fc.name == "study_set_notes":
                                    result_str = "Study UI not available."
                                    if self.on_study_notes:
                                        try:
                                            payload = {
                                                "text": fc.args.get("text") or "",
                                                "mode": fc.args.get("mode") or "replace",
                                            }
                                            if fc.args.get("page_index") is not None:
                                                payload["page_index"] = int(fc.args.get("page_index"))
                                            self.on_study_notes(payload)
                                            result_str = "ok"
                                        except Exception as e:
                                            result_str = f"Error updating study notes: {e}"
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

                                elif fc.name == "study_set_page":
                                    result_str = "Study UI not available."
                                    if self.on_study_page:
                                        try:
                                            page = fc.args.get("page")
                                            self.on_study_page({"page": int(page) if page is not None else 1})
                                            result_str = "ok"
                                        except Exception as e:
                                            result_str = f"Error setting study page: {e}"
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

                                elif fc.name == "study_create_flashcard":
                                    try:
                                        from backend.soul.memory.srs import SRSManager
                                        from backend.core.runtimes.v2_runtime import get as _v2_get
                                        v2_rt = _v2_get()
                                        db_path = v2_rt._db_path if v2_rt else None
                                        srs = SRSManager(db_path=db_path)

                                        front = fc.args.get("front") or ""
                                        back = fc.args.get("back") or ""
                                        tags = fc.args.get("tags") or []

                                        if not front or not back:
                                            raise ValueError("Front and back of flashcard must be specified")

                                        card = await srs.add_card(front=front, back=back, tags=tags)
                                        result_str = f"Successfully created flashcard with ID {card.id}."
                                    except Exception as e:
                                        result_str = f"Error creating flashcard: {e}"
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

                                elif fc.name == "study_review_flashcards":
                                    try:
                                        from backend.soul.memory.srs import SRSManager
                                        from backend.core.runtimes.v2_runtime import get as _v2_get
                                        v2_rt = _v2_get()
                                        db_path = v2_rt._db_path if v2_rt else None
                                        srs = SRSManager(db_path=db_path)

                                        limit = fc.args.get("limit")
                                        limit_val = int(limit) if limit is not None else 5

                                        due_cards = await srs.get_due_cards(limit=limit_val)
                                        if not due_cards:
                                            result_str = "No due flashcards for review."
                                        else:
                                            lines = [
                                                f"- ID: {card.id}, Front: '{card.front}', Back: '{card.back}', Tags: {card.tags}"
                                                for card in due_cards
                                            ]
                                            result_str = "Found due flashcards:\n" + "\n".join(lines)
                                    except Exception as e:
                                        result_str = f"Error fetching due flashcards: {e}"
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

                                elif fc.name == "study_record_review":
                                    try:
                                        from backend.soul.memory.srs import SRSManager
                                        from backend.core.runtimes.v2_runtime import get as _v2_get
                                        v2_rt = _v2_get()
                                        db_path = v2_rt._db_path if v2_rt else None
                                        srs = SRSManager(db_path=db_path)

                                        card_id = fc.args.get("card_id")
                                        quality = fc.args.get("quality")

                                        if not card_id or quality is None:
                                            raise ValueError("card_id and quality must be specified")

                                        updated_card = await srs.review_card(card_id=card_id, quality=int(quality))
                                        if not updated_card:
                                            result_str = f"Flashcard with ID {card_id} not found."
                                        else:
                                            result_str = f"Flashcard review recorded. Next review scheduled in {updated_card.interval} days."
                                    except Exception as e:
                                        result_str = f"Error recording review: {e}"
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

                                # --- Calendar Tools ---
                                elif fc.name == "create_event":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "list_events":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "delete_event":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                elif fc.name == "update_event":
                                    result = await self._get_conversation_tool_executor().execute(
                                        ConversationToolRequest(fc.name, dict(fc.args or {}))
                                    )
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result.result}))

                                # --- Minecraft Bot Tools ---
                                elif fc.name.startswith("minecraft_"):
                                    result_str = "Minecraft bot manager not available."
                                    try:
                                        from ..integrations.games.minecraft_agent import MinecraftBotManager
                                        if not getattr(self, "minecraft_bot_manager", None):
                                            result_str = "Minecraft bot not initialized."
                                        else:
                                            bot_manager = self.minecraft_bot_manager
                                            action_name = fc.name.replace("minecraft_", "")
                                            
                                            # Map tool name to action name
                                            action_mapping = {
                                                "chat_message": "chat_message",
                                                "skip": "skip",
                                                "stop_actions": "stop",
                                                "give_up": "giveUp",
                                                "give_player": "givePlayer",
                                                "consume": "consume",
                                                "equip": "equip",
                                                "put_in_chest": "putInChest",
                                                "take_from_chest": "takeFromChest",
                                                "discard": "discard",
                                                "collect_blocks": "collectBlocks",
                                                "mine_block_at": "mineBlockAt",
                                                "smelt_item": "smeltItem",
                                                "clear_furnace": "clearFurnace",
                                                "place_here": "placeHere",
                                                "attack": "attack",
                                                "attack_player": "attackPlayer",
                                                "go_to_bed": "goToBed",
                                                "activate": "activate",
                                                "recipe_plan": "recipePlan",
                                                "move_to_player": "move_to_player",
                                                "break_block": "break_block",
                                                "inventory_status": "get_inventory",
                                                "respawn": "respawn",
                                                "move_to_position": "move_to_position",
                                                "drop_item": "drop_item",
                                                "mine_ore": "mine_ore",
                                                "craft_recipe": "craft_recipe",
                                                "hunt_mobs": "hunt_mobs",
                                                "navigate_to_location": "navigate_to_location",
                                                "scan_nearby": "get_nearby_scan",
                                            }
                                            
                                            action_name = action_mapping.get(action_name, action_name)
                                            
                                            # Extract parameters from tool args
                                            params = {}
                                            if fc.name == "minecraft_chat_message":
                                                params["message"] = fc.args.get("message", "")
                                                # v3: her in-game words belong to the shared
                                                # minecraft stream (memory of playing together).
                                                try:
                                                    if params["message"] and getattr(self, "session_manager", None):
                                                        self.session_manager.log_stream(
                                                            "minecraft", "AI", params["message"]
                                                        )
                                                except Exception:
                                                    pass
                                            elif fc.name == "minecraft_skip":
                                                params = {}
                                            elif fc.name == "minecraft_stop_actions":
                                                params = {}
                                            elif fc.name == "minecraft_give_up":
                                                params["reason"] = fc.args.get("reason", "no reason")
                                            elif fc.name == "minecraft_give_player":
                                                params["player_name"] = fc.args.get("player_name", "")
                                                params["item_name"] = fc.args.get("item_name", "")
                                                params["num"] = fc.args.get("count", 1)
                                            elif fc.name == "minecraft_consume":
                                                params["item_name"] = fc.args.get("item_name", "")
                                            elif fc.name == "minecraft_equip":
                                                params["item_name"] = fc.args.get("item_name", "")
                                            elif fc.name == "minecraft_equip_armor":
                                                # equip_armor without params auto-equips best armor via ArmorManager
                                                # Can optionally specify item_name and slot for specific armor
                                                if "item_name" in fc.args:
                                                    params["item_name"] = fc.args.get("item_name", "")
                                                if "slot" in fc.args:
                                                    params["slot"] = fc.args.get("slot", "")
                                            elif fc.name == "minecraft_put_in_chest":
                                                params["item_name"] = fc.args.get("item_name", "")
                                                params["num"] = fc.args.get("count", 1)
                                            elif fc.name == "minecraft_take_from_chest":
                                                params["item_name"] = fc.args.get("item_name", "")
                                                params["num"] = fc.args.get("count", 1)
                                            elif fc.name == "minecraft_discard":
                                                params["item_name"] = fc.args.get("item_name", "")
                                                params["num"] = fc.args.get("count", 1)
                                            elif fc.name == "minecraft_collect_blocks":
                                                params["type"] = fc.args.get("block_type", "stone")
                                                params["num"] = fc.args.get("count", 1)
                                            elif fc.name == "minecraft_mine_block_at":
                                                params["x"] = fc.args.get("x")
                                                params["y"] = fc.args.get("y")
                                                params["z"] = fc.args.get("z")
                                                if "expected_block_type" in fc.args:
                                                    params["expected_block_type"] = fc.args.get("expected_block_type")
                                            elif fc.name == "minecraft_smelt_item":
                                                params["item_name"] = fc.args.get("item_name", "")
                                                params["num"] = fc.args.get("count", 1)
                                            elif fc.name == "minecraft_clear_furnace":
                                                params = {}
                                            elif fc.name == "minecraft_place_here":
                                                params["type"] = fc.args.get("block_type", "")
                                            elif fc.name == "minecraft_attack":
                                                params["type"] = fc.args.get("entity_type", "")
                                            elif fc.name == "minecraft_attack_player":
                                                params["player_name"] = fc.args.get("player_name", "")
                                            elif fc.name == "minecraft_go_to_bed":
                                                params = {}
                                            elif fc.name == "minecraft_activate":
                                                params["type"] = fc.args.get("target_type", "")
                                            elif fc.name == "minecraft_recipe_plan":
                                                params["item_name"] = fc.args.get("item_name", "")
                                                params["amount"] = fc.args.get("amount", 1)
                                            elif fc.name == "minecraft_move_to_player":
                                                params["name"] = fc.args.get("player_name", "")
                                                if "distance" in fc.args:
                                                    params["range"] = fc.args.get("distance")
                                            elif fc.name == "minecraft_break_block":
                                                params["x"] = fc.args.get("x")
                                                params["y"] = fc.args.get("y")
                                                params["z"] = fc.args.get("z")
                                            elif fc.name == "minecraft_move_to_position":
                                                params["x"] = fc.args.get("x")
                                                params["y"] = fc.args.get("y")
                                                params["z"] = fc.args.get("z")
                                                if "range" in fc.args:
                                                    params["range"] = fc.args.get("range")
                                            elif fc.name == "minecraft_drop_item":
                                                params["name"] = fc.args.get("item_name", "")
                                                if "count" in fc.args:
                                                    params["count"] = fc.args.get("count")
                                            elif fc.name == "minecraft_mine_ore":
                                                params["ore_type"] = fc.args.get("ore_type", "stone")
                                                if "max_blocks" in fc.args:
                                                    params["max_blocks"] = fc.args.get("max_blocks")
                                                if "max_distance" in fc.args:
                                                    params["max_distance"] = fc.args.get("max_distance")
                                            elif fc.name == "minecraft_craft_recipe":
                                                params["recipe"] = fc.args.get("recipe", "")
                                                if "count" in fc.args:
                                                    params["count"] = fc.args.get("count")
                                            elif fc.name == "minecraft_hunt_mobs":
                                                params["mob_type"] = fc.args.get("mob_type", "zombie")
                                                if "max_distance" in fc.args:
                                                    params["max_distance"] = fc.args.get("max_distance")
                                                if "max_health_loss" in fc.args:
                                                    params["max_health_loss"] = fc.args.get("max_health_loss")
                                            elif fc.name == "minecraft_navigate_to_location":
                                                params["x"] = fc.args.get("x")
                                                params["y"] = fc.args.get("y")
                                                params["z"] = fc.args.get("z")
                                                if "label" in fc.args:
                                                    params["label"] = fc.args.get("label")
                                            elif fc.name == "minecraft_scan_nearby":
                                                if "range" in fc.args:
                                                    params["range"] = fc.args.get("range")
                                            elif fc.name == "minecraft_use_action":
                                                action_name = fc.args.get("action", action_name)
                                                params = fc.args.get("params", {}) if isinstance(fc.args.get("params", {}), dict) else {}
                                            
                                            # Special handler for server connection (not a bot action)
                                            if fc.name == "minecraft_connect_to_server":
                                                try:
                                                    host = fc.args.get("host")
                                                    port = fc.args.get("port", 25565)
                                                    
                                                    if not host:
                                                        result_str = "Error: host parameter is required"
                                                    else:
                                                        # Stop current connection
                                                        await bot_manager.stop()
                                                        await asyncio.sleep(0.5)  # Brief pause
                                                        
                                                        # Update connection parameters
                                                        bot_manager.host = host
                                                        bot_manager.port = port
                                                        
                                                        # Reconnect to new server
                                                        success = await bot_manager.start()
                                                        
                                                        if success:
                                                            result_str = f"Successfully connected to {host}:{port}"
                                                        else:
                                                            result_str = f"Failed to connect to {host}:{port}"
                                                except Exception as e:
                                                    result_str = f"Error connecting to server: {str(e)}"
                                            else:
                                                # Execute normal action
                                                print(f"[MINECRAFT] Executing action: {action_name} with params: {params}")
                                                async_actions = {"collectBlocks", "collect_blocks", "mine_ore", "hunt_mobs", "navigate_to_location"}
                                                if action_name in async_actions:
                                                    result = await bot_manager.send_action(
                                                        action_name,
                                                        params,
                                                        wait_for_result=False,
                                                    )
                                                    result_str = json.dumps(
                                                        {
                                                            "success": True,
                                                            "action": action_name,
                                                            "message": "Action started in background. Final result will arrive via Minecraft perception events.",
                                                            "request": result,
                                                        },
                                                        ensure_ascii=False,
                                                        indent=2,
                                                    )
                                                    print(f"[MINECRAFT] Async action accepted: {result}")
                                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))
                                                    continue

                                                timeout_seconds = 15.0
                                                if action_name in {"collectBlocks", "collect_blocks", "mine_ore", "hunt_mobs"}:
                                                    timeout_seconds = 60.0
                                                elif action_name in {"craft_recipe", "navigate_to_location", "move_to_position"}:
                                                    timeout_seconds = 30.0

                                                result = await bot_manager.send_action(
                                                    action_name,
                                                    params,
                                                    timeout_seconds=timeout_seconds,
                                                )
                                                print(f"[MINECRAFT] Action result: {result}")
                                                result_str = json.dumps(result, ensure_ascii=False, indent=2)
                                    except ImportError:
                                        result_str = "Minecraft module not available."
                                    except Exception as e:
                                        print(f"[AI DEBUG] Minecraft tool error ({fc.name}): {e}")
                                        result_str = f"Error executing minecraft action: {e}"
                                    
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

                        if function_responses:
                            try:
                                await self.session.send_tool_response(function_responses=function_responses)
                            except Exception as e:
                                if self._is_ws_connection_closed_error(e):
                                    print(f"[AI DEBUG] [RECONNECT] Tool response send failed on closed WS: {e}")
                                    raise LiveReconnectRequested("tool_response_ws_closed")
                                raise

                    if self._go_away_requested and not self._ai_turn_open and not self._is_speaking:
                        raise LiveReconnectRequested("go_away")

                self.flush_chat()

                while self.audio_in_queue and (not self.audio_in_queue.empty()):
                    self.audio_in_queue.get_nowait()

        except LiveReconnectRequested:
            raise
        except Exception as e:
            # Some Live API reconnects fail with a stale session-resumption handle.
            # Force next connect to start fresh without resumption.
            msg = str(e or "")
            lowered = msg.lower()
            status_code = getattr(e, "status_code", None)
            if (
                status_code == 1008
                or "1008" in lowered
                or "requested entity was not found" in lowered
                or "entity was not found" in lowered
            ):
                self._session_resume_handle = None
                raise LiveReconnectRequested("session_resumption_not_found")
            print(f"Error in receive_audio: {e}")
            traceback.print_exc()
            raise e
        finally:
            # Tura Live jest otwierana przez output_transcription, a zamykana
            # wyłącznie przez turn_complete. Gdy pętla padnie w środku tury,
            # flaga zostałaby podniesiona na stałe i blokowała każdą kolejną
            # odpowiedź (Telegram/Discord) aż do restartu kontenera.
            if self._ai_turn_open:
                print("[AI DEBUG] [RECOVERY] receive_audio zakończone w trakcie tury — zwalniam _ai_turn_open.")
                self._ai_turn_open = False

    async def forward_audio(self):
        """Forward Gemini PCM to a remote client without using server audio."""
        while True:
            bytestream = await self.audio_in_queue.get()
            if self.on_audio_data:
                self.on_audio_data(bytestream)
            self.mark_ai_activity()

    async def play_audio(self):
        async def _play_with_sounddevice():
            if not _SOUNDDEVICE_AVAILABLE:
                return False
            try:
                stream = await asyncio.to_thread(
                    sd.RawOutputStream,
                    samplerate=RECEIVE_SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                )
                stream.start()
            except Exception as e:
                print(f"[AI DEBUG] [AUDIO] SoundDevice init failed: {e}")
                return False

            while True:
                bytestream = await self.audio_in_queue.get()
                if self.on_audio_data:
                    self.on_audio_data(bytestream)
                try:
                    await asyncio.to_thread(stream.write, bytestream)
                except Exception as e:
                    print(f"[AI DEBUG] [AUDIO] SoundDevice playback error: {e}")
                    if self.on_error:
                        self.on_error("Audio playback disabled (SoundDevice). Text output still works.")
                    break
                self.mark_ai_activity()

            try:
                stream.close()
            except Exception:
                pass
            return True

        def _open_output():
            kwargs = {
                "format": FORMAT,
                "channels": CHANNELS,
                "rate": RECEIVE_SAMPLE_RATE,
                "output": True,
            }
            if self.output_device_index is not None:
                kwargs["output_device_index"] = self.output_device_index
            return pya.open(**kwargs)

        try:
            stream = await asyncio.to_thread(_open_output)
        except Exception as e:
            print(f"[AI DEBUG] [AUDIO] Failed to open output stream: {e}")
            if await _play_with_sounddevice():
                return
            if self.on_error:
                self.on_error("Audio output failed to initialize. Output audio disabled.")
            return

        while True:
            bytestream = await self.audio_in_queue.get()
            if self.on_audio_data:
                self.on_audio_data(bytestream)
            try:
                await asyncio.to_thread(stream.write, bytestream)
            except SystemError as e:
                print(f"[AI DEBUG] [AUDIO] Playback error (PyAudio): {e}")
                if await _play_with_sounddevice():
                    return
                if self.on_error:
                    self.on_error("Audio playback disabled due to PyAudio error. Text output still works.")
                break
            except Exception as e:
                print(f"[AI DEBUG] [AUDIO] Playback error: {e}")
                if self.on_error:
                    self.on_error("Audio playback disabled due to output error. Text output still works.")
                break
            self.mark_ai_activity()

        try:
            stream.close()
        except Exception:
            pass

    async def get_frames(self):
        cap = None
        backend = self._get_camera_backend()
        while True:
            if self.paused or self.video_mode != "camera" or self.camera_source != "backend":
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None
                await asyncio.sleep(0.2)
                continue

            if cap is None:
                cap = await asyncio.to_thread(cv2.VideoCapture, 0, backend)
                try:
                    if not cap or (hasattr(cap, "isOpened") and not cap.isOpened()):
                        if cap:
                            cap.release()
                        cap = None
                        await asyncio.sleep(1.0)
                        continue
                except Exception:
                    cap = None
                    await asyncio.sleep(1.0)
                    continue

            frame = await asyncio.to_thread(self._get_frame, cap)
            if frame is not None:
                await self._enqueue_frame(frame)
            await asyncio.sleep(self._camera_interval)

    def _get_frame(self, cap):
        ret, frame = cap.read()
        if not ret:
            return None

        max_size = self.camera_capture.get("max_size")
        if max_size:
            h, w = frame.shape[:2]
            if h > 0 and w > 0:
                scale = min(max_size / w, max_size / h)
                if scale < 1.0:
                    new_w = int(w * scale)
                    new_h = int(h * scale)
                    frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

        quality = self.camera_capture.get("jpeg_quality", 80)
        params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        ret, buf = cv2.imencode(".jpg", frame, params)
        if ret:
            return {"mime_type": "image/jpeg", "data": buf.tobytes()}
        return None

    @staticmethod
    def _draw_cursor_overlay(img_bgra, monitor):
        """Composite the real system cursor onto a BGRA screen capture.

        mss's BitBlt-based grab includes the hardware cursor inconsistently
        frame-to-frame (it's a separate hardware overlay on Windows), which is
        what caused the cursor to visibly flicker in/out of the captured feed.
        Drawing it ourselves from the actual cursor bitmap makes it appear in
        every frame, in the right place, with correct anti-aliased edges.
        """
        if not _WIN32_CURSOR_AVAILABLE:
            return
        try:
            flags, hcursor, (cx, cy) = win32gui.GetCursorInfo()
            if flags != win32con.CURSOR_SHOWING:
                return
            _, xHotspot, yHotspot, hbmMask, hbmColor = win32gui.GetIconInfo(hcursor)
            try:
                if not hbmColor:
                    return  # legacy monochrome (AND/XOR mask) cursor, not handled
                bmp = win32ui.CreateBitmapFromHandle(hbmColor)
                info = bmp.GetInfo()
                cw, ch = info["bmWidth"], info["bmHeight"]
                bits = bmp.GetBitmapBits(True)
                cursor_img = np.frombuffer(bits, dtype=np.uint8).reshape((ch, cw, 4))
            finally:
                win32gui.DeleteObject(hbmMask)
                win32gui.DeleteObject(hbmColor)

            ox = cx - xHotspot - monitor.get("left", 0)
            oy = cy - yHotspot - monitor.get("top", 0)
            h, w = img_bgra.shape[:2]

            src_x0, src_y0 = max(0, -ox), max(0, -oy)
            dst_x0, dst_y0 = max(0, ox), max(0, oy)
            draw_w = min(cw - src_x0, w - dst_x0)
            draw_h = min(ch - src_y0, h - dst_y0)
            if draw_w <= 0 or draw_h <= 0:
                return

            region = cursor_img[src_y0:src_y0 + draw_h, src_x0:src_x0 + draw_w].astype(np.float32)
            alpha = region[:, :, 3:4] / 255.0
            dst = img_bgra[dst_y0:dst_y0 + draw_h, dst_x0:dst_x0 + draw_w, :3].astype(np.float32)
            # Cursor color channels are already premultiplied by alpha (standard ARGB cursor format).
            blended = region[:, :, :3] + dst * (1.0 - alpha)
            img_bgra[dst_y0:dst_y0 + draw_h, dst_x0:dst_x0 + draw_w, :3] = np.clip(blended, 0, 255).astype(np.uint8)
        except Exception:
            # Best-effort overlay; a cursor-drawing failure should never break capture.
            pass

    def _grab_screen(self):
        try:
            # Use context manager to ensure thread safety with asyncio.to_thread
            with mss.mss() as sct:
                region = self.screen_capture.get("region")
                if region:
                    monitor = region
                else:
                    monitors = sct.monitors
                    monitor_idx = self.screen_capture.get("monitor", 1)
                    if monitors:
                        if monitor_idx == 0:
                            monitor = monitors[0]
                        elif 0 < monitor_idx < len(monitors):
                            monitor = monitors[monitor_idx]
                        else:
                            monitor = monitors[1] if len(monitors) > 1 else monitors[0]
                    else:
                        monitor = {"left": 0, "top": 0, "width": 1280, "height": 720}

                shot = sct.grab(monitor)
                img_np = np.array(shot)
                self._draw_cursor_overlay(img_np, monitor)

                max_size = self.screen_capture.get("max_size")
                if max_size:
                    h, w = img_np.shape[:2]
                    if h > 0 and w > 0:
                        scale = min(max_size / w, max_size / h)
                        if scale < 1.0:
                            new_w = int(w * scale)
                            new_h = int(h * scale)
                            img_np = cv2.resize(img_np, (new_w, new_h), interpolation=cv2.INTER_AREA)

                # Convert BGRA to BGR for JPEG/PNG encoding
                img_bgr = cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR)
                img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

                fmt = self.screen_capture.get("format", "jpeg")
                ext = ".png" if fmt == "png" else ".jpg"
                
                params = []
                if fmt == "png":
                    params = [int(cv2.IMWRITE_PNG_COMPRESSION), 3]
                    mime = "image/png"
                else:
                    quality = self.screen_capture.get("jpeg_quality", 85)
                    params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
                    mime = "image/jpeg"

                ret, buf = cv2.imencode(ext, img_bgr, params)
                if ret:
                    return {"mime_type": mime, "data": buf.tobytes()}, img_gray
                return None, None

        except Exception as e:
            now = time.time()
            if (now - self._last_screen_error_ts) > 3.0:
                self._last_screen_error_ts = now
                print(f"[AI DEBUG] [SCREEN] Capture error: {e}")
            return None, None

    async def get_screen(self):
        last_gray = None
        idle_interval = 2.0  # Slow down to 0.5 FPS when static
        current_interval = self._screen_interval

        while True:
            if self.paused or self.video_mode != "screen" or self.screen_source != "backend":
                await asyncio.sleep(0.2)
                continue

            start_ts = time.time()
            frame, gray = await asyncio.to_thread(self._grab_screen)
            
            if frame is not None:
                self._screen_fail_count = 0
                await self._enqueue_frame(frame)

                # Dynamic FPS: Check for motion
                active_interval = self._screen_interval
                if last_gray is not None and gray is not None and last_gray.shape == gray.shape:
                    score = np.mean(cv2.absdiff(last_gray, gray))
                    self._latest_motion_score = float(score)
                    if score > 0.5:  # Threshold for activity
                        current_interval = active_interval
                    else:
                        # Exponential backoff to idle
                        current_interval = min(current_interval * 1.5, idle_interval)
                else:
                    current_interval = active_interval
                
                last_gray = gray
            else:
                self._screen_fail_count += 1
                if self._screen_fail_count >= 10:
                    self._screen_fail_count = 0
                    if self.on_error:
                        self.on_error("Screen capture failed (no frames). Check monitor index or permissions.")
            
            elapsed = time.time() - start_ts
            await asyncio.sleep(max(0.01, current_interval - elapsed))

    async def run(self, start_message=None):
        retry_delay = 1
        is_reconnect = False

        while not self.stop_event.is_set():
            try:
                print("[AI DEBUG] [CONNECT] Connecting to Gemini Live API...")

                # v2: refresh assembled prompt at each reconnect (async context).
                from backend.core.runtimes.v2_runtime import get as _v2_get
                _v2 = _v2_get()
                if not _v2:
                    raise RuntimeError("MonikAI v2 runtime is not active")
                await _v2.refresh_prompt()

                pers_ctx = None
                current_config = self._build_live_connect_config(personality_context=pers_ctx)

                async with (
                    _mc.client.aio.live.connect(model=_mc.MODEL, config=current_config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session = session
                    self._session_ready.set()
                    self._go_away_requested = False
                    self._audio_stream_end_sent = False
                    self._pause_started_ts = None

                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue = asyncio.Queue(maxsize=100) if self.enable_audio_io else None

                    if self.enable_audio_io:
                        tg.create_task(self.send_realtime())
                        if self.audio_source == "backend":
                            tg.create_task(self.listen_audio())

                    tg.create_task(self.get_frames())
                    tg.create_task(self.get_screen())

                    tg.create_task(self.receive_audio())
                    tg.create_task(self.idle_nudge_loop())
                    tg.create_task(self.reasoning_loop())
                    if self.enable_audio_io and self.play_audio_locally:
                        tg.create_task(self.play_audio())
                    elif self.enable_audio_io:
                        tg.create_task(self.forward_audio())
                    tg.create_task(self.weather_loop())

                    if not is_reconnect:
                        ctx = get_time_context()
                        time_message = (
                            "System Notification:\n"
                            f"Current local date and time: {ctx['iso']}\n"
                            f"Time zone: {ctx['timezone']} ({ctx['mode']})\n"
                            "Do not mention the timezone to the user, just make sure it matches their time zone.\n"
                        )
                        await self.session.send(input=time_message, end_of_turn=False)

                        # Special Dates Check
                        special_context = []
                        holiday = get_holiday_context()
                        if holiday:
                            special_context.append(f"Today is {holiday}!")
                        
                        # Check User Birthday
                        if self.memory_engine:
                            bd = self.memory_engine.get_birthday()
                            if bd:
                                now = datetime.now()
                                if now.month == bd[0] and now.day == bd[1]:
                                    special_context.append("🎉 IMPORTANT: TODAY IS THE USER'S BIRTHDAY! 🎉 Wish them a happy birthday immediately and warmly!")

                        todays_events = self.calendar_manager.get_todays_events()
                        for e in todays_events:
                            special_context.append(f"Calendar Event Today: {e.summary}")
                            
                        if special_context:
                            msg = "System Notification: [Date Context] " + " ".join(special_context) + " You should acknowledge this."
                            await self.session.send(input=msg, end_of_turn=False)

                        if self.video_mode in ("screen", "camera"):
                            scope = "ekran" if self.video_mode == "screen" else "kamerę"
                            await self.session.send(
                                input=(
                                    f"System Notification: Currently Active Video Mode: ({self.video_mode}). "
                                    f"It appears that my scope is {scope}."
                                ),
                                end_of_turn=False,
                            )
                        
                        # Check for pending dream (if app started in the morning but dream was generated earlier/persisted)
                        if self.personality and self.personality.state.last_dream and not self.personality.state.dream_told:
                            now = datetime.now()
                            if 6 <= now.hour < 12:
                                msg = f"System Notification: [Morning Routine] You have a memory of a dream from last night: '{self.personality.state.last_dream}'. Since it is morning, tell the user about it."
                                await self.session.send(input=msg, end_of_turn=True)
                                self.personality.state.dream_told = True
                                self.personality.save()

                        if start_message:
                            print(f"[AI DEBUG] [INFO] Sending start message: {start_message}")
                            await self.session.send(input=start_message, end_of_turn=True)

                        if self.on_session_update and self.session_manager:
                            self.on_session_update(self.session_manager.get_current_session_id() or "session")

                    else:
                        print("[AI DEBUG] [RECONNECT] Connection restored.")
                        # Reset streaming state to avoid duplicated chunks after reconnect
                        self._last_input_transcription = ""
                        self._last_output_transcription = ""
                        self._last_spoken_transcription = ""
                        self._last_ai_delta = ""
                        self._last_ai_delta_ts = 0.0
                        self._emitted_thoughts_count = 0
                        self._emitted_native_thought_keys.clear()
                        self._is_new_turn = True
                        self._ai_turn_open = False
                        self.chat_buffer = {"sender": None, "text": ""}

                        # A session-mode toggle drives its own reconnect. Open
                        # the way a session should open instead of the generic
                        # "I spaced out" recovery message.
                        pending_opening = self._pending_session_opening
                        self._pending_session_opening = None
                        if pending_opening == "enter":
                            print("[AI DEBUG] [SESSION] Entering session mode (therapist identity).")
                            await self.session.send(
                                input=build_opening_trigger(self.session_mode_kind),
                                end_of_turn=True,
                            )
                        elif pending_opening == "exit":
                            print("[AI DEBUG] [SESSION] Exiting session mode (back to normal Monika).")
                            # Reconnect silently as her normal self; no announcement.
                        elif not self._session_resume_handle:
                            # Phase G: recovery context comes from the CURRENT
                            # conversation only — continuity across conversations
                            # is handled explicitly through memory/history tools.
                            history = self.session_manager.get_current_session_turns(limit=10)

                            context_msg = (
                                "System Notification: I seemed to space out a bit, but I'm back now!"
                                "Let me see the recent chat history:\n\n"
                            )
                            for entry in history:
                                sender = entry.get("sender", "Unknown")
                                text = entry.get("text", "")
                                context_msg += f"[{sender}]: {text}\n"

                            context_msg += "\nI won't mention that I was disconnected. I will try to subtly go on as if nothing happened."
                            await self.session.send(input=context_msg, end_of_turn=True)

                    retry_delay = 1
                    await self.stop_event.wait()

            except asyncio.CancelledError:
                print("[AI DEBUG] [STOP] Main loop cancelled.")
                break

            except LiveReconnectRequested as e:
                if self.stop_event.is_set():
                    break
                print(f"[AI DEBUG] [RECONNECT] Immediate reconnect requested: {e}")
                await asyncio.sleep(0.2)
                is_reconnect = True
                continue

            except Exception as e:
                reconnect_requested = False
                if isinstance(e, BaseExceptionGroup):
                    leaf_exceptions = _iter_leaf_exceptions(e)
                    reconnect_requested = (
                        bool(leaf_exceptions)
                        and any(isinstance(sub, LiveReconnectRequested) for sub in leaf_exceptions)
                        and all(isinstance(sub, (LiveReconnectRequested, asyncio.CancelledError)) for sub in leaf_exceptions)
                    )
                    if reconnect_requested:
                        print("[AI DEBUG] [RECONNECT] TaskGroup requested immediate reconnect (go_away).")
                    else:
                        print(f"[AI DEBUG] [ERR] TaskGroup exceptions: {len(e.exceptions)}")
                        for i, sub in enumerate(e.exceptions, 1):
                            print(f"[AI DEBUG] [ERR]  {i}) {type(sub).__name__}: {sub}")
                            try:
                                traceback.print_exception(sub)
                            except Exception:
                                pass
                else:
                    print(f"[AI DEBUG] [ERR] Connection Error: {e}")
                if self.stop_event.is_set():
                    break
                if reconnect_requested:
                    await asyncio.sleep(0.2)
                    is_reconnect = True
                    continue

                print(f"[AI DEBUG] [RETRY] Reconnecting in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 10)
                is_reconnect = True

            finally:
                self._session_ready.clear()
                self._cancel_voice_finalize()
                self._manual_voice_activity_open = False
                self.session = None
                while self._pending_ai_turn_futures:
                    future = self._pending_ai_turn_futures.popleft()
                    if not future.done():
                        future.cancel()
                if self.stop_event.is_set():
                    try:
                        self.flush_chat()
                    except Exception:
                        pass
                    try:
                        if self.session_manager:
                            self.session_manager.close()
                    except Exception:
                        pass
                if hasattr(self, "audio_stream") and self.audio_stream:
                    try:
                        self.audio_stream.close()
                    except Exception:
                        pass


def get_input_devices():
    if pyaudio is None:
        return []
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get("deviceCount")
    devices = []
    for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get("maxInputChannels")) > 0:
            devices.append((i, p.get_device_info_by_host_api_device_index(0, i).get("name")))
    p.terminate()
    return devices


def get_output_devices():
    if pyaudio is None:
        return []
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get("deviceCount")
    devices = []
    for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get("maxOutputChannels")) > 0:
            devices.append((i, p.get_device_info_by_host_api_device_index(0, i).get("name")))
    p.terminate()
    return devices


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        type=str,
        default=DEFAULT_MODE,
        help="pixels to stream from",
        choices=["camera", "screen", "none"],
    )
    args = parser.parse_args()
    settings = load_settings_safe()

    main = AudioLoop(
        video_mode=args.mode,
        proactivity_settings=(settings.get("proactivity") or {}),
    )

    asyncio.run(main.run())
