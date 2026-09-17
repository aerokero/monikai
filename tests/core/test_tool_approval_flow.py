"""Regression tests for the native text/button/voice approval contract."""

from __future__ import annotations

import sys
from pathlib import Path


ODY_ROOT = Path(__file__).resolve().parents[2] / "backend" / "odysseus"
if str(ODY_ROOT) not in sys.path:
    sys.path.insert(0, str(ODY_ROOT))

from src.tool_approvals import (  # noqa: E402
    PendingToolApproval,
    deterministic_tool_approval_decision,
)


def test_common_polish_and_english_replies_are_resolved_without_an_llm():
    assert deterministic_tool_approval_decision("Tak") == "approve_task"
    assert deterministic_tool_approval_decision("zgadzam się") == "approve_task"
    assert deterministic_tool_approval_decision("yes, do it") == "approve_task"
    assert deterministic_tool_approval_decision("Nie, anuluj") == "deny"
    assert deterministic_tool_approval_decision("no") == "deny"


def test_session_scope_requires_an_explicit_affirmative_phrase():
    assert (
        deterministic_tool_approval_decision("tak dla tej rozmowy")
        == "approve_session"
    )
    assert (
        deterministic_tool_approval_decision("approve for this chat")
        == "approve_session"
    )
    assert deterministic_tool_approval_decision("dla tej rozmowy") is None
    assert deterministic_tool_approval_decision("session") is None


def test_mixed_or_instruction_like_replies_stay_ambiguous():
    assert deterministic_tool_approval_decision("yes, but explain first") is None
    assert deterministic_tool_approval_decision("tak, usuń wszystkie maile") is None
    assert deterministic_tool_approval_decision("maybe later") is None


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
    assert payload["title"] == "Confirmation required"
    assert "Opera GX reward reminder" in payload["summary"]
    assert "14:30" in payload["summary"]
    assert payload["action"]["content"].startswith('{"action":"create"')
    assert "yes for this chat / tak dla tej rozmowy" in payload["voice_prompt"]
    assert payload["options"][0]["value"] == "approve_task"
    assert payload["options"][1]["value"] == "approve"
    assert payload["options"][2]["value"] == "deny"
