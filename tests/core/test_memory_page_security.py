import pytest

from backend.services.memory_adapter import MemoryEngine


def test_memory_page_methods_reject_paths_outside_pages_root(tmp_path):
    engine = MemoryEngine(base_dir=tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="escapes memory/pages"):
        engine.get_page(str(outside))
    with pytest.raises(ValueError, match="escapes memory/pages"):
        engine.append_page("../outside.md", "changed")
    with pytest.raises(ValueError, match="escapes memory/pages"):
        engine.create_page("Escape", folder="../../outside")

    assert outside.read_text(encoding="utf-8") == "secret"


def test_absolute_internal_page_path_remains_supported(tmp_path):
    engine = MemoryEngine(base_dir=tmp_path)
    page = engine.pages_dir / "journal" / "today.md"

    engine.append_page(str(page), "pierwszy wpis")

    assert "pierwszy wpis" in engine.get_page(str(page))

