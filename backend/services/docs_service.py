"""Workspace Documents Service — Versioned markdown docs with AI Diff generation."""

from __future__ import annotations

import difflib
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.models.model_router import LLMMessage, get_model_router

logger = logging.getLogger(__name__)


@dataclass
class DocumentRevision:
    revision_id: int
    content: str
    timestamp: str
    author: str = "user"  # "user" or "monika_ai"
    commit_message: str = ""


@dataclass
class DocumentDiff:
    original_content: str
    proposed_content: str
    unified_diff: str
    additions: int
    deletions: int
    explanation: str = ""


@dataclass
class WorkspaceDocument:
    id: str
    title: str
    filename: str
    content: str
    created_at: str
    updated_at: str
    revisions: List[DocumentRevision] = field(default_factory=list)
    pending_diff: Optional[DocumentDiff] = None


class DocsService:
    """Manages workspace documents with AI-assisted collaborative editing and diffs."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = (data_dir or Path("data")).resolve()
        self.docs_dir = self.data_dir / "documents"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.meta_file = self.docs_dir / "_docs_metadata.json"
        self._documents: Dict[str, WorkspaceDocument] = {}
        self._load_documents()

    def _load_documents(self) -> None:
        if not self.meta_file.exists():
            return
        try:
            raw = json.loads(self.meta_file.read_text(encoding="utf-8"))
            for doc_id, item in raw.items():
                doc_path = self.docs_dir / item.get("filename", f"{doc_id}.md")
                content = doc_path.read_text(encoding="utf-8") if doc_path.exists() else item.get("content", "")
                
                revisions = [
                    DocumentRevision(
                        revision_id=r.get("revision_id", 1),
                        content=r.get("content", ""),
                        timestamp=r.get("timestamp", ""),
                        author=r.get("author", "user"),
                        commit_message=r.get("commit_message", ""),
                    )
                    for r in item.get("revisions", [])
                ]
                
                self._documents[doc_id] = WorkspaceDocument(
                    id=doc_id,
                    title=item.get("title", "Dokument"),
                    filename=item.get("filename", f"{doc_id}.md"),
                    content=content,
                    created_at=item.get("created_at", datetime.now().isoformat()),
                    updated_at=item.get("updated_at", datetime.now().isoformat()),
                    revisions=revisions,
                )
        except Exception as e:
            logger.error(f"Error loading docs metadata: {e}")

    def _save_metadata(self) -> None:
        raw: Dict[str, Any] = {}
        for doc_id, doc in self._documents.items():
            raw[doc_id] = {
                "id": doc.id,
                "title": doc.title,
                "filename": doc.filename,
                "created_at": doc.created_at,
                "updated_at": doc.updated_at,
                "revisions": [asdict(r) for r in doc.revisions[-10:]],  # Keep last 10 revisions in meta
            }
        self.meta_file.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")

    def list_documents(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": d.id,
                "title": d.title,
                "filename": d.filename,
                "preview": d.content[:180],
                "char_count": len(d.content),
                "created_at": d.created_at,
                "updated_at": d.updated_at,
                "has_pending_diff": d.pending_diff is not None,
            }
            for d in self._documents.values()
        ]

    def get_document(self, doc_id: str) -> Optional[WorkspaceDocument]:
        return self._documents.get(doc_id)

    def create_document(self, title: str, content: str = "", filename: Optional[str] = None) -> WorkspaceDocument:
        doc_id = str(uuid.uuid4())[:8]
        safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
        fname = filename or f"{safe_title or 'doc'}_{doc_id}.md"
        now_iso = datetime.now().isoformat()

        doc = WorkspaceDocument(
            id=doc_id,
            title=title,
            filename=fname,
            content=content,
            created_at=now_iso,
            updated_at=now_iso,
            revisions=[DocumentRevision(revision_id=1, content=content, timestamp=now_iso, author="user", commit_message="Utworzenie dokumentu")],
        )

        doc_path = self.docs_dir / fname
        doc_path.write_text(content, encoding="utf-8")
        self._documents[doc_id] = doc
        self._save_metadata()
        return doc

    def update_document(self, doc_id: str, content: str, commit_message: str = "Edycja użytkownika") -> Optional[WorkspaceDocument]:
        doc = self._documents.get(doc_id)
        if not doc:
            return None

        now_iso = datetime.now().isoformat()
        rev_id = len(doc.revisions) + 1
        doc.revisions.append(
            DocumentRevision(revision_id=rev_id, content=content, timestamp=now_iso, author="user", commit_message=commit_message)
        )
        doc.content = content
        doc.updated_at = now_iso
        doc.pending_diff = None

        doc_path = self.docs_dir / doc.filename
        doc_path.write_text(content, encoding="utf-8")
        self._save_metadata()
        return doc

    def compute_diff(self, original_text: str, proposed_text: str, explanation: str = "") -> DocumentDiff:
        orig_lines = original_text.splitlines(keepends=True)
        prop_lines = proposed_text.splitlines(keepends=True)

        diff = list(difflib.unified_diff(orig_lines, prop_lines, fromfile="original", tofile="proposed"))
        diff_text = "".join(diff)

        additions = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

        return DocumentDiff(
            original_content=original_text,
            proposed_content=proposed_text,
            unified_diff=diff_text,
            additions=additions,
            deletions=deletions,
            explanation=explanation,
        )

    async def propose_ai_edit(self, doc_id: str, instruction: str) -> Optional[DocumentDiff]:
        """Ask LLM to edit document according to instruction and return a reviewable diff."""
        doc = self._documents.get(doc_id)
        if not doc:
            return None

        router = get_model_router()
        prompt = f"""Jesteś redaktorem i autorem w systemie MonikAI Workspace (Odysseus Docs Engine).
Masz za zadanie zmodyfikować poniższy dokument zgodnie z instrukcją użytkownika.

INSTRUKCJA:
{instruction}

ORYGINALNA TREŚĆ DOKUMENTU:
```markdown
{doc.content}
```

Zwróć odpowiedź w formacie JSON z polami:
- "proposed_content": pełna, zmodyfikowana treść dokumentu po wprowadzonych zmianach.
- "explanation": zwięzłe podsumowanie (2-3 zdania w języku polskim) co i dlaczego zmieniono.
"""

        res = await router.complete(
            messages=[LLMMessage(role="user", content=prompt)],
            task="agent",
            response_format={"type": "json_object"},
        )

        try:
            data = json.loads(res.content)
            proposed_content = data.get("proposed_content", doc.content)
            explanation = data.get("explanation", "Wprowadzono modyfikacje zgodnie z poleceniem.")
        except Exception:
            proposed_content = res.content
            explanation = "Zaproponowano nową wersję dokumentu."

        diff = self.compute_diff(doc.content, proposed_content, explanation=explanation)
        doc.pending_diff = diff
        return diff

    def accept_pending_diff(self, doc_id: str) -> Optional[WorkspaceDocument]:
        doc = self._documents.get(doc_id)
        if not doc or not doc.pending_diff:
            return None

        proposed = doc.pending_diff.proposed_content
        now_iso = datetime.now().isoformat()
        rev_id = len(doc.revisions) + 1
        doc.revisions.append(
            DocumentRevision(
                revision_id=rev_id,
                content=proposed,
                timestamp=now_iso,
                author="monika_ai",
                commit_message=f"Zatwierdzono propozycję AI: {doc.pending_diff.explanation[:60]}",
            )
        )
        doc.content = proposed
        doc.updated_at = now_iso
        doc.pending_diff = None

        doc_path = self.docs_dir / doc.filename
        doc_path.write_text(proposed, encoding="utf-8")
        self._save_metadata()
        return doc

    def reject_pending_diff(self, doc_id: str) -> bool:
        doc = self._documents.get(doc_id)
        if not doc or not doc.pending_diff:
            return False
        doc.pending_diff = None
        return True


# Global singleton instance
_GLOBAL_DOCS_SERVICE: Optional[DocsService] = None


def get_docs_service(data_dir: Optional[Path] = None) -> DocsService:
    global _GLOBAL_DOCS_SERVICE
    if _GLOBAL_DOCS_SERVICE is None:
        _GLOBAL_DOCS_SERVICE = DocsService(data_dir=data_dir)
    return _GLOBAL_DOCS_SERVICE
