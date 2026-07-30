"""Socket API for lorebook import, World Stack selection, and diagnostics."""

from __future__ import annotations

from pathlib import Path

from backend.soul.lorebook import (
    WorldStack,
    export_lorebook,
    import_lorebook,
    list_activation_diagnostics,
    LoreReviewService,
)
from backend.soul.lorebook import store


def register_lorebook_handlers(
    sio,
    *,
    get_audio_loop,
    db_path: Path,
):
    def _conversation_id() -> str:
        loop = get_audio_loop()
        manager = getattr(loop, "session_manager", None) if loop else None
        if manager is not None:
            value = str(manager.get_current_session_id() or "").strip()
            if value:
                return value
        return "conversation"

    async def _state() -> dict:
        conversation_id = _conversation_id()
        books = await store.list_lorebooks(db_path=db_path)
        entries = await store.list_entries(
            [book.id for book in books],
            enabled_only=False,
            db_path=db_path,
        )
        counts: dict[str, int] = {}
        for entry in entries:
            counts[entry.lorebook_id] = counts.get(entry.lorebook_id, 0) + 1
        stack = await store.get_world_stack(conversation_id, db_path)
        diagnostics = await list_activation_diagnostics(
            conversation_id,
            limit=50,
            db_path=db_path,
        )
        candidates = await store.list_lore_candidates(
            status="pending",
            limit=100,
            db_path=db_path,
        )
        return {
            "conversation_id": conversation_id,
            "lorebooks": [
                {
                    **book.model_dump(mode="json"),
                    "entry_count": counts.get(book.id, 0),
                }
                for book in books
            ],
            "world_stack": stack.model_dump(mode="json"),
            "diagnostics": diagnostics,
            "candidates": [
                candidate.model_dump(mode="json")
                for candidate in candidates
            ],
        }

    @sio.event
    async def lore_state_get(sid, data=None):
        try:
            payload = await _state()
            await sio.emit("lore_state", payload, room=sid)
            return payload
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
            await sio.emit("lore_error", result, room=sid)
            return result

    @sio.event
    async def lore_world_stack_set(sid, data=None):
        try:
            data = data or {}
            books = await store.list_lorebooks(
                enabled_only=True,
                db_path=db_path,
            )
            known_ids = {book.id for book in books}
            requested_ids = list(
                dict.fromkeys(
                    str(value).strip()
                    for value in (data.get("lorebook_ids") or [])
                    if str(value).strip()
                )
            )
            unknown = [value for value in requested_ids if value not in known_ids]
            if unknown:
                raise ValueError(
                    "Unknown or disabled lorebooks: " + ", ".join(unknown)
                )
            pins = [
                str(value).strip()
                for value in (data.get("pinned_entries") or [])
                if str(value).strip().split(":", 1)[0] in requested_ids
            ]
            raw_budget = data.get("token_budget")
            token_budget = (
                None
                if raw_budget in {None, ""}
                else max(100, min(12000, int(raw_budget)))
            )
            stack = WorldStack(
                conversation_id=_conversation_id(),
                reality_mode=str(data.get("reality_mode") or "grounded"),
                lorebook_ids=requested_ids,
                pinned_entries=pins,
                token_budget=token_budget,
            )
            await store.set_world_stack(stack, db_path)
            payload = await _state()
            await sio.emit("lore_state", payload, room=sid)
            return {"ok": True, **payload}
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
            await sio.emit("lore_error", result, room=sid)
            return result

    @sio.event
    async def lore_import(sid, data=None):
        try:
            data = data or {}
            content = data.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Import content is empty.")
            filename = Path(str(data.get("file_name") or "lorebook.json")).name
            hint = str(data.get("format_hint") or Path(filename).suffix)
            bundle = await import_lorebook(
                content,
                format_hint=hint,
                book_id=data.get("book_id"),
                name=data.get("name"),
                kind=data.get("kind"),
                trusted=False,
                db_path=db_path,
            )
            payload = {
                "ok": True,
                "book_id": bundle.lorebook.id,
                "entry_count": len(bundle.entries),
                "warnings": bundle.warnings,
                "state": await _state(),
            }
            await sio.emit("lore_imported", payload, room=sid)
            await sio.emit("lore_state", payload["state"], room=sid)
            return payload
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
            await sio.emit("lore_error", result, room=sid)
            return result

    @sio.event
    async def lore_export(sid, data=None):
        try:
            data = data or {}
            book_id = str(data.get("book_id") or "").strip()
            selected_format = str(data.get("format") or "json").casefold()
            if not book_id:
                raise ValueError("Lorebook ID is required.")
            content = await export_lorebook(
                book_id,
                format=selected_format,
                db_path=db_path,
            )
            extension = "md" if selected_format in {"md", "markdown"} else (
                "yaml" if selected_format in {"yaml", "yml"} else "json"
            )
            return {
                "ok": True,
                "filename": f"{book_id}.{extension}",
                "content": content,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @sio.event
    async def lore_diagnostics_get(sid, data=None):
        try:
            data = data or {}
            items = await list_activation_diagnostics(
                _conversation_id(),
                turn_id=data.get("turn_id"),
                limit=max(1, min(200, int(data.get("limit", 50)))),
                db_path=db_path,
            )
            payload = {"items": items}
            await sio.emit("lore_diagnostics", payload, room=sid)
            return {"ok": True, **payload}
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
            await sio.emit("lore_error", result, room=sid)
            return result

    @sio.event
    async def lore_candidate_review(sid, data=None):
        try:
            data = data or {}
            candidate_id = str(data.get("candidate_id") or "").strip()
            if not candidate_id:
                raise ValueError("Candidate ID is required.")
            reviewed = await LoreReviewService(db_path=db_path).review(
                candidate_id,
                accept=bool(data.get("accept")),
                edits=data.get("edits") if isinstance(data.get("edits"), dict) else None,
                supersedes_uid=(
                    str(data.get("supersedes_uid") or "").strip() or None
                ),
                keep_conflicts=bool(data.get("keep_conflicts", False)),
            )
            payload = {
                "ok": True,
                "candidate": reviewed.model_dump(mode="json"),
                "state": await _state(),
            }
            await sio.emit("lore_candidate_reviewed", payload, room=sid)
            await sio.emit("lore_state", payload["state"], room=sid)
            return payload
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
            await sio.emit("lore_error", result, room=sid)
            return result
