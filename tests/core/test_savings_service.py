from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.routers.savings_http_router import register_savings_http_routes
from backend.services.savings_service import SavingsService, normalize_ledger_state


def test_savings_service_uninitialized(tmp_path: Path):
    ledger_file = tmp_path / "savings_ledger.json"
    service = SavingsService(ledger_path=ledger_file)
    assert not service.is_initialized()

    result = service.get_ledger()
    assert result["initialized"] is False
    assert result["ledger"] is None


def test_savings_service_save_and_load(tmp_path: Path):
    ledger_file = tmp_path / "savings_ledger.json"
    service = SavingsService(ledger_path=ledger_file)

    payload = {
        "settings": {
            "currency": "PLN",
            "income": 7000,
            "monthlyLimit": 3500,
            "payday": 10,
        },
        "wallets": [
            {
                "id": "wallet-1",
                "name": "Konto Główne",
                "balance": 5000,
                "savings": 2000,
                "debt": 0,
                "includeSavings": True,
                "color": "#ee9fc5",
            }
        ],
        "transactions": [
            {
                "id": "tx-1",
                "date": "2026-09-01",
                "merchant": "Biedronka",
                "amount": 120.5,
                "direction": "expense",
                "category": "Needs",
                "walletId": "wallet-1",
            }
        ],
        "months": [
            {"key": "2026-09", "expenses": 120.5, "income": 7000, "limit": 3500}
        ],
        "dailyHistory": [
            {"date": "2026-09-23", "balance": 5000, "dailyLimit": 250, "daysToPayday": 20}
        ],
    }

    saved = service.save_ledger(payload)
    assert service.is_initialized()
    assert saved["settings"]["income"] == 7000
    assert len(saved["wallets"]) == 1
    assert saved["wallets"][0]["name"] == "Konto Główne"
    assert len(saved["transactions"]) == 1
    assert saved["transactions"][0]["merchant"] == "Biedronka"

    # Reload from disk
    loaded = service.get_ledger()
    assert loaded["initialized"] is True
    assert loaded["ledger"]["settings"]["income"] == 7000
    assert loaded["ledger"]["wallets"][0]["id"] == "wallet-1"
    assert loaded["ledger"]["wallets"][0]["balance"] == 5000.0


def test_savings_service_reset(tmp_path: Path):
    ledger_file = tmp_path / "savings_ledger.json"
    service = SavingsService(ledger_path=ledger_file)
    service.save_ledger({"settings": {"income": 10000}})
    assert service.is_initialized()

    reset_res = service.reset_ledger()
    assert reset_res["initialized"] is False
    assert not service.is_initialized()


def test_savings_http_routes(tmp_path: Path, monkeypatch):
    ledger_file = tmp_path / "savings_ledger.json"
    test_service = SavingsService(ledger_path=ledger_file)

    monkeypatch.setattr(
        "backend.core.routers.savings_http_router.get_savings_service",
        lambda: test_service,
    )

    emitted_events = []

    def mock_emit(event, data):
        emitted_events.append((event, data))

    app = FastAPI()
    register_savings_http_routes(app, emit_to_frontend=mock_emit)
    client = TestClient(app)

    # 1. GET when uninitialized
    res = client.get("/api/savings/ledger")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "initialized": False, "ledger": None}

    # 2. PUT to save ledger
    sample_data = {
        "settings": {"currency": "PLN", "income": 8000, "payday": 1},
        "wallets": [{"id": "main", "name": "Main", "balance": 1500}],
        "transactions": [],
        "months": [],
        "dailyHistory": [],
    }
    put_res = client.put("/api/savings/ledger", json=sample_data)
    assert put_res.status_code == 200
    body = put_res.json()
    assert body["status"] == "ok"
    assert body["ledger"]["settings"]["income"] == 8000
    assert len(emitted_events) == 1
    assert emitted_events[0][0] == "savings:updated"

    # 3. GET after saving
    get_res = client.get("/api/savings/ledger")
    assert get_res.status_code == 200
    assert get_res.json()["initialized"] is True
    assert get_res.json()["ledger"]["settings"]["income"] == 8000

    # 4. POST reset
    reset_res = client.post("/api/savings/reset")
    assert reset_res.status_code == 200
    assert reset_res.json()["initialized"] is False
    assert len(emitted_events) == 2

