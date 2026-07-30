"""Conservative proposal and review pipeline for learned lore."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from uuid import uuid4

from backend.conversation.providers import TextGenerationRequest, TextModelProvider

from . import store
from .models import LoreCandidate, LoreEntry, Lorebook, WorldStack

LEARNING_INSTRUCTION = (
    "Jesteś konserwatywnym ekstraktorem wiedzy, nie autorem rozmowy. "
    "Analizuj wyłącznie jawne twierdzenia użytkownika. Odpowiedź asystenta "
    "jest tylko kontekstem i nigdy nie stanowi źródła faktu. Nie wnioskuj cech "
    "osobowości, emocji, diagnoz ani ukrytych preferencji. Pomijaj small talk, "
    "niepewność, żarty bez jasnego faktu oraz informacje jednorazowe. "
    "Zwróć wyłącznie tablicę JSON. Każdy element: target_type "
    "(personal_memory, world_lore lub fiction_lore), target_lorebook_id "
    "(null dla personal_memory, reality dla realnego świata, dokładne ID "
    "aktywnego fikcyjnego świata), title, content, keys, entities, confidence "
    "0..1 i rationale. Jeśli nic nie zasługuje na propozycję, zwróć []. "
    "Nie twórz więcej niż 3 propozycje."
)

_UNCERTAIN_RE = re.compile(
    r"\b(nie wiem|chyba|może|moze|wydaje mi się|wydaje mi sie|"
    r"i don't know|maybe|perhaps|i guess)\b",
    re.IGNORECASE,
)


def _slug(value: str, fallback: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-_").lower()
    return text[:64] or fallback


def _clean_strings(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(
        dict.fromkeys(
            text
            for item in value
            if (text := str(item or "").strip())
        )
    )[:12]


def _parse_json_array(raw: str) -> list[dict]:
    text = str(raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.I | re.S)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("["):
        match = re.search(r"\[.*\]", text, re.S)
        text = match.group(0) if match else "[]"
    data = json.loads(text)
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _conflicts(candidate: LoreCandidate, entries: list[LoreEntry]) -> list[str]:
    title = candidate.title.casefold().strip()
    keys = {item.casefold().strip() for item in candidate.keys + candidate.entities}
    result = []
    for entry in entries:
        same_subject = entry.title.casefold().strip() == title
        existing_keys = {
            item.casefold().strip()
            for item in entry.keys + entry.entities
        }
        if not same_subject and not (keys and keys & existing_keys):
            continue
        if entry.content.casefold().strip() != candidate.content.casefold().strip():
            result.append(entry.uid)
    return result


class LoreLearningEngine:
    def __init__(
        self,
        *,
        provider: TextModelProvider,
        model: str,
        db_path: Path | None = None,
        minimum_confidence: float = 0.7,
    ):
        self._provider = provider
        self._model = model
        self._db_path = db_path
        self._minimum_confidence = max(0.0, min(1.0, minimum_confidence))

    async def propose_from_turn(
        self,
        *,
        conversation_id: str,
        user_text: str,
        assistant_reply: str,
        turn_id: str | None = None,
        world_stack: WorldStack | None = None,
    ) -> list[LoreCandidate]:
        user_text = re.sub(r"\s+", " ", str(user_text or "")).strip()
        if len(user_text) < 18 or user_text.endswith("?"):
            return []
        if _UNCERTAIN_RE.search(user_text):
            return []

        stack = world_stack or await store.get_world_stack(
            conversation_id,
            self._db_path,
        )
        books = await store.list_lorebooks(
            enabled_only=True,
            db_path=self._db_path,
        )
        active_books = [book for book in books if book.id in stack.lorebook_ids]
        active_description = [
            {"id": book.id, "kind": book.kind, "name": book.name}
            for book in active_books
        ]
        prompt = json.dumps(
            {
                "active_worlds": active_description,
                "reality_mode": stack.reality_mode,
                "user_statement": user_text,
                "assistant_reply_for_context_only": str(assistant_reply or "")[:900],
            },
            ensure_ascii=False,
        )
        raw = await self._provider.generate(
            TextGenerationRequest(
                model=self._model,
                system_instruction=LEARNING_INSTRUCTION,
                prompt=prompt,
                thinking_budget=0,
            )
        )
        allowed_fiction = {
            book.id
            for book in active_books
            if book.kind in {"imported_fiction", "scenario", "custom"}
        }
        candidates: list[LoreCandidate] = []
        for item in _parse_json_array(raw)[:3]:
            target_type = str(item.get("target_type") or "")
            if target_type not in {
                "personal_memory", "world_lore", "fiction_lore"
            }:
                continue
            confidence = max(
                0.0,
                min(1.0, float(item.get("confidence", 0.0) or 0.0)),
            )
            if confidence < self._minimum_confidence:
                continue
            target_book = str(item.get("target_lorebook_id") or "").strip() or None
            if target_type == "personal_memory":
                target_book = None
            elif target_type == "world_lore":
                target_book = "reality"
            elif target_book not in allowed_fiction:
                continue
            content = re.sub(r"\s+", " ", str(item.get("content") or "")).strip()
            title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
            if not title or not content:
                continue
            candidate = LoreCandidate(
                conversation_id=conversation_id,
                target_type=target_type,
                target_lorebook_id=target_book,
                title=title[:160],
                content=content[:1200],
                keys=_clean_strings(item.get("keys")),
                entities=_clean_strings(item.get("entities")),
                confidence=confidence,
                rationale=str(item.get("rationale") or "").strip()[:500],
                source_turn_id=turn_id,
                source_excerpt=user_text[:600],
            )
            if target_book:
                existing = await store.list_entries(
                    [target_book],
                    enabled_only=True,
                    db_path=self._db_path,
                )
                candidate = candidate.model_copy(
                    update={"conflicts_with": _conflicts(candidate, existing)}
                )
            persisted = await store.add_lore_candidate(
                candidate,
                self._db_path,
            )
            candidates.append(persisted)
        return candidates


class LoreReviewService:
    def __init__(self, *, db_path: Path | None = None):
        self._db_path = db_path

    async def review(
        self,
        candidate_id: str,
        *,
        accept: bool,
        edits: dict | None = None,
        supersedes_uid: str | None = None,
        keep_conflicts: bool = False,
    ) -> LoreCandidate:
        candidate = await store.get_lore_candidate(
            candidate_id,
            self._db_path,
        )
        if candidate is None:
            raise ValueError("Lore candidate does not exist.")
        if candidate.status != "pending":
            return candidate
        if not accept:
            await store.set_lore_candidate_review(
                candidate.id,
                status="rejected",
                db_path=self._db_path,
            )
            return (await store.get_lore_candidate(candidate.id, self._db_path))

        edits = edits or {}
        title = str(edits.get("title") or candidate.title).strip()
        content = str(edits.get("content") or candidate.content).strip()
        keys = _clean_strings(edits.get("keys", candidate.keys))
        entities = _clean_strings(edits.get("entities", candidate.entities))
        if not title or not content:
            raise ValueError("Accepted candidate requires title and content.")
        if candidate.conflicts_with:
            if supersedes_uid and supersedes_uid not in candidate.conflicts_with:
                raise ValueError("Superseded entry is not a detected conflict.")
            if not supersedes_uid and not keep_conflicts:
                raise ValueError(
                    "Resolve detected conflicts before accepting the candidate."
                )

        if candidate.target_type == "personal_memory":
            from backend.soul.memory import store as memory_store
            from backend.soul.models import MemoryEntry

            entry_id, _ = await memory_store.add(
                MemoryEntry(
                    id=str(uuid4()),
                    type="semantic",
                    content=content,
                    importance=5.0,
                    perspective="factual",
                    tags=["learned", *keys],
                    entities=entities,
                    source_session=candidate.conversation_id,
                ),
                db_path=self._db_path,
            )
            accepted_uid = f"memory:{entry_id}"
        else:
            book_id = str(
                edits.get("target_lorebook_id")
                or candidate.target_lorebook_id
                or ""
            ).strip()
            if candidate.target_type == "world_lore":
                book_id = book_id or "reality"
                book = await store.get_lorebook(book_id, self._db_path)
                if book is None:
                    await store.upsert_lorebook(
                        Lorebook(
                            id=book_id,
                            name="Rzeczywistość",
                            kind="reality",
                            trusted=True,
                        ),
                        self._db_path,
                    )
            else:
                book = await store.get_lorebook(book_id, self._db_path)
                if book is None or book.kind not in {
                    "imported_fiction", "scenario", "custom"
                }:
                    raise ValueError("Target fictional lorebook is unavailable.")

            entry_id = _slug(
                title,
                f"learned-{candidate.id[:8]}",
            )
            if await store.get_entry(book_id, entry_id, self._db_path):
                entry_id = f"{entry_id}-{candidate.id[:8]}"
            entry = LoreEntry(
                id=entry_id,
                lorebook_id=book_id,
                title=title,
                content=content,
                keys=keys,
                entities=entities,
                canon_status="learned",
                source=(
                    f"conversation:{candidate.conversation_id}:"
                    f"{candidate.source_turn_id or 'turn'}"
                ),
                confidence=candidate.confidence,
            )
            await store.upsert_entry(entry, self._db_path)
            accepted_uid = entry.uid
            if supersedes_uid:
                await store.supersede_entry(
                    supersedes_uid,
                    self._db_path,
                )

        changed = await store.set_lore_candidate_review(
            candidate.id,
            status="accepted",
            accepted_entry_uid=accepted_uid,
            db_path=self._db_path,
        )
        if not changed:
            raise RuntimeError("Candidate was reviewed concurrently.")
        return (await store.get_lore_candidate(candidate.id, self._db_path))
