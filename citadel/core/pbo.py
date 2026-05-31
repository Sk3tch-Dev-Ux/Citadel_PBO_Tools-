"""PBO (Packed Bank Of files) read and write support.

The PBO format used by DayZ / Arma engines is a flat archive made of:

  1. An optional header entry carrying ``Mime = "Vers"`` and a chain of
     null-terminated key/value strings (e.g. ``prefix=My\\Addon``). The first
     entry of the file is this header whenever it carries metadata.
  2. A sequence of file entries. Each entry's header is::

         filename (null-terminated ASCII)
         packing_method  uint32 little-endian
         original_size   uint32 little-endian
         reserved        uint32
         timestamp       uint32 (unix seconds)
         data_size       uint32 (bytes stored in the data block)

     A final zero-name entry with all-zero fields terminates the index.
  3. After the terminator, the file data blocks appear in index order.
  4. An optional 21-byte trailer: one zero byte + 20-byte SHA1 over the
     header+data sections.

Packing methods we recognize::

    0x00000000      stored (uncompressed) — data_size == original_size
    0x43707273 ("Cprs") BI LZSS compressed
    0x456e6372 ("Encr") encrypted (not supported for read/extract)
    0x56657273 ("Vers") product entry marker (header chain)

This module implements:

  - :func:`read_pbo` to parse a PBO from disk into :class:`PboArchive`.
  - :func:`extract_entry` and :func:`extract_all` for safe extraction.
  - :class:`PboWriter` to build a new PBO from staged files.
"""

from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterable

from citadel.core import lzss
from citadel.core.paths import is_safe_relative, normalize_pbo_path


PACK_STORED = 0x00000000
PACK_CPRS = 0x73727043  # "Cprs" in little-endian byte order
PACK_VERS = 0x56657273  # "Vers"
PACK_ENCR = 0x72636E45  # "Encr"


PACK_NAMES = {
    PACK_STORED: "Stored",
    PACK_CPRS: "Compressed (Cprs)",
    PACK_VERS: "Version header",
    PACK_ENCR: "Encrypted",
}


class PboError(Exception):
    """Raised for any unrecoverable PBO read/write failure."""


@dataclass
class PboEntry:
    """A single file entry inside a PBO."""

    name: str
    packing_method: int
    original_size: int
    reserved: int
    timestamp: int
    data_size: int
    data_offset: int = 0  # absolute offset in the source PBO

    @property
    def is_compressed(self) -> bool:
        return self.packing_method == PACK_CPRS

    @property
    def is_encrypted(self) -> bool:
        return self.packing_method == PACK_ENCR

    @property
    def is_stored(self) -> bool:
        return self.packing_method == PACK_STORED

    @property
    def is_supported_for_extract(self) -> bool:
        return self.is_stored or self.is_compressed

    def packing_name(self) -> str:
        return PACK_NAMES.get(self.packing_method, f"0x{self.packing_method:08X}")


@dataclass
class PboArchive:
    """An open (read-only) view of a parsed PBO file."""

    source_path: Path
    properties: dict[str, str] = field(default_factory=dict)
    entries: list[PboEntry] = field(default_factory=list)
    sha1: bytes | None = None  # raw 20-byte trailer SHA, if present
    header_size: int = 0  # bytes from file start through the index terminator

    @property
    def prefix(self) -> str:
        return self.properties.get("prefix", "")

    @property
    def product(self) -> str:
        return self.properties.get("product", "")

    @property
    def file_count(self) -> int:
        return len(self.entries)

    @property
    def total_unpacked_size(self) -> int:
        return sum(entry.original_size for entry in self.entries)

    def find(self, name: str) -> PboEntry | None:
        target = normalize_pbo_path(name).lower()
        for entry in self.entries:
            if normalize_pbo_path(entry.name).lower() == target:
                return entry
        return None


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _read_cstring(stream: BinaryIO, limit: int = 1024) -> str:
    """Read a null-terminated ASCII/latin-1 string."""
    chars: list[int] = []
    for _ in range(limit):
        byte = stream.read(1)
        if not byte:
            raise PboError("Unexpected end of file while reading string")
        if byte == b"\x00":
            return bytes(chars).decode("latin-1", errors="replace")
        chars.append(byte[0])
    raise PboError("String exceeded maximum allowed length while reading PBO")


def _read_entry_header(stream: BinaryIO) -> PboEntry | None:
    """Read one entry header. Returns ``None`` for the trailing all-zero terminator."""
    name = _read_cstring(stream)
    raw = stream.read(20)
    if len(raw) < 20:
        raise PboError("Truncated entry header")
    packing, original, reserved, timestamp, data_size = struct.unpack("<IIIII", raw)
    if name == "" and packing == 0 and original == 0 and reserved == 0 and timestamp == 0 and data_size == 0:
        return None
    return PboEntry(name, packing, original, reserved, timestamp, data_size)


def read_pbo(path: str | Path) -> PboArchive:
    """Parse a PBO and return its metadata + entry list (data is not yet extracted)."""
    pbo_path = Path(path)
    if not pbo_path.is_file():
        raise PboError(f"PBO not found: {pbo_path}")

    archive = PboArchive(source_path=pbo_path)
    with pbo_path.open("rb") as stream:
        # First entry may be the Vers header carrying property strings.
        first_pos = stream.tell()
        first_name = _read_cstring(stream)
        first_header = stream.read(20)
        if len(first_header) < 20:
            raise PboError("PBO is too small to contain a valid header")

        packing, original, reserved, timestamp, data_size = struct.unpack("<IIIII", first_header)
        if first_name == "" and packing == PACK_VERS:
            # Read property chain until empty key.
            while True:
                key = _read_cstring(stream)
                if key == "":
                    break
                value = _read_cstring(stream)
                archive.properties[key.lower()] = value
        else:
            # Not a property header — rewind to re-read this as a real entry.
            stream.seek(first_pos)

        # Read remaining entry headers.
        while True:
            entry = _read_entry_header(stream)
            if entry is None:
                break
            archive.entries.append(entry)

        # Compute data offsets sequentially after the index.
        data_cursor = stream.tell()
        archive.header_size = data_cursor
        for entry in archive.entries:
            entry.data_offset = data_cursor
            data_cursor += entry.data_size

        # SHA1 trailer (best-effort).
        try:
            stream.seek(data_cursor)
            trailer = stream.read(21)
            if len(trailer) == 21 and trailer[0] == 0:
                archive.sha1 = trailer[1:]
        except OSError:
            pass

    return archive


def read_entry_bytes(archive: PboArchive, entry: PboEntry) -> bytes:
    """Read and (if necessary) decompress a single entry's payload."""
    if entry.is_encrypted:
        raise PboError(f"Encrypted entry not supported: {entry.name}")
    with archive.source_path.open("rb") as stream:
        stream.seek(entry.data_offset)
        data = stream.read(entry.data_size)
    if entry.is_compressed:
        return lzss.decompress(data, entry.original_size)
    if entry.is_stored:
        return data
    raise PboError(f"Unsupported packing method 0x{entry.packing_method:08X} for {entry.name}")


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _safe_target(entry_name: str, root: Path) -> Path:
    """Map a PBO entry name to a safe filesystem path inside ``root``."""
    cleaned = normalize_pbo_path(entry_name).replace("\\", os.sep)
    if cleaned.startswith(os.sep) or (len(cleaned) > 1 and cleaned[1] == ":"):
        raise PboError(f"Refusing absolute path in entry: {entry_name}")
    if ".." in cleaned.split(os.sep):
        raise PboError(f"Refusing parent-folder traversal in entry: {entry_name}")
    target = root / cleaned
    if not is_safe_relative(target.parent, root):
        raise PboError(f"Refusing path that escapes output folder: {entry_name}")
    return target


def extract_entry(archive: PboArchive, entry: PboEntry, output_root: Path) -> Path:
    """Extract ``entry`` into ``output_root`` and return the written path."""
    target = _safe_target(entry.name, output_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = read_entry_bytes(archive, entry)
    with target.open("wb") as fh:
        fh.write(data)
    if entry.timestamp:
        try:
            os.utime(target, (entry.timestamp, entry.timestamp))
        except OSError:
            pass
    return target


def write_prefix_file(archive: PboArchive, output_root: Path) -> Path | None:
    """Persist the archive's PBO prefix as a ``$PBOPREFIX$`` file.

    The PBO prefix lives in the leading Vers properties chain — it is never an
    entry, so plain entry-by-entry extraction loses it. Without this helper,
    extracting ``AP_equipment_PUBLIC.pbo`` (prefix ``AP_equipment_PUBLIC``)
    into ``AP_equipment_PUBLIC_extracted/`` leaves no prefix file, and a
    later rebuild would fall back to the folder name and emit broken paths
    like ``AP_equipment_PUBLIC_extracted\\config.cpp``.

    Returns the written file path, or ``None`` if the archive carries no
    prefix to preserve.
    """
    if not archive.prefix:
        return None
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / "$PBOPREFIX$"
    # DayZ Tools and packers expect Windows line endings here.
    target.write_text(archive.prefix + "\r\n", encoding="utf-8")
    return target


def extract_all(archive: PboArchive, output_root: Path,
                progress: callable | None = None) -> list[Path]:
    """Extract every supported entry. Unsupported entries are skipped (caller can
    enumerate them by inspecting ``archive.entries``)."""
    output_root.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    total = len(archive.entries)
    for index, entry in enumerate(archive.entries):
        if not entry.is_supported_for_extract:
            continue
        path = extract_entry(archive, entry, output_root)
        extracted.append(path)
        if progress is not None:
            try:
                progress(index + 1, total, entry)
            except Exception:
                pass
    return extracted


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

class PboWriter:
    """Build a new PBO from a list of source files.

    Usage::

        writer = PboWriter(prefix="MyAddon")
        writer.add_file(Path("config.bin"), "config.bin")
        writer.write(Path("my_addon.pbo"))

    Properties are written into the leading Vers header. Files are written
    stored (uncompressed); compression is not currently emitted because the
    DayZ engine and signing tooling both accept stored PBOs and the tradeoff
    of write-time CPU vs. tiny size gains favors simplicity.
    """

    def __init__(self, prefix: str = "", product: str = "Citadel PBO Builder",
                 version: str = "", properties: dict[str, str] | None = None) -> None:
        props = dict(properties) if properties else {}
        if prefix:
            props.setdefault("prefix", prefix)
        if product:
            props.setdefault("product", product)
        if version:
            props.setdefault("version", version)
        self._properties: list[tuple[str, str]] = list(props.items())
        self._entries: list[tuple[str, Path, int]] = []  # (pbo name, source path, timestamp)

    def add_file(self, source: Path, pbo_name: str | None = None,
                 timestamp: int | None = None) -> None:
        """Queue ``source`` for inclusion under ``pbo_name`` (defaults to file name)."""
        if not source.is_file():
            raise PboError(f"Source file not found: {source}")
        name = pbo_name if pbo_name is not None else source.name
        name = normalize_pbo_path(name)
        if not name:
            raise PboError(f"PBO entry name resolved to empty for source {source}")
        if timestamp is None:
            try:
                timestamp = int(source.stat().st_mtime)
            except OSError:
                timestamp = 0
        self._entries.append((name, source, int(timestamp)))

    def add_folder(self, root: Path, exclude_patterns: list[str] | None = None) -> None:
        """Add every file under ``root`` keeping the relative path layout."""
        from citadel.core.paths import iter_files  # local import to keep module load light
        for path in iter_files(root, exclude_patterns or []):
            rel = path.relative_to(root)
            self.add_file(path, str(rel))

    def entry_count(self) -> int:
        return len(self._entries)

    def write(self, output_path: Path) -> Path:
        """Serialize the PBO to ``output_path``. Returns the written path."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sha1 = hashlib.sha1()

        with output_path.open("wb") as fh:
            # ---- Header (Vers) ----
            fh.write(b"\x00")  # empty name for the Vers header entry
            sha1.update(b"\x00")
            header = struct.pack("<IIIII", PACK_VERS, 0, 0, 0, 0)
            fh.write(header)
            sha1.update(header)
            for key, value in self._properties:
                k = key.encode("latin-1", errors="replace") + b"\x00"
                v = value.encode("latin-1", errors="replace") + b"\x00"
                fh.write(k)
                fh.write(v)
                sha1.update(k)
                sha1.update(v)
            fh.write(b"\x00")  # terminator for property chain
            sha1.update(b"\x00")

            # ---- Entry index ----
            for name, source, timestamp in self._entries:
                size = source.stat().st_size
                if size > 0xFFFFFFFF:
                    raise PboError(f"File too large for PBO format (>4GB): {source}")
                name_bytes = name.encode("latin-1", errors="replace") + b"\x00"
                fh.write(name_bytes)
                sha1.update(name_bytes)
                entry_header = struct.pack("<IIIII", PACK_STORED, size, 0, timestamp, size)
                fh.write(entry_header)
                sha1.update(entry_header)

            # ---- Index terminator (empty name + zeroed 20-byte block) ----
            fh.write(b"\x00")
            sha1.update(b"\x00")
            terminator = struct.pack("<IIIII", 0, 0, 0, 0, 0)
            fh.write(terminator)
            sha1.update(terminator)

            # ---- File data ----
            for _, source, _ in self._entries:
                with source.open("rb") as src:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        fh.write(chunk)
                        sha1.update(chunk)

            # ---- Trailer: 0x00 + SHA1 ----
            fh.write(b"\x00" + sha1.digest())

        return output_path
