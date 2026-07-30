from types import SimpleNamespace

from backend.core.handlers.chat_input_handlers import register_chat_input_handlers


class FakeSio:
    def __init__(self):
        self.handlers = {}
        self.emitted = []

    def event(self, function):
        self.handlers[function.__name__] = function
        return function

    async def emit(self, event, payload, room=None):
        self.emitted.append((event, payload, room))


def _register(loop):
    sio = FakeSio()
    register_chat_input_handlers(
        sio,
        get_audio_loop=lambda: loop,
        emit_to_frontend=lambda *args, **kwargs: None,
        audio_loop_mark_user_activity=lambda target, text: None,
        get_vn_user_buf=lambda: "",
        set_vn_user_buf=lambda value: None,
        set_vn_user_last_ts=lambda value: None,
        get_vn_scene_task=lambda: None,
        set_vn_scene_task=lambda value: None,
        create_debounced_vn_scene_task=lambda: None,
        is_private_web_task_request=lambda text: False,
        study_reader=SimpleNamespace(),
        screen_ocr_runtime=None,
    )
    return sio


async def test_drafts_are_not_delivered_until_one_candidate_is_selected():
    delivered = []
    logged = []

    class FakeThinker:
        last_trace = {"context": {"user_prompt_sha256": "same-context"}}

        async def prepare_reply_candidates(
            self,
            text,
            *,
            count,
            timeout_sec,
            on_progress,
        ):
            assert count == 3
            await on_progress({"stage": "context_ready"})
            return ("Wariant pierwszy.", "Wariant drugi.", "Wariant trzeci.")

        def mark_voice_delivered(self):
            pass

    async def deliver(reply, *, speak):
        delivered.append((reply, speak))
        return True

    loop = SimpleNamespace(
        session=object(),
        thinker=FakeThinker(),
        session_manager=SimpleNamespace(
            log_chat=lambda sender, text: logged.append((sender, text))
        ),
        _dedicated_speech_enabled=lambda: True,
        deliver_authored_reply=deliver,
    )
    sio = _register(loop)

    draft = await sio.handlers["conversation_draft_turn"](
        "client-1",
        {"text": "Rano od razu jestem skupiony.", "count": 3},
    )

    assert draft["ok"] is True
    assert len(draft["candidates"]) == 3
    assert delivered == []
    assert logged == [("User", "Rano od razu jestem skupiony.")]

    selected = await sio.handlers["conversation_draft_select"](
        "client-1",
        {
            "response_set_id": draft["response_set_id"],
            "index": 1,
            "speak": True,
        },
    )
    repeated = await sio.handlers["conversation_draft_select"](
        "client-1",
        {
            "response_set_id": draft["response_set_id"],
            "index": 0,
        },
    )

    assert selected["ok"] is True
    assert delivered == [("Wariant drugi.", True)]
    assert repeated["ok"] is False
