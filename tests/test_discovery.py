from __future__ import annotations

from pathlib import Path

from citadel.builder.discovery import discover_addons


def test_mono_addon_project(tmp_path: Path) -> None:
    (tmp_path / "config.cpp").write_text("class CfgPatches {};\n", encoding="utf-8")
    targets = discover_addons(tmp_path, exclude_patterns=[])
    assert len(targets) == 1
    assert targets[0].source == tmp_path


def test_multi_addon_project(tmp_path: Path) -> None:
    for name in ("AddonA", "AddonB"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "config.cpp").write_text("class CfgPatches {};\n", encoding="utf-8")
    targets = discover_addons(tmp_path, exclude_patterns=[])
    names = sorted(t.name for t in targets)
    assert names == ["AddonA", "AddonB"]


def test_excludes_terrain_work_folders(tmp_path: Path) -> None:
    for name in ("AddonA", "source", "exports", "tb"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "config.cpp").write_text("dummy\n", encoding="utf-8")
    targets = discover_addons(tmp_path, exclude_patterns=[])
    assert {t.name for t in targets} == {"AddonA"}


def test_detects_terrain_addon_by_wrp(tmp_path: Path) -> None:
    addon = tmp_path / "MyMap"
    (addon / "data").mkdir(parents=True)
    (addon / "data" / "world.wrp").write_bytes(b"\x00" * 64)
    targets = discover_addons(tmp_path, exclude_patterns=[])
    assert len(targets) == 1
    assert targets[0].has_wrp
