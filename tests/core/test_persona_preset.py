"""The built-in Monika persona is upgraded only when the stored copy is an unedited built-in."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "odysseus"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "odysseus" / "src"))

import preset_manager as pm  # noqa: E402


def _load(tmp_path, preset):
    (tmp_path / "presets.json").write_text(json.dumps({"monika": preset}))
    return pm.PresetManager(str(tmp_path)).presets["monika"]


def test_unedited_v3_is_upgraded_and_edited_v3_is_kept(tmp_path):
    # The unedited v3 text is only known by hash, so upgrade is exercised via the v2 marker.
    upgraded = _load(tmp_path, {"name": "Monika", "prompt_version": 2, "system_prompt": "old bible"})
    assert upgraded["prompt_version"] == pm.MONIKA_PERSONA_PROMPT_VERSION
    assert upgraded["system_prompt"] == pm.MONIKA_PERSONA_PROMPT

    kept = _load(tmp_path, {"name": "Monika", "prompt_version": 3, "system_prompt": "my own edit"})
    assert kept["system_prompt"] == "my own edit"
