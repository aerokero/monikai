import asyncio
import io
import json
import wave
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.telegram_bot import (
    TelegramBotService,
    TelegramChatSession,
    _pcm_to_wav_bytes,
)
from backend.services.calendar_manager import CalendarEvent


def test_pcm_to_wav_bytes():
    # 240 samples of 16-bit silence
    pcm = b"\x00\x00" * 240
    wav_bytes = _pcm_to_wav_bytes(pcm, sample_rate=24000, channels=1, sampwidth=2)
    assert len(wav_bytes) > len(pcm)
    assert wav_bytes.startswith(b"RIFF")
    
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 24000
        assert wf.getnframes() == 240


def test_telegram_session_voice_mode():
    session = TelegramChatSession(
        chat_id=123,
        user_label="test_user",
        settings_getter=lambda: {},
    )
    assert session.voice_mode == "auto"

    msg = session.set_voice_mode("on")
    assert session.voice_mode == "on"
    assert "Włączono" in msg

    msg = session.set_voice_mode("off")
    assert session.voice_mode == "off"
    assert "Wyłączono" in msg

    msg = session.set_voice_mode("auto")
    assert session.voice_mode == "auto"
    assert "automatyczny" in msg.lower()


def test_telegram_session_today_summary():
    mock_cal = MagicMock()
    session = TelegramChatSession(
        chat_id=123,
        user_label="test_user",
        settings_getter=lambda: {},
        calendar_manager=mock_cal,
    )

    now = datetime.now()
    ev1 = CalendarEvent(
        id="1",
        summary="Spotkanie z zespołem",
        start_iso=now.replace(hour=10, minute=0).isoformat(),
        end_iso=now.replace(hour=11, minute=0).isoformat(),
    )
    mock_cal.list_events.return_value = [ev1]

    summary = session.get_today_summary()
    assert "Spotkanie z zespołem" in summary
    assert "10:00-11:00" in summary


def test_telegram_session_weather_and_profile():
    mock_personality = MagicMock()
    mock_personality.state.weather = "22°C, słonecznie"

    session = TelegramChatSession(
        chat_id=123,
        user_label="test_user",
        settings_getter=lambda: {},
        personality=mock_personality,
    )

    w_summary = session.get_weather_summary()
    assert "22°C, słonecznie" in w_summary


def test_telegram_session_remind_command():
    mock_reminders = MagicMock()
    mock_rem = MagicMock()
    mock_rem.id = "rem_123"
    mock_rem.message = "zadzwoń do mamy"
    mock_rem.when_iso = "2026-03-15T18:30:00"
    mock_reminders.create.return_value = mock_rem

    session = TelegramChatSession(
        chat_id=123,
        user_label="test_user",
        settings_getter=lambda: {},
        reminder_manager=mock_reminders,
    )

    resp_txt, rem_obj = session.create_reminder_from_command("zadzwoń do mamy | 45m")
    assert rem_obj is not None
    assert rem_obj.id == "rem_123"
    assert "zadzwoń do mamy" in resp_txt


@pytest.mark.asyncio
async def test_telegram_bot_service_commands_and_callbacks():
    bot = TelegramBotService(
        token="test_token",
        settings_getter=lambda: {},
        allowed_chat_id=12345,
    )
    
    # Test command parser
    cmd, args = bot._parse_command("/today")
    assert cmd == "today"
    assert args == ""

    cmd, args = bot._parse_command("/voice on")
    assert cmd == "voice"
    assert args == "on"

    cmd, args = bot._parse_command("/remind kupić chleb | 10m")
    assert cmd == "remind"
    assert args == "kupić chleb | 10m"

    # Test callback query handling
    bot._api_call = AsyncMock(return_value={"ok": True})
    mock_reminders = MagicMock()
    mock_reminders.cancel.return_value = True
    bot.reminder_manager = mock_reminders

    cb_query = {
        "id": "cb_999",
        "data": "del_rem:rem_123",
        "message": {"chat": {"id": 12345}, "message_id": 42, "text": "Przypomnienie: kup mleko"},
        "from": {"username": "test_user"},
    }

    await bot._handle_callback_query(cb_query)
    mock_reminders.cancel.assert_called_once_with("rem_123")
    assert bot._api_call.call_count >= 1


@pytest.mark.asyncio
async def test_telegram_document_text_handling():
    bot = TelegramBotService(
        token="test_token",
        settings_getter=lambda: {},
        allowed_chat_id=12345,
    )

    bot._api_call = AsyncMock(return_value={"ok": True, "result": {"file_path": "documents/script.py"}})
    bot._download_telegram_file = AsyncMock(return_value=b"print('Hello world!')")

    msg = {
        "document": {
            "file_id": "doc_1",
            "file_name": "script.py",
            "mime_type": "text/x-python",
        }
    }

    attachments = await bot._build_message_attachments(msg)
    assert len(attachments) == 1
    assert attachments[0]["name"] == "script.py"
    assert attachments[0]["text_content"] == "print('Hello world!')"

