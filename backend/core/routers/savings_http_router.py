"""HTTP adapter for the Savings statement importer and centralized ledger storage."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from fastapi import Body, File, HTTPException, UploadFile

from backend.services.savings_service import get_savings_service
from backend.services.savings_statement_parser import (
    MAX_STATEMENT_BYTES,
    StatementParseError,
    parse_bank_statement,
)


def register_savings_http_routes(app, emit_to_frontend: Optional[Callable[[str, Any], Any]] = None):
    @app.get("/api/savings/ledger")
    async def get_savings_ledger():
        svc = get_savings_service()
        result = svc.get_ledger()
        return {"status": "ok", **result}

    @app.put("/api/savings/ledger")
    async def save_savings_ledger(payload: Dict[str, Any] = Body(...)):
        svc = get_savings_service()
        try:
            saved = svc.save_ledger(payload)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save ledger: {e}")

        if emit_to_frontend:
            try:
                res = emit_to_frontend("savings:updated", saved)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception:
                pass

        return {"status": "ok", "ledger": saved}

    @app.post("/api/savings/reset")
    async def reset_savings_ledger():
        svc = get_savings_service()
        try:
            result = svc.reset_ledger()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to reset ledger: {e}")

        if emit_to_frontend:
            try:
                res = emit_to_frontend("savings:updated", None)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception:
                pass

        return {"status": "ok", **result}

    @app.post("/api/savings/import-statement")
    async def import_savings_statement(file: UploadFile = File(...)):
        filename = Path(file.filename or "statement").name
        suffix = Path(filename).suffix.lower()
        allowed = {".pdf", ".csv", ".tsv", ".txt", ".json", ".ofx", ".mt940"}
        content_type = str(file.content_type or "")
        if suffix not in allowed and not any(
            marker in content_type.lower() for marker in ("pdf", "csv", "text", "json", "ofx")
        ):
            raise HTTPException(status_code=415, detail="Use a PDF, CSV, TSV, TXT, JSON, OFX or MT940 statement")

        payload = await file.read(MAX_STATEMENT_BYTES + 1)
        if len(payload) > MAX_STATEMENT_BYTES:
            raise HTTPException(status_code=413, detail="The statement is larger than the 25 MB import limit")
        try:
            result = await asyncio.to_thread(parse_bank_statement, payload, filename, content_type)
        except StatementParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return result
