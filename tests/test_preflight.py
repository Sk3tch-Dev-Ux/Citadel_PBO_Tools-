from __future__ import annotations

from pathlib import Path

from citadel.builder.discovery import AddonTarget
from citadel.builder.preflight import Level, PreflightOptions, run_preflight


def _make_target(root: Path, name: str = "TestAddon") -> AddonTarget:
    return AddonTarget(name=name, source=root, has_config=True, has_wrp=False, prefix_files=[])


def test_missing_cfg_patches_warns(tmp_path: Path) -> None:
    addon = tmp_path / "addon"
    addon.mkdir()
    (addon / "config.cpp").write_text("class Foo {};\n", encoding="utf-8")
    findings = run_preflight(_make_target(addon), PreflightOptions(), cfgconvert=None)
    rules = {f.rule for f in findings}
    assert "config.cfg_patches.missing" in rules


def test_modded_class_with_base_errors(tmp_path: Path) -> None:
    addon = tmp_path / "addon"
    addon.mkdir()
    (addon / "config.cpp").write_text("class CfgPatches { class A { requiredAddons[]={}; }; };\n",
                                       encoding="utf-8")
    (addon / "scripts").mkdir()
    (addon / "scripts" / "foo.c").write_text(
        "modded class PlayerBase extends ManBase\n{\n}\n", encoding="utf-8")
    findings = run_preflight(_make_target(addon), PreflightOptions(), cfgconvert=None)
    levels = [f.level for f in findings if f.rule == "script.modded_class.base"]
    assert Level.ERROR in levels


def test_clean_addon_no_errors(tmp_path: Path) -> None:
    addon = tmp_path / "addon"
    addon.mkdir()
    (addon / "$PBOPREFIX$").write_text("My\\Addon\n", encoding="utf-8")
    (addon / "config.cpp").write_text(
        'class CfgPatches { class My_Addon { requiredAddons[]={}; }; };\n', encoding="utf-8")
    findings = run_preflight(_make_target(addon), PreflightOptions(), cfgconvert=None)
    errors = [f for f in findings if f.level == Level.ERROR]
    assert errors == []
