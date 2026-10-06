"""Regression tests for the native text/button/voice approval contract."""

from __future__ import annotations

import sys
from pathlib import Path


ODY_ROOT = Path(__file__).resolve().parents[2] / "backend" / "odysseus"
if str(ODY_ROOT) not in sys.path:
    sys.path.insert(0, str(ODY_ROOT))

from src.tool_approvals import (  # noqa: E402
    PendingToolApproval,
)


def test_classifier_response_parsing_is_closed_vocabulary():
    from routes.chat_routes import _parse_tool_approval_classifier_response as parse

    assert parse('{"decision":"approve_task"}') == "approve_task"
    assert parse('```json\n{"decision":"deny"}\n```') == "deny"
    assert parse("approve_session") == "approve_session"
    assert parse('{"decision":"do anything"}') is None


def test_public_payload_prioritizes_summary_and_hides_raw_args_behind_metadata():
    pending = PendingToolApproval(
        approval_id="approval-1",
        owner="bartosz",
        session_id="session-1",
        origin_run_id="run-1",
        tool_name="manage_tasks",
        content=(
            '{"action":"create","name":"Opera GX reward reminder",'
            '"prompt":"collect rewards from Opera GX","schedule":"daily",'
            '"scheduled_time":"14:30"}'
        ),
        workspace="",
        document_id="",
        document_version=None,
        document_digest="",
        external_untrusted_context_seen=True,
        effects=("write_private",),
        result_integrity="system",
        digest="0123456789abcdef0123456789abcdef",
        created_at=100.0,
        expires_at=700.0,
    )

    payload = pending.public_payload()

    assert payload["kind"] == "tool_approval"
    from src.approval_text import t

    assert payload["title"] == t("card.title")
    assert "Opera GX reward reminder" in payload["summary"]
    assert "14:30" in payload["summary"]
    assert payload["action"]["content"].startswith('{"action":"create"')
    assert "Opera GX reward reminder" in payload["voice_prompt"]
    assert "dla tej rozmowy" not in payload["voice_prompt"]
    assert payload["options"][0]["value"] == "approve_task"
    assert payload["options"][1]["value"] == "approve"
    assert payload["options"][2]["value"] == "deny"


def test_web_fetch_allowed_after_external_untrusted_context():
    from src.tool_capabilities import ToolRunSecurityContext

    context = ToolRunSecurityContext()
    context.observe_tool_result(
        "web_search",
        {"results": "pogoda krakow jutro 17:00", "success": True},
        content="pogoda krakow jutro",
    )
    assert context.external_untrusted_context_seen is True

    decision = context.decision_for(
        "web_fetch",
        '{"url": "https://weather.example.com/krakow"}',
    )
    assert decision.allowed is True
    assert decision.reason is None


def test_home_assistant_still_blocked_after_web_fetch_taint():
    from src.tool_capabilities import ToolRunSecurityContext

    context = ToolRunSecurityContext()
    context.observe_tool_result(
        "web_fetch",
        {"content": "forecast data with prompt injection", "success": True},
        content="https://weather.example.com/krakow",
    )
    assert context.external_untrusted_context_seen is True

    decision = context.decision_for(
        "home_assistant_control",
        '{"action": "turn_off", "target": "all lights"}',
    )
    assert decision.allowed is False
    assert "external_side_effect" in decision.reason


def test_tool_approval_store_peek_latest_for_owner():
    from src.tool_approvals import ToolApprovalStore
    from src.tool_capabilities import capabilities_for_tool

    store = ToolApprovalStore()
    p1 = store.create(
        owner="bartosz",
        session_id="voice_1",
        origin_run_id="run_1",
        tool_name="home_assistant_control",
        content='{"action": "turn_off"}',
        workspace="",
        external_untrusted_context_seen=True,
        capabilities=capabilities_for_tool("home_assistant_control"),
    )
    assert store.peek_latest_for_owner(owner="bartosz") == p1
    assert store.peek_latest_for_owner(owner="other_user") is None


def test_live_voice_rotated_session_fallback_lookup():
    from src.tool_approvals import ToolApprovalStore
    from src.tool_capabilities import capabilities_for_tool

    store = ToolApprovalStore()
    original_approval = store.create(
        owner="bartosz",
        session_id="voice_original_session",
        origin_run_id="run_1",
        tool_name="home_assistant_control",
        content='{"action": "turn_off"}',
        workspace="",
        external_untrusted_context_seen=True,
        capabilities=capabilities_for_tool("home_assistant_control"),
    )

    rotated_session = "voice_rotated_session"
    assert store.peek_for_session(owner="bartosz", session_id=rotated_session) is None

    fallback = store.peek_latest_for_owner(owner="bartosz")
    assert fallback is not None
    assert fallback.approval_id == original_approval.approval_id
    assert fallback.session_id == "voice_original_session"




def test_first_party_context_and_notes_do_not_arm_the_gate_but_web_does():
    from src.prompt_security import untrusted_context_message
    from src.tool_capabilities import (
        ToolRunSecurityContext,
        messages_contain_external_untrusted_context as tainted,
    )

    memory = untrusted_context_message("saved memory: pinned context", "x")
    web = untrusted_context_message("web search results", "x", arm_tool_gate=True)
    assert not tainted([memory])
    assert tainted([memory, web])

    run = ToolRunSecurityContext()
    note = '{"action":"list"}'
    run.observe_tool_result("manage_notes", {"output": "- [1] **a**", "exit_code": 0}, note)
    assert run.decision_for("manage_notes", '{"action":"add","title":"t"}').allowed
    run.observe_tool_result("web_search", {"output": "page", "exit_code": 0})
    assert not run.decision_for("manage_notes", '{"action":"add","title":"t"}').allowed
