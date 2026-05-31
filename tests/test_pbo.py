"""Round-trip tests for PBO read + write."""

from __future__ import annotations

from pathlib import Path

import pytest

from citadel.core import pbo


def test_round_trip_single_file(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "config.cpp").write_text("class CfgPatches {};\n", encoding="utf-8")
    (source / "data" / "icon.txt").parent.mkdir()
    (source / "data" / "icon.txt").write_text("hello icon", encoding="utf-8")

    writer = pbo.PboWriter(prefix="My\\Addon", product="Citadel PBO Builder", version="test")
    writer.add_folder(source)

    out = tmp_path / "my_addon.pbo"
    writer.write(out)

    archive = pbo.read_pbo(out)
    assert archive.prefix == "My\\Addon"
    names = sorted(e.name.lower() for e in archive.entries)
    assert "config.cpp" in names
    assert "data\\icon.txt" in names

    config_entry = archive.find("config.cpp")
    assert config_entry is not None
    payload = pbo.read_entry_bytes(archive, config_entry)
    assert payload.startswith(b"class CfgPatches")


def test_extract_all_writes_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("alpha", encoding="utf-8")
    nested = source / "sub"
    nested.mkdir()
    (nested / "b.txt").write_text("beta", encoding="utf-8")

    writer = pbo.PboWriter(prefix="X")
    writer.add_folder(source)
    out = tmp_path / "x.pbo"
    writer.write(out)

    archive = pbo.read_pbo(out)
    extract_root = tmp_path / "extract"
    written = pbo.extract_all(archive, extract_root)
    assert (extract_root / "a.txt").read_text() == "alpha"
    assert (extract_root / "sub" / "b.txt").read_text() == "beta"
    assert len(written) == 2


def test_write_prefix_file_round_trips(tmp_path: Path) -> None:
    """The PBO prefix must survive extract -> rebuild via $PBOPREFIX$."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "config.cpp").write_text("class CfgPatches {};\n", encoding="utf-8")

    writer = pbo.PboWriter(prefix="AP_equipment_PUBLIC", product="test")
    writer.add_folder(source)
    pbo_path = tmp_path / "AP_equipment_PUBLIC.pbo"
    writer.write(pbo_path)

    archive = pbo.read_pbo(pbo_path)
    assert archive.prefix == "AP_equipment_PUBLIC"

    extract = tmp_path / "AP_equipment_PUBLIC_extracted"
    extract.mkdir()
    pbo.extract_all(archive, extract)

    # Without the helper, no prefix file lands on disk — extract_all alone
    # is not enough. Confirm the bug surface still exists.
    assert not (extract / "$PBOPREFIX$").exists()

    # The helper writes it out and the Builder's prefix reader picks it up.
    written = pbo.write_prefix_file(archive, extract)
    assert written is not None and written.name == "$PBOPREFIX$"

    from citadel.core import prefix as prefix_mod
    info = prefix_mod.read_prefix(extract, fallback_name=extract.name)
    assert info.prefix == "AP_equipment_PUBLIC"
    assert not info.is_multiple


def test_write_prefix_file_skips_when_no_prefix(tmp_path: Path) -> None:
    archive = pbo.PboArchive(source_path=tmp_path / "fake.pbo")
    assert pbo.write_prefix_file(archive, tmp_path) is None
    assert not (tmp_path / "$PBOPREFIX$").exists()


def test_safe_extract_refuses_traversal(tmp_path: Path) -> None:
    archive = pbo.PboArchive(source_path=tmp_path / "fake.pbo")
    archive.entries.append(pbo.PboEntry(
        name="..\\..\\evil.txt", packing_method=pbo.PACK_STORED,
        original_size=4, reserved=0, timestamp=0, data_size=4, data_offset=0,
    ))
    with pytest.raises(pbo.PboError):
        pbo.extract_entry(archive, archive.entries[0], tmp_path)
