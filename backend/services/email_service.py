"""Secure Email Service — IMAP reader and strict Draft-First approval workflow."""

from __future__ import annotations

import email
import imaplib
import json
import logging
import smtplib
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    id: str
    subject: str
    sender: str
    recipients: List[str]
    date: str
    snippet: str
    body_text: str
    is_read: bool = False


@dataclass
class EmailDraft:
    id: str
    to: str
    subject: str
    body: str
    created_at: str
    status: str = "pending_approval"  # "pending_approval", "approved", "sent", "rejected"
    error: Optional[str] = None
    sent_at: Optional[str] = None


class EmailService:
    """Manages email fetching and safe Draft-First composition."""

    def __init__(self, data_dir: Optional[Path] = None, settings_getter: Optional[Any] = None):
        self.data_dir = (data_dir or Path("data")).resolve()
        self.email_dir = self.data_dir / "email"
        self.email_dir.mkdir(parents=True, exist_ok=True)
        self.drafts_file = self.email_dir / "drafts.json"
        self.settings_getter = settings_getter
        self.drafts: Dict[str, EmailDraft] = {}
        self._load_drafts()

    def _load_drafts(self) -> None:
        if not self.drafts_file.exists():
            return
        try:
            raw = json.loads(self.drafts_file.read_text(encoding="utf-8"))
            for d_id, item in raw.items():
                self.drafts[d_id] = EmailDraft(
                    id=d_id,
                    to=item.get("to", ""),
                    subject=item.get("subject", ""),
                    body=item.get("body", ""),
                    created_at=item.get("created_at", ""),
                    status=item.get("status", "pending_approval"),
                    error=item.get("error"),
                    sent_at=item.get("sent_at"),
                )
        except Exception as e:
            logger.error(f"Failed to load email drafts: {e}")

    def _save_drafts(self) -> None:
        raw = {d_id: asdict(d) for d_id, d in self.drafts.items()}
        self.drafts_file.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")

    def create_draft(self, to: str, subject: str, body: str) -> EmailDraft:
        """Create a new draft that strictly requires user confirmation before sending."""
        d_id = str(uuid.uuid4())[:8]
        now_iso = datetime.now().isoformat()
        draft = EmailDraft(
            id=d_id,
            to=to,
            subject=subject,
            body=body,
            created_at=now_iso,
            status="pending_approval",
        )
        self.drafts[d_id] = draft
        self._save_drafts()
        logger.info(f"Created email draft '{subject}' (id={d_id}) awaiting user confirmation")
        return draft

    def list_drafts(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        drafts_list = list(self.drafts.values())
        if status:
            drafts_list = [d for d in drafts_list if d.status == status]
        return [asdict(d) for d in sorted(drafts_list, key=lambda x: x.created_at, reverse=True)]

    def get_draft(self, draft_id: str) -> Optional[EmailDraft]:
        return self.drafts.get(draft_id)

    async def approve_and_send(self, draft_id: str) -> Dict[str, Any]:
        """Approve and dispatch an email draft via SMTP."""
        draft = self.drafts.get(draft_id)
        if not draft:
            return {"ok": False, "error": "Draft not found"}

        if draft.status == "sent":
            return {"ok": False, "error": "Draft has already been sent"}

        # Check SMTP settings
        settings = self.settings_getter() if self.settings_getter else {}
        smtp_cfg = settings.get("email", {}).get("smtp", {})

        host = smtp_cfg.get("host")
        port = int(smtp_cfg.get("port", 587))
        user = smtp_cfg.get("user")
        password = smtp_cfg.get("password")

        if host and user and password:
            try:
                msg = MIMEMultipart()
                msg["From"] = user
                msg["To"] = draft.to
                msg["Subject"] = draft.subject
                msg.attach(MIMEText(draft.body, "plain", "utf-8"))

                with smtplib.SMTP(host, port, timeout=15.0) as server:
                    server.starttls()
                    server.login(user, password)
                    server.send_message(msg)

                draft.status = "sent"
                draft.sent_at = datetime.now().isoformat()
                self._save_drafts()
                return {"ok": True, "message": "Email sent successfully", "draft_id": draft_id}
            except Exception as e:
                draft.error = str(e)
                self._save_drafts()
                return {"ok": False, "error": f"SMTP error: {e}"}
        else:
            # Simulated sending mode for testing/local dev
            draft.status = "sent"
            draft.sent_at = datetime.now().isoformat()
            self._save_drafts()
            return {"ok": True, "message": "Email approved and marked as sent (Simulated dev mode)", "draft_id": draft_id}

    def reject_draft(self, draft_id: str) -> bool:
        draft = self.drafts.get(draft_id)
        if not draft:
            return False
        draft.status = "rejected"
        self._save_drafts()
        return True


# Global singleton instance
_GLOBAL_EMAIL_SERVICE: Optional[EmailService] = None


def get_email_service(data_dir: Optional[Path] = None, settings_getter: Optional[Any] = None) -> EmailService:
    global _GLOBAL_EMAIL_SERVICE
    if _GLOBAL_EMAIL_SERVICE is None:
        _GLOBAL_EMAIL_SERVICE = EmailService(data_dir=data_dir, settings_getter=settings_getter)
    return _GLOBAL_EMAIL_SERVICE
