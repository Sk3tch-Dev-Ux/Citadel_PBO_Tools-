"""Path utilities shared across Builder and Inspector."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path


def normalize_pbo_path(path: str) -> str:
    """Normalize a PBO-internal path: backslash separators, no leading slash."""
    cleaned = path.replace("/", "\\").strip()
    while cleaned.startswith("\\"):
        cleaned = cleaned[1:]
    return cleaned


def is_safe_relative(target: Path, root: Path) -> bool:
    """Return True if ``target`` resolves inside ``root`` (no parent-folder escape)."""
    try:
        root_resolved = root.resolve()
        target_resolved = target.resolve()
        target_resolved.relative_to(root_resolved)
        return True
    except (ValueError, OSError):
        return False


def matches_any(name: str, patterns: list[str]) -> bool:
    """Case-insensitive fnmatch against multiple patterns."""
    lowered = name.lower()
    for pattern in patterns:
        if fnmatch.fnmatch(lowered, pattern.lower()):
            return True
    return False


def is_excluded(path_within_addon: str, patterns: list[str]) -> bool:
    """Return True if any path segment of the addon-relative path matches an exclude pattern."""
    normalized = path_within_addon.replace("\\", "/")
    parts = normalized.split("/")
    for segment in parts:
        if matches_any(segment, patterns):
            return True
    return matches_any(parts[-1] if parts else normalized, patterns)


def iter_files(root: Path, patterns: list[str] | None = None) -> list[Path]:
    """Walk ``root`` and return files, optionally filtering by exclude patterns."""
    patterns = patterns or []
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place so os.walk skips them entirely.
        dirnames[:] = [name for name in dirnames if not matches_any(name, patterns)]
        for name in filenames:
            if matches_any(name, patterns):
                continue
            found.append(Path(dirpath) / name)
    return found


def human_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
