from types import SimpleNamespace

from backend.core import monikai
from backend.core.conversation_tool_executor import CoreConversationToolExecutor
from backend.core.monikai import AudioLoop
from backend.conversation.tools import (
    ConversationToolRequest,
    ConversationToolResult,
)


async def test_read_only_tool_result_returns_to_text_author(monkeypatch):
    captured = {}

    class FakeThinker:
        async def prepare_spoken_reply(self, text, *, turn_evidence=None):
            captured["text"] = text
            captured["evidence"] = turn_evidence
            return "Jest 9:15."

    monkeypatch.setattr(
        monikai,
        "get_time_context",
        lambda: {
            "iso": "2026-07-30T09:15:00+02:00",
            "timezone": "Europe/Warsaw",
            "mode": "summer",
            "offset": "+02:00",
        },
    )
    loop = AudioLoop.__new__(AudioLoop)
    loop.permissions = {"get_time_context": False}
    loop.thinker = FakeThinker()
    loop._last_tool_trace = {}

    outcome = await loop.author_read_only_tool_turn("Która jest godzina?")

    assert outcome.handled is True
    assert outcome.tool_name == "get_time_context"
    assert outcome.reply == "Jest 9:15."
    assert "2026-07-30T09:15:00+02:00" in captured["evidence"]
    assert loop._last_tool_trace["status"] == "authored"


async def test_missing_confirmation_channel_denies_tool_and_authors_result():
    captured = {}

    class FakeThinker:
        async def prepare_spoken_reply(self, text, *, turn_evidence=None):
            captured["evidence"] = turn_evidence
            return "Nie wykonałam tej operacji."

    loop = AudioLoop.__new__(AudioLoop)
    loop.permissions = {"get_time_context": True}
    loop.on_tool_confirmation = None
    loop.auto_allow_tools_without_confirmation = False
    loop.thinker = FakeThinker()
    loop._last_tool_trace = {}

    outcome = await loop.author_read_only_tool_turn("Która jest godzina?")

    assert outcome.handled is True
    assert outcome.tool_name == "get_time_context"
    assert loop._last_tool_trace["authorized"] is False
    assert "status=error" in captured["evidence"]


async def test_reminder_listing_is_grounded_before_natural_reply():
    captured = {}

    class FakeThinker:
        async def prepare_spoken_reply(self, text, *, turn_evidence=None):
            captured["evidence"] = turn_evidence
            return "Masz jedno przypomnienie: raport jutro o dziewiątej."

    loop = AudioLoop.__new__(AudioLoop)
    loop.permissions = {"list_reminders": False}
    loop.thinker = FakeThinker()
    loop.reminder_manager = SimpleNamespace(
        list=lambda: [
            SimpleNamespace(
                id="r1",
                when_iso="2026-07-31T09:00:00+02:00",
                message="raport",
            )
        ]
    )
    loop._last_tool_trace = {}

    outcome = await loop.author_read_only_tool_turn("Jakie mam przypomnienia?")

    assert outcome.handled is True
    assert "r1 | 2026-07-31T09:00:00+02:00 | raport" in captured["evidence"]


async def test_native_plan_creates_reminder_exactly_once():
    created = []
    evidence = []

    class FakeThinker:
        async def plan_tool_calls(self, text, *, tools, runtime_context):
            return (
                ConversationToolRequest(
                    name="create_reminder",
                    arguments={"message": "raport", "in_minutes": 10},
                ),
            )

        async def prepare_spoken_reply(self, text, *, turn_evidence=None):
            evidence.append(turn_evidence)
            return "Jasne, przypomnę ci za dziesięć minut."

    def create(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(
            id="r1",
            when_iso="2026-07-30T09:25:00+02:00",
            message=kwargs["message"],
        )

    loop = AudioLoop.__new__(AudioLoop)
    loop.permissions = {"create_reminder": False}
    loop.thinker = FakeThinker()
    loop.reminder_manager = SimpleNamespace(create=create)
    loop.personality = None
    loop._last_tool_trace = {}

    outcome = await loop.author_tool_turn(
        "Przypomnij mi o raporcie za dziesięć minut."
    )

    assert outcome.handled is True
    assert outcome.reply.startswith("Jasne")
    assert len(created) == 1
    assert created[0]["in_minutes"] == 10
    assert "Reminder created. ID: r1" in evidence[0]


async def test_denied_mutating_tool_is_not_executed():
    created = []
    evidence = []

    class FakeThinker:
        async def plan_tool_calls(self, text, *, tools, runtime_context):
            return (
                ConversationToolRequest(
                    name="create_reminder",
                    arguments={"message": "raport", "in_minutes": 10},
                ),
            )

        async def prepare_spoken_reply(self, text, *, turn_evidence=None):
            evidence.append(turn_evidence)
            return "Okej, nie ustawiłam przypomnienia."

    loop = AudioLoop.__new__(AudioLoop)
    loop.permissions = {"create_reminder": True}
    loop.auto_allow_tools_without_confirmation = False
    loop._pending_confirmations = {}
    loop.thinker = FakeThinker()
    loop.reminder_manager = SimpleNamespace(
        create=lambda **kwargs: created.append(kwargs)
    )
    loop.personality = None
    loop._last_tool_trace = {}

    def deny(payload):
        loop.resolve_tool_confirmation(payload["id"], False)

    loop.on_tool_confirmation = deny

    outcome = await loop.author_tool_turn(
        "Przypomnij mi o raporcie za dziesięć minut."
    )

    assert outcome.handled is True
    assert created == []
    assert loop._last_tool_trace["authorized"] is False
    assert "User denied" in evidence[0]


async def test_confirmed_mutating_tool_executes_once():
    created = []

    class FakeThinker:
        async def plan_tool_calls(self, text, *, tools, runtime_context):
            return (
                ConversationToolRequest(
                    name="create_reminder",
                    arguments={"message": "raport", "in_minutes": 10},
                ),
            )

        async def prepare_spoken_reply(self, text, *, turn_evidence=None):
            return "Przypomnienie ustawione."

    def create(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(
            id="r2",
            when_iso="2026-07-30T09:25:00+02:00",
            message=kwargs["message"],
        )

    loop = AudioLoop.__new__(AudioLoop)
    loop.permissions = {"create_reminder": True}
    loop.auto_allow_tools_without_confirmation = False
    loop._pending_confirmations = {}
    loop.thinker = FakeThinker()
    loop.reminder_manager = SimpleNamespace(create=create)
    loop.personality = None
    loop._last_tool_trace = {}

    def approve(payload):
        loop.resolve_tool_confirmation(payload["id"], True)

    loop.on_tool_confirmation = approve

    outcome = await loop.author_tool_turn(
        "Przypomnij mi o raporcie za dziesięć minut."
    )

    assert outcome.reply == "Przypomnienie ustawione."
    assert len(created) == 1
    assert loop._last_tool_trace["authorized"] is True


async def test_native_calendar_plan_creates_event_exactly_once():
    created = []
    evidence = []

    class FakeThinker:
        async def plan_tool_calls(self, text, *, tools, runtime_context):
            return (
                ConversationToolRequest(
                    name="create_event",
                    arguments={
                        "summary": "Dentysta",
                        "start_iso": "2026-08-01T12:00:00+02:00",
                        "end_iso": "2026-08-01T13:00:00+02:00",
                    },
                ),
            )

        async def prepare_spoken_reply(self, text, *, turn_evidence=None):
            evidence.append(turn_evidence)
            return "Dodałam dentystę do kalendarza na sobotę o dwunastej."

    def create_event(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(
            id="e1",
            summary=kwargs["summary"],
            start_iso=kwargs["start_iso"],
            end_iso=kwargs["end_iso"],
        )

    loop = AudioLoop.__new__(AudioLoop)
    loop.permissions = {"create_event": False}
    loop.thinker = FakeThinker()
    loop.reminder_manager = None
    loop.calendar_manager = SimpleNamespace(create_event=create_event)
    loop.on_calendar_update = None
    loop.personality = None
    loop._last_tool_trace = {}

    outcome = await loop.author_tool_turn(
        "Dodaj wydarzenie do kalendarza: dentysta w sobotę o 12."
    )

    assert outcome.handled is True
    assert len(created) == 1
    assert created[0]["summary"] == "Dentysta"
    assert "Event created. ID: e1" in evidence[0]


async def test_native_notes_plan_appends_without_replacing(tmp_path):
    notes_path = tmp_path / "notes.md"
    notes_path.write_text("stara notatka\n", encoding="utf-8")

    class FakeThinker:
        async def plan_tool_calls(self, text, *, tools, runtime_context):
            return (
                ConversationToolRequest(
                    name="notes_append",
                    arguments={"content": "kup mleko"},
                ),
            )

        async def prepare_spoken_reply(self, text, *, turn_evidence=None):
            return "Dopisałam „kup mleko” do notatek."

    loop = AudioLoop.__new__(AudioLoop)
    loop.permissions = {"notes_append": False}
    loop.thinker = FakeThinker()
    loop.reminder_manager = None
    loop.calendar_manager = None
    loop.notes_path = notes_path
    loop.on_calendar_update = None
    loop.personality = None
    loop._last_tool_trace = {}

    outcome = await loop.author_tool_turn("Dopisz do notatek: kup mleko.")

    assert outcome.handled is True
    assert notes_path.read_text(encoding="utf-8") == "stara notatka\nkup mleko\n"


async def test_explicit_memory_write_executes_once_and_returns_evidence():
    calls = []
    evidence = []

    class FakeThinker:
        async def plan_tool_calls(self, text, *, tools, runtime_context):
            return (
                ConversationToolRequest(
                    name="memory_add_entry",
                    arguments={
                        "type": "semantic",
                        "content": "Bartosz nie lubi oliwek.",
                    },
                ),
            )

        async def prepare_spoken_reply(self, text, *, turn_evidence=None):
            evidence.append(turn_evidence)
            return "Dobrze, zapamiętam, że nie lubisz oliwek."

    class FakeExecutor:
        async def execute(self, request):
            calls.append(request)
            return ConversationToolResult(
                name=request.name,
                result="ok: mem_1",
            )

    loop = AudioLoop.__new__(AudioLoop)
    loop.permissions = {"memory_add_entry": False}
    loop.thinker = FakeThinker()
    loop._conversation_tool_executor = FakeExecutor()
    loop._last_tool_trace = {}

    outcome = await loop.author_tool_turn(
        "Zapamiętaj, że nie lubię oliwek."
    )

    assert outcome.handled is True
    assert len(calls) == 1
    assert calls[0].arguments["content"] == "Bartosz nie lubi oliwek."
    assert "ok: mem_1" in evidence[0]


async def test_explicit_light_control_executes_once_and_returns_evidence():
    calls = []
    evidence = []

    class FakeThinker:
        async def plan_tool_calls(self, text, *, tools, runtime_context):
            return (
                ConversationToolRequest(
                    name="control_light",
                    arguments={
                        "target": "lampa w salonie",
                        "action": "turn_on",
                    },
                ),
            )

        async def prepare_spoken_reply(self, text, *, turn_evidence=None):
            evidence.append(turn_evidence)
            return "Włączyłam lampę w salonie."

    class FakeExecutor:
        async def execute(self, request):
            calls.append(request)
            return ConversationToolResult(
                name=request.name,
                result="Turned ON 'lampa w salonie'. (hue)",
            )

    loop = AudioLoop.__new__(AudioLoop)
    loop.permissions = {"control_light": False}
    loop.thinker = FakeThinker()
    loop._conversation_tool_executor = FakeExecutor()
    loop._last_tool_trace = {}

    outcome = await loop.author_tool_turn("Włącz lampę w salonie.")

    assert outcome.handled is True
    assert len(calls) == 1
    assert calls[0].arguments["action"] == "turn_on"
    assert "Turned ON" in evidence[0]


async def test_casual_fact_does_not_trigger_memory_planner():
    class FakeThinker:
        async def plan_tool_calls(self, *args, **kwargs):
            raise AssertionError("planner must not run for ordinary facts")

    loop = AudioLoop.__new__(AudioLoop)
    loop.thinker = FakeThinker()
    loop._last_tool_trace = {}

    outcome = await loop.author_tool_turn("Nie lubię oliwek.")

    assert outcome.handled is False


async def test_memory_page_read_cannot_escape_pages_directory(tmp_path):
    pages = tmp_path / "memory" / "pages"
    pages.mkdir(parents=True)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    engine = SimpleNamespace(pages_dir=pages)
    executor = CoreConversationToolExecutor(
        reminder_manager=None,
        calendar_manager=None,
        notes_path=None,
        memory_engine=engine,
        session_manager=None,
        spotify_manager=None,
        smart_home_executor=None,
        get_memory_db_path=lambda: None,
        get_time_context_fn=lambda: {},
        get_personality=lambda: None,
    )

    result = await executor.execute(
        ConversationToolRequest(
            "memory_get_page",
            {"path": str(outside)},
        )
    )

    assert result.ok is False
    assert "escapes memory/pages" in result.result


async def test_memory_page_append_preserves_existing_content(tmp_path):
    from backend.services.memory_adapter import MemoryEngine

    engine = MemoryEngine(base_dir=tmp_path)
    page = engine.pages_dir / "topics" / "projekt.md"
    page.parent.mkdir(parents=True)
    page.write_text("stary wpis\n", encoding="utf-8")
    executor = CoreConversationToolExecutor(
        reminder_manager=None,
        calendar_manager=None,
        notes_path=None,
        memory_engine=engine,
        session_manager=None,
        spotify_manager=None,
        smart_home_executor=None,
        get_memory_db_path=lambda: None,
        get_time_context_fn=lambda: {},
        get_personality=lambda: None,
    )

    result = await executor.execute(
        ConversationToolRequest(
            "memory_append_page",
            {"path": "topics/projekt.md", "content": "nowy wpis"},
        )
    )

    assert result.ok is True
    content = page.read_text(encoding="utf-8")
    assert "stary wpis" in content
    assert "nowy wpis" in content


async def test_native_spotify_now_playing_is_grounded_once():
    manager_calls = []
    evidence = []

    class FakeSpotify:
        def get_now_playing(self):
            manager_calls.append(True)
            return {
                "is_playing": True,
                "item": {"name": "In Your Room", "artists": ["Depeche Mode"]},
            }

    class FakeThinker:
        async def plan_tool_calls(self, text, *, tools, runtime_context):
            return (ConversationToolRequest("spotify_get_now_playing"),)

        async def prepare_spoken_reply(self, text, *, turn_evidence=None):
            evidence.append(turn_evidence)
            return "Leci „In Your Room” Depeche Mode."

    loop = AudioLoop.__new__(AudioLoop)
    loop.permissions = {"spotify_get_now_playing": False}
    loop.thinker = FakeThinker()
    loop.spotify_manager = FakeSpotify()
    loop.reminder_manager = None
    loop.calendar_manager = None
    loop.notes_path = None
    loop.memory_engine = None
    loop.session_manager = None
    loop.on_calendar_update = None
    loop.personality = None
    loop._last_tool_trace = {}

    outcome = await loop.author_tool_turn("Co teraz leci na Spotify?")

    assert outcome.handled is True
    assert len(manager_calls) == 1
    assert "In Your Room" in evidence[0]


async def test_spotify_unavailable_returns_error_evidence():
    executor = CoreConversationToolExecutor(
        reminder_manager=None,
        calendar_manager=None,
        notes_path=None,
        memory_engine=None,
        session_manager=None,
        spotify_manager=None,
        smart_home_executor=None,
        get_memory_db_path=lambda: None,
        get_time_context_fn=lambda: {},
        get_personality=lambda: None,
    )

    result = await executor.execute(
        ConversationToolRequest("spotify_get_status")
    )

    assert result.ok is False
    assert "unavailable" in result.result.lower()


async def test_notes_get_returns_file_content(tmp_path):
    notes_file = tmp_path / "notes.md"
    notes_file.write_text("kupić mleko\nprzeczytać książkę", encoding="utf-8")

    executor = CoreConversationToolExecutor(
        reminder_manager=None,
        calendar_manager=None,
        notes_path=notes_file,
        memory_engine=None,
        session_manager=None,
        spotify_manager=None,
        smart_home_executor=None,
        get_memory_db_path=lambda: None,
        get_time_context_fn=lambda: {},
        get_personality=lambda: None,
    )

    result = await executor.execute(ConversationToolRequest("notes_get"))
    assert result.ok is True
    assert "kupić mleko" in result.result


async def test_session_manager_stream_channel_returns_turns(tmp_path):
    from backend.core.session_manager import SessionManager
    sm = SessionManager(tmp_path, stream_channel="telegram")
    sm.log_chat("User", "Cześć Monika!")
    sm.log_chat("Monika", "Hej! Jak się masz?")

    turns = sm.get_current_session_turns(limit=10)
    assert len(turns) == 2
    assert turns[0]["sender"] == "User"
    assert turns[0]["text"] == "Cześć Monika!"
    assert turns[1]["sender"] == "Monika"
    assert turns[1]["text"] == "Hej! Jak się masz?"
    assert sm.get_current_session_id().startswith("stream_telegram")


async def test_memory_adapter_update_and_delete(tmp_path):
    from backend.services.memory_adapter import MemoryEngine
    from backend.soul.db import init_db

    db_file = tmp_path / "monika.db"
    await init_db(db_file)

    engine = MemoryEngine(base_dir=tmp_path)
    entry_id, status = engine.add_entry(type="semantic", content="Lubi kawę bez cukru")
    assert status == "ok"
    assert entry_id.startswith("mem_")

    recent = engine.list_recent(limit=5)
    assert len(recent) == 1
    assert recent[0]["content"] == "Lubi kawę bez cukru"

    # Test update
    up_status = engine.update_entry(entry_id, {"content": "Lubi kawę z mlekiem owsianym"})
    assert up_status == "ok"
    recent = engine.list_recent(limit=5)
    assert recent[0]["content"] == "Lubi kawę z mlekiem owsianym"

    # Test delete via status archived
    arch_status = engine.update_entry(entry_id, {"status": "archived"})
    assert arch_status == "ok"
    recent = engine.list_recent(limit=5)
    assert len(recent) == 0


async def test_memory_search_executor(tmp_path):
    from backend.soul.db import init_db
    from backend.soul.memory import store as memory_store
    from backend.soul.models import MemoryEntry

    db_file = tmp_path / "monika.db"
    await init_db(db_file)

    await memory_store.add(
        MemoryEntry(
            id="mem_1",
            type="semantic",
            content="Ulubiony kolor to butelkowa zieleń",
            importance=5.0,
        ),
        db_path=db_file,
    )

    executor = CoreConversationToolExecutor(
        reminder_manager=None,
        calendar_manager=None,
        notes_path=None,
        memory_engine=None,
        session_manager=None,
        spotify_manager=None,
        smart_home_executor=None,
        get_memory_db_path=lambda: db_file,
        get_time_context_fn=lambda: {},
        get_personality=lambda: None,
    )

    result = await executor.execute(
        ConversationToolRequest("memory_search", {"query": "kolor"})
    )
    assert result.ok is True
    assert "butelkowa zieleń" in result.result



async def test_named_scene_command_executes_without_model_planning():
    executed = []

    class FakeThinker:
        async def plan_tool_calls(self, text, *, tools, runtime_context):
            raise AssertionError("named scenes must not wait for model planning")

        async def prepare_spoken_reply(self, text, *, turn_evidence=None):
            assert "status=success" in turn_evidence
            return "Włączyłam tryb relaksu."

    class FakeExecutor:
        async def execute(self, request):
            executed.append(request)
            return ConversationToolResult(request.name, "Activated scene: Relaks")

    loop = AudioLoop.__new__(AudioLoop)
    loop.permissions = {"control_light": False}
    loop.thinker = FakeThinker()
    loop._conversation_tool_executor = FakeExecutor()
    loop._last_tool_trace = {}

    outcome = await loop.author_tool_turn("tryb relaksu poprosze")

    assert outcome.handled is True
    assert outcome.reply == "Włączyłam tryb relaksu."
    assert executed == [
        ConversationToolRequest(
            "control_light",
            {"target": "relaks", "action": "turn_on"},
        )
    ]


