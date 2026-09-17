from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

_ODY_ROOT = Path(__file__).resolve().parents[2] / "backend" / "odysseus"
if str(_ODY_ROOT) not in sys.path:
    sys.path.insert(0, str(_ODY_ROOT))

from backend.odysseus_bridge import _mount_upload_routes


def test_bridge_mounts_native_upload_endpoint():
    app = FastAPI()

    _mount_upload_routes(app, object())

    assert "/api/upload" in app.openapi()["paths"]
    assert "post" in app.openapi()["paths"]["/api/upload"]
    assert callable(app.state.upload_rate_cleanup)
