from __future__ import annotations

from pathlib import Path

from citadel.core import prefix


def test_read_prefix_picks_first_non_empty_line(tmp_path: Path) -> None:
    addon = tmp_path / "addon"
    addon.mkdir()
    (addon / "$PBOPREFIX$").write_text("\n\nCitadel\\Vault\n", encoding="utf-8")
    info = prefix.read_prefix(addon, fallback_name="addon")
    assert info.prefix == "Citadel\\Vault"
    assert len(info.source_files) == 1


def test_multiple_prefix_files_detected(tmp_path: Path) -> None:
    addon = tmp_path / "addon"
    addon.mkdir()
    (addon / "$PBOPREFIX$").write_text("A", encoding="utf-8")
    (addon / "$prefix$").write_text("B", encoding="utf-8")
    info = prefix.read_prefix(addon, fallback_name="addon")
    assert info.is_multiple


def test_fallback_to_addon_name(tmp_path: Path) -> None:
    addon = tmp_path / "addon"
    addon.mkdir()
    info = prefix.read_prefix(addon, fallback_name="MyAddon")
    assert info.prefix == "MyAddon"
    assert info.source_files == []


def test_warning_flags() -> None:
    assert prefix.looks_like_drive_path("P:\\addon")
    assert prefix.has_forward_slashes("My/Addon")
    assert prefix.has_leading_or_trailing_slash("\\My\\Addon")
