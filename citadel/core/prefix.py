"""Detection of PBO prefix helper files inside addon source folders.

DayZ addons declare their internal PBO prefix using one of these files at the
addon root:

    $PBOPREFIX$
    $prefix$
    $PBOPREFIX$.txt
    $prefix$.txt

The first non-empty line of the file is the internal prefix. These helper
files are NOT packed into the final PBO themselves — the prefix instead goes
into the PBO ``properties`` chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PREFIX_FILE_NAMES = (
    "$PBOPREFIX$",
    "$prefix$",
    "$PBOPREFIX$.txt",
    "$prefix$.txt",
)


@dataclass
class PrefixInfo:
    """Outcome of scanning an addon folder for prefix helper files."""

    prefix: str
    source_files: list[Path]  # all detected helper files (>1 is a warning)
    raw_content: str = ""

    @property
    def is_multiple(self) -> bool:
        return len(self.source_files) > 1


def find_prefix_files(addon_root: Path) -> list[Path]:
    """Return every prefix helper file present in ``addon_root`` (case-insensitive)."""
    if not addon_root.is_dir():
        return []
    candidates: list[Path] = []
    lower_targets = {name.lower() for name in PREFIX_FILE_NAMES}
    for child in addon_root.iterdir():
        if child.is_file() and child.name.lower() in lower_targets:
            candidates.append(child)
    return sorted(candidates, key=lambda p: p.name.lower())


def read_prefix(addon_root: Path, fallback_name: str = "") -> PrefixInfo:
    """Read the addon's prefix.

    Falls back to ``fallback_name`` (typically the addon folder name) when no
    helper file is present or readable.
    """
    files = find_prefix_files(addon_root)
    if not files:
        return PrefixInfo(prefix=fallback_name, source_files=[], raw_content="")
    main = files[0]
    try:
        text = main.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return PrefixInfo(prefix=fallback_name, source_files=files, raw_content="")

    # First non-empty stripped line wins.
    extracted = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            extracted = stripped
            break
    if not extracted:
        extracted = fallback_name
    return PrefixInfo(prefix=extracted, source_files=files, raw_content=text)


def is_prefix_file(name: str) -> bool:
    """Return True if ``name`` is one of the recognized prefix helper names."""
    return name.lower() in {n.lower() for n in PREFIX_FILE_NAMES}


def looks_like_drive_path(prefix: str) -> bool:
    """Return True if prefix starts with a Windows drive letter like ``P:\\``."""
    return len(prefix) >= 2 and prefix[1] == ":" and prefix[0].isalpha()


def has_forward_slashes(prefix: str) -> bool:
    return "/" in prefix


def has_leading_or_trailing_slash(prefix: str) -> bool:
    return prefix.startswith(("\\", "/")) or prefix.endswith(("\\", "/"))
