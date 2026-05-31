"""Addon discovery.

Given a Project Source folder, return the list of addon folders that should be
offered as build targets. The rules mirror what a real packer does:

  - If the selected folder itself contains a ``config.cpp``, treat the folder
    as a single addon target (mono-addon project).
  - Otherwise, each immediate child folder that contains a ``config.cpp`` is a
    candidate target.
  - Terrain source/export work folders (``source``, ``exports``,
    ``terrainbuilder``, ``tb``, etc.) are never offered as targets — they are
    map-project work folders, not addons.
  - Folders matching the user's exclude patterns are skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from citadel.core.paths import matches_any
from citadel.core.prefix import find_prefix_files


# Folder names that are never offered as addon build targets.
TERRAIN_WORK_FOLDERS = {
    "source", "sources", "export", "exports",
    "terrainbuilder", "tb", "tb_work",
    "raw", "raws",
    "_temp", "tmp", "temp",
    "build", "_build", "dist",
}


@dataclass
class AddonTarget:
    """A discovered addon ready to be packed."""

    name: str          # folder name, used as PBO file name when no prefix file present
    source: Path       # folder containing the addon files
    has_config: bool   # True if config.cpp exists at root
    has_wrp: bool      # True if any .wrp file exists in tree (terrain)
    prefix_files: list[Path]


def discover_addons(project_root: Path, exclude_patterns: list[str]) -> list[AddonTarget]:
    """Return the build targets for a given project source folder."""
    if not project_root.is_dir():
        return []

    # Case A: project root is a single addon (has config.cpp at root).
    root_config = _has_root_config(project_root)
    if root_config:
        return [_build_target(project_root, exclude_patterns)]

    targets: list[AddonTarget] = []
    for child in sorted(project_root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue
        if child.name.lower() in TERRAIN_WORK_FOLDERS:
            continue
        if matches_any(child.name, exclude_patterns):
            continue
        if not _qualifies_as_addon(child):
            continue
        targets.append(_build_target(child, exclude_patterns))

    return targets


def _qualifies_as_addon(folder: Path) -> bool:
    """A child folder qualifies if it has a config.cpp or a .wrp (terrain)."""
    if _has_root_config(folder):
        return True
    return _has_wrp_anywhere(folder, max_depth=3)


def _has_root_config(folder: Path) -> bool:
    candidate = folder / "config.cpp"
    return candidate.is_file()


def _has_wrp_anywhere(folder: Path, max_depth: int = 3) -> bool:
    """Best-effort recursive search for any .wrp under ``folder``."""
    return _search_extension(folder, ".wrp", max_depth)


_WALK_BUDGET = 25_000  # entries scanned per call before we bail out


def _search_extension(folder: Path, ext: str, max_depth: int) -> bool:
    """Depth-limited search for any file with ``ext`` under ``folder``.

    Returns True as soon as one is found. Bails out after ``_WALK_BUDGET``
    entries so a misclicked root (e.g. ``C:\\``) cannot freeze discovery.
    """
    ext_lower = ext.lower()
    stack: list[tuple[Path, int]] = [(folder, 0)]
    visited = 0
    while stack:
        current, depth = stack.pop()
        try:
            for child in current.iterdir():
                visited += 1
                if visited > _WALK_BUDGET:
                    return False
                if child.is_file() and child.suffix.lower() == ext_lower:
                    return True
                if child.is_dir() and depth + 1 <= max_depth:
                    stack.append((child, depth + 1))
        except OSError:
            continue
    return False


def _build_target(folder: Path, exclude_patterns: list[str]) -> AddonTarget:
    return AddonTarget(
        name=folder.name,
        source=folder,
        has_config=_has_root_config(folder),
        has_wrp=_has_wrp_anywhere(folder),
        prefix_files=find_prefix_files(folder),
    )
