"""Import and export adapters for Monika and common lorebook formats."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from . import store
from .models import LoreEntry, Lorebook

LoreFormat = Literal["json", "yaml", "markdown", "sillytavern"]
MAX_IMPORT_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class LoreImportBundle:
    lorebook: Lorebook
    entries: list[LoreEntry]
    source_format: str
    warnings: list[str] = field(default_factory=list)


def _slug(value: object, fallback: str) -> str:
    text = unicodedata.normalize(
        "NFKD",
        "" if value is None else str(value),
    )
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-_").lower()
    return text[:80] or fallback


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        values = re.split(r"[,;\n]", value)
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        return []
    return list(
        dict.fromkeys(
            text
            for item in values
            if (text := str(item or "").strip())
        )
    )


def _integer(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_text_payload(text: str, format_hint: str | None) -> tuple[Any, str]:
    hint = str(format_hint or "").strip().casefold().lstrip(".")
    if hint in {"md", "markdown"}:
        return _parse_markdown(text), "markdown"
    if hint in {"yaml", "yml"}:
        return yaml.safe_load(text), "yaml"
    if hint in {"json", "sillytavern", "world_info", "character_book"}:
        return json.loads(text), "sillytavern" if hint != "json" else "json"

    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(text), "json"
    if stripped.startswith("---") or re.search(r"(?m)^entries\s*:", text):
        return yaml.safe_load(text), "yaml"
    return _parse_markdown(text), "markdown"


def _parse_markdown(text: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    body = text
    if text.lstrip().startswith("---"):
        match = re.match(r"\s*---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.S)
        if match:
            loaded = yaml.safe_load(match.group(1)) or {}
            if not isinstance(loaded, dict):
                raise ValueError("Markdown front matter must be an object.")
            metadata = loaded
            body = text[match.end() :]

    headings = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", body))
    entries = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        section = body[heading.end() : end].strip()
        entry_meta: dict[str, Any] = {}
        marker = re.match(r"\s*<!--\s*lore:\s*(\{.*?\})\s*-->\s*", section, re.S)
        if marker:
            entry_meta = json.loads(marker.group(1))
            section = section[marker.end() :].strip()
        entries.append(
            {
                **entry_meta,
                "title": heading.group(1).strip(),
                "content": section,
            }
        )
    if not entries and body.strip():
        title_match = re.match(r"\s*#\s+(.+?)\s*$", body, re.M)
        title = (
            title_match.group(1).strip()
            if title_match
            else str(metadata.get("title") or metadata.get("name") or "Imported entry")
        )
        if title_match and not metadata.get("name"):
            metadata["name"] = title
        content = body
        if title_match:
            content = (body[: title_match.start()] + body[title_match.end() :]).strip()
        entries.append({"title": title, "content": content})
    return {
        "lorebook": metadata,
        "entries": entries,
        "format": "monikai_markdown_v1",
    }


def _unwrap_payload(data: Any) -> tuple[dict, Any, str]:
    if isinstance(data, list):
        return {}, data, "generic"
    if not isinstance(data, dict):
        raise ValueError("Lorebook payload must be an object or entry list.")

    if isinstance(data.get("data"), dict) and isinstance(
        data["data"].get("character_book"), dict
    ):
        data = data["data"]["character_book"]
        return data, data.get("entries", []), "sillytavern_character_book"
    if isinstance(data.get("character_book"), dict):
        data = data["character_book"]
        return data, data.get("entries", []), "sillytavern_character_book"
    if isinstance(data.get("lorebook"), dict):
        return data["lorebook"], data.get("entries", []), str(
            data.get("format") or "monikai"
        )
    if "entries" in data:
        entries = data.get("entries")
        source = (
            "sillytavern_world_info"
            if isinstance(entries, dict)
            else str(data.get("format") or "generic")
        )
        return data, entries, source
    if data.get("content") or data.get("text"):
        return {}, [data], "generic_single_entry"
    raise ValueError("Payload does not contain lorebook entries.")


def _normalise_entries(raw_entries: Any) -> list[dict]:
    if isinstance(raw_entries, dict):
        result = []
        for key, value in raw_entries.items():
            if isinstance(value, dict):
                result.append({"_map_id": key, **value})
        return result
    if isinstance(raw_entries, list):
        return [item for item in raw_entries if isinstance(item, dict)]
    raise ValueError("Lorebook entries must be a list or object.")


def parse_lorebook(
    payload: str | bytes | dict,
    *,
    format_hint: str | None = None,
    book_id: str | None = None,
    name: str | None = None,
    kind: str | None = None,
    trusted: bool = False,
) -> LoreImportBundle:
    """Parse without persistence, suitable for previews and validation."""
    if isinstance(payload, bytes):
        if len(payload) > MAX_IMPORT_BYTES:
            raise ValueError("Lorebook import exceeds the 10 MiB limit.")
        payload = payload.decode("utf-8-sig")
    if isinstance(payload, str):
        if len(payload.encode("utf-8")) > MAX_IMPORT_BYTES:
            raise ValueError("Lorebook import exceeds the 10 MiB limit.")
        data, detected = _load_text_payload(payload, format_hint)
    else:
        data, detected = payload, str(format_hint or "object")

    metadata, raw_entries, source_format = _unwrap_payload(data)
    source_format = source_format or detected
    display_name = str(
        name
        or metadata.get("name")
        or metadata.get("title")
        or metadata.get("id")
        or "Imported lorebook"
    ).strip()
    resolved_id = _slug(
        book_id or metadata.get("id") or display_name,
        "imported-lorebook",
    )
    allowed_kinds = {"reality", "imported_fiction", "custom", "scenario"}
    payload_kind = metadata.get("kind")
    resolved_kind = (
        kind
        if kind in allowed_kinds
        else (
            payload_kind
            if source_format.startswith("monikai")
            and payload_kind in allowed_kinds
            else "imported_fiction"
        )
    )
    book = Lorebook(
        id=resolved_id,
        name=display_name,
        description=str(metadata.get("description") or "").strip(),
        kind=resolved_kind,
        # Imported payloads cannot elevate their own trust.
        trusted=bool(trusted),
        editable=True,
        enabled=not bool(metadata.get("disabled", False)),
        default_mode=(
            metadata.get("default_mode")
            if metadata.get("default_mode") in {
                "grounded", "crossover", "roleplay", "ambiguous"
            }
            else "grounded"
        ),
        token_budget=max(
            1,
            _integer(metadata.get("token_budget"), 1800),
        ),
        priority=_integer(metadata.get("priority"), 50),
        metadata={
            "import_format": source_format,
            "original_name": display_name,
        },
    )

    warnings: list[str] = []
    entries: list[LoreEntry] = []
    used_ids: set[str] = set()
    for index, raw in enumerate(_normalise_entries(raw_entries)):
        content = str(raw.get("content") or raw.get("text") or "").strip()
        if not content:
            warnings.append(f"Skipped entry {index}: empty content.")
            continue
        raw_id = raw.get("id", raw.get("uid", raw.get("_map_id", index)))
        entry_id = _slug(raw_id, f"entry-{index + 1}")
        base_id = entry_id
        suffix = 2
        while entry_id in used_ids:
            entry_id = f"{base_id}-{suffix}"
            suffix += 1
        used_ids.add(entry_id)

        keys = _strings(raw.get("keys", raw.get("key", [])))
        secondary = _strings(
            raw.get("secondary_keys", raw.get("keysecondary", []))
        )
        selective = bool(raw.get("selective", False))
        match_mode = str(raw.get("match_mode") or "")
        if match_mode not in {"any", "all", "primary_and_secondary"}:
            match_mode = (
                "primary_and_secondary"
                if selective and secondary
                else "any"
            )
        entry_type = str(raw.get("entry_type") or "knowledge")
        if entry_type not in {
            "knowledge", "scene", "dialogue_example", "behavior_instruction"
        }:
            entry_type = "knowledge"
        probability = _integer(raw.get("probability"), 100)
        if raw.get("useProbability") and 0 < probability < 100:
            warnings.append(
                f"Entry {entry_id}: probability {probability}% is not "
                "randomized; deterministic activation is used."
            )
        enabled = not bool(raw.get("disable", raw.get("disabled", False)))
        if raw.get("enabled") is not None:
            enabled = bool(raw.get("enabled"))
        if raw.get("useProbability") and probability <= 0:
            enabled = False

        title = str(
            raw.get("title")
            or raw.get("comment")
            or raw.get("name")
            or (keys[0] if keys else entry_id)
        ).strip() or entry_id
        entries.append(
            LoreEntry(
                id=entry_id,
                lorebook_id=book.id,
                title=title,
                content=content,
                entry_type=entry_type,
                keys=keys,
                secondary_keys=secondary,
                entities=_strings(raw.get("entities", [])),
                relations=_strings(raw.get("relations", [])),
                match_mode=match_mode,
                priority=_integer(
                    raw.get(
                        "priority",
                        raw.get("order", raw.get("insertion_order", 50)),
                    ),
                    50,
                ),
                constant=bool(raw.get("constant", False)),
                enabled=enabled,
                sticky_turns=max(
                    0,
                    _integer(
                        raw.get("sticky_turns", raw.get("sticky", 0)),
                        0,
                    ),
                ),
                canon_status=(
                    raw.get("canon_status")
                    if raw.get("canon_status") in {
                        "canonical", "learned", "proposed", "superseded"
                    }
                    else "canonical"
                ),
                source=source_format,
                confidence=max(
                    0.0,
                    min(1.0, _float(raw.get("confidence"), 1.0)),
                ),
            )
        )
    if not entries:
        raise ValueError("Lorebook contains no non-empty entries.")
    return LoreImportBundle(book, entries, source_format, warnings)


async def import_lorebook(
    payload: str | bytes | dict,
    *,
    format_hint: str | None = None,
    book_id: str | None = None,
    name: str | None = None,
    kind: str | None = None,
    trusted: bool = False,
    db_path: Path | None = None,
) -> LoreImportBundle:
    bundle = parse_lorebook(
        payload,
        format_hint=format_hint,
        book_id=book_id,
        name=name,
        kind=kind,
        trusted=trusted,
    )
    await store.upsert_lorebook(bundle.lorebook, db_path)
    await store.upsert_entries(bundle.entries, db_path)
    return bundle


async def import_lorebook_file(
    path: Path,
    *,
    book_id: str | None = None,
    name: str | None = None,
    kind: str | None = None,
    trusted: bool = False,
    db_path: Path | None = None,
) -> LoreImportBundle:
    source = Path(path)
    size = source.stat().st_size
    if size > MAX_IMPORT_BYTES:
        raise ValueError("Lorebook import exceeds the 10 MiB limit.")
    return await import_lorebook(
        source.read_bytes(),
        format_hint=source.suffix,
        book_id=book_id,
        name=name,
        kind=kind,
        trusted=trusted,
        db_path=db_path,
    )


def _export_payload(book: Lorebook, entries: list[LoreEntry]) -> dict:
    book_data = book.model_dump(mode="json")
    entry_data = [entry.model_dump(mode="json") for entry in entries]
    return {
        "format": "monikai_lorebook_v1",
        "lorebook": book_data,
        "entries": entry_data,
    }


async def export_lorebook(
    book_id: str,
    *,
    format: str = "json",
    db_path: Path | None = None,
) -> str:
    book = await store.get_lorebook(book_id, db_path)
    if book is None:
        raise ValueError(f"Lorebook '{book_id}' does not exist.")
    entries = await store.list_entries(
        [book_id],
        enabled_only=False,
        db_path=db_path,
    )
    payload = _export_payload(book, entries)
    selected = str(format).strip().casefold().lstrip(".")
    if selected == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2)
    if selected in {"yaml", "yml"}:
        return yaml.safe_dump(
            payload,
            allow_unicode=True,
            sort_keys=False,
        )
    if selected not in {"markdown", "md"}:
        raise ValueError("Export format must be json, yaml, or markdown.")

    book_meta = payload["lorebook"]
    front_matter = yaml.safe_dump(
        book_meta,
        allow_unicode=True,
        sort_keys=False,
    ).strip()
    sections = [f"---\n{front_matter}\n---"]
    for entry in payload["entries"]:
        metadata = {
            key: value
            for key, value in entry.items()
            if key not in {"title", "content", "lorebook_id", "created_at", "updated_at"}
        }
        marker = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        sections.append(
            f"## {entry['title']}\n\n"
            f"<!-- lore: {marker} -->\n\n"
            f"{entry['content']}"
        )
    return "\n\n".join(sections) + "\n"
