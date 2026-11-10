import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "odysseus"))

from src.agent_loop import _history_has_truncated_document  # noqa: E402

NOTE = "[…truncated for inline context — full 142,870 chars saved as document `x`. Use `manage_documents` with action=read]"


def test_truncated_attachment_in_history_keeps_document_tool_reachable():
    history = [
        {"role": "user", "content": "Czy jest załączona?\n" + NOTE},
        {"role": "assistant", "content": "Tak."},
        {"role": "user", "content": "Na pewno nie widzisz całości?"},
    ]
    assert _history_has_truncated_document(history)
    assert not _history_has_truncated_document(history[1:])
    assert not _history_has_truncated_document([{"role": "assistant", "content": NOTE}])


def test_paging_an_attached_document_is_allowed_after_untrusted_context():
    from src.tool_capabilities import ToolRunSecurityContext

    doc = "73928871-4486-4195-a332-807f3c412379"
    note = f"[…truncated for inline context — full 142,870 chars saved as document `{doc}`. Use `manage_documents`]"
    ctx = ToolRunSecurityContext(external_untrusted_context_seen=True)
    ctx.observe_messages([{"role": "user", "content": "tekst\n" + note}])

    read = lambda d: f'{{"action": "read", "document_id": "{d}", "offset": 15000}}'
    assert ctx.decision_for("manage_documents", read(doc)).allowed
    assert not ctx.decision_for("manage_documents", read("11111111-1111-1111-1111-111111111111")).allowed
    assert not ctx.decision_for("manage_documents", f'{{"action": "delete", "document_id": "{doc}"}}').allowed


def test_manage_documents_schema_exposes_read_and_offset():
    from src.tool_schemas import FUNCTION_TOOL_SCHEMAS

    schema = next(t["function"] for t in FUNCTION_TOOL_SCHEMAS if t["function"]["name"] == "manage_documents")
    assert "read" in schema["parameters"]["properties"]["action"]["enum"]
    assert "offset" in schema["parameters"]["properties"]
