"""Tests for the reskin (retexture) layer: registry persistence, validation, and
a full extract → replace → repack build using synthetic PBOs (no DayZ Tools)."""
from __future__ import annotations

from pathlib import Path

import pytest

from citadel.core import pbo
from citadel.core.reskin import (
    ReskinEntry,
    ReskinTarget,
    ReskinError,
    build_reskin,
    load_registry,
    save_registry,
    validate_target,
)


def _make_source_pbo(tmp_path: Path) -> Path:
    """Build a small PBO with data/skin.paa and config.cpp under a known prefix."""
    src = tmp_path / "src"
    (src / "data").mkdir(parents=True)
    (src / "data" / "skin.paa").write_bytes(b"ORIGINAL-PAA")
    (src / "config.cpp").write_text("class CfgPatches {};")
    out = tmp_path / "source.pbo"
    writer = pbo.PboWriter(prefix="Test\\Mod", product="p", version="1")
    writer.add_folder(src)
    writer.write(out)
    return out


# ── Registry ─────────────────────────────────────────────────

def test_registry_round_trip(tmp_path: Path) -> None:
    targets = [ReskinTarget(name="Skin A", source_pbo="src.pbo",
                            entries=[ReskinEntry("a\\b.paa", "rep.paa")])]
    path = tmp_path / "reg.json"
    save_registry(path, targets)
    assert load_registry(path) == targets


# ── Validation ───────────────────────────────────────────────

def test_validate_flags_missing_source_replacement_and_bad_target(tmp_path: Path) -> None:
    target = ReskinTarget("t", str(tmp_path / "nope.pbo"),
                          [ReskinEntry("a\\b.txt", str(tmp_path / "missing.paa"))])
    errors = validate_target(target)
    assert any("Source PBO not found" in e for e in errors)
    assert any("not a .paa texture" in e for e in errors)
    assert any("Replacement image not found" in e for e in errors)


def test_validate_against_archive_presence(tmp_path: Path) -> None:
    source_pbo = _make_source_pbo(tmp_path)
    rep = tmp_path / "r.paa"
    rep.write_bytes(b"X")
    archive = pbo.read_pbo(source_pbo)

    ok = ReskinTarget("t", str(source_pbo), [ReskinEntry("data\\skin.paa", str(rep))])
    assert validate_target(ok, archive=archive) == []

    ghost = ReskinTarget("t", str(source_pbo), [ReskinEntry("data\\ghost.paa", str(rep))])
    assert any("not present in source PBO" in e for e in validate_target(ghost, archive=archive))


# ── Build ────────────────────────────────────────────────────

def test_build_reskin_replaces_texture_and_preserves_rest(tmp_path: Path) -> None:
    source_pbo = _make_source_pbo(tmp_path)
    new_paa = tmp_path / "new_skin.paa"
    new_paa.write_bytes(b"NEW-SKIN-BYTES")

    target = ReskinTarget("t", str(source_pbo),
                          [ReskinEntry("data\\skin.paa", str(new_paa))])
    out = tmp_path / "reskinned.pbo"
    result = build_reskin(target, out)

    assert result.applied == ["data\\skin.paa"]
    assert result.missing == []

    archive = pbo.read_pbo(out)
    assert archive.prefix == "Test\\Mod"  # prefix carried through
    assert pbo.read_entry_bytes(archive, archive.find("data\\skin.paa")) == b"NEW-SKIN-BYTES"
    # Untouched files survive verbatim.
    assert pbo.read_entry_bytes(archive, archive.find("config.cpp")) == b"class CfgPatches {};"


def test_missing_texture_is_reported_not_applied(tmp_path: Path) -> None:
    source_pbo = _make_source_pbo(tmp_path)
    rep = tmp_path / "n.paa"
    rep.write_bytes(b"X")
    target = ReskinTarget("t", str(source_pbo), [ReskinEntry("data\\nope.paa", str(rep))])
    result = build_reskin(target, tmp_path / "o.pbo")
    assert result.applied == []
    assert result.missing == ["data\\nope.paa"]


def test_non_paa_without_converter_raises(tmp_path: Path) -> None:
    source_pbo = _make_source_pbo(tmp_path)
    png = tmp_path / "s.png"
    png.write_bytes(b"PNG")
    target = ReskinTarget("t", str(source_pbo), [ReskinEntry("data\\skin.paa", str(png))])
    with pytest.raises(ReskinError):
        build_reskin(target, tmp_path / "o.pbo")


def test_converter_used_for_non_paa_replacement(tmp_path: Path) -> None:
    source_pbo = _make_source_pbo(tmp_path)
    png = tmp_path / "s.png"
    png.write_bytes(b"PNG-SOURCE")

    def fake_convert(src: Path, dest: Path) -> None:
        dest.write_bytes(b"CONVERTED-PAA")

    target = ReskinTarget("t", str(source_pbo), [ReskinEntry("data\\skin.paa", str(png))])
    out = tmp_path / "o.pbo"
    result = build_reskin(target, out, convert_image=fake_convert)

    assert result.applied == ["data\\skin.paa"]
    archive = pbo.read_pbo(out)
    assert pbo.read_entry_bytes(archive, archive.find("data\\skin.paa")) == b"CONVERTED-PAA"


def test_sign_callback_invoked_when_textures_applied(tmp_path: Path) -> None:
    source_pbo = _make_source_pbo(tmp_path)
    rep = tmp_path / "n.paa"
    rep.write_bytes(b"N")
    calls: list[Path] = []

    def fake_sign(p: Path):
        calls.append(p)

        class _R:
            bisign = Path(str(p) + ".bisign")

        return _R()

    target = ReskinTarget("t", str(source_pbo), [ReskinEntry("data\\skin.paa", str(rep))])
    result = build_reskin(target, tmp_path / "o.pbo", sign=fake_sign)

    assert result.signed is True
    assert len(calls) == 1
    assert result.bisign is not None


def test_sign_skipped_when_nothing_applied(tmp_path: Path) -> None:
    source_pbo = _make_source_pbo(tmp_path)
    rep = tmp_path / "n.paa"
    rep.write_bytes(b"N")
    calls: list[Path] = []

    target = ReskinTarget("t", str(source_pbo), [ReskinEntry("data\\ghost.paa", str(rep))])
    result = build_reskin(target, tmp_path / "o.pbo", sign=lambda p: calls.append(p))

    assert result.signed is False
    assert calls == []
