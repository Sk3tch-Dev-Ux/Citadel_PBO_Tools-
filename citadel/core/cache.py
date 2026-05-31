"""Content-fingerprint build cache.

Skips rebuilding addons whose source tree has not changed. Fingerprint includes
file sizes and a fast streaming SHA-1 over the addon's relevant files, so a
file edit that keeps size + mtime identical still invalidates the cache.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from citadel.core.paths import matches_any
from citadel.core.settings import cache_dir


@dataclass(frozen=True)
class CacheKey:
    """Distinct cache slot per addon + build output combination."""

    addon_path: str
    output_path: str

    def filename(self) -> str:
        # Deterministic hashed filename so we don't blow up filesystems with
        # path-ish names.
        key_bytes = f"{self.addon_path}|{self.output_path}".encode("utf-8")
        digest = hashlib.sha1(key_bytes).hexdigest()
        return f"addon_{digest}.json"


def fingerprint_addon(root: Path, exclude_patterns: Iterable[str]) -> str:
    """Compute a content-safe SHA1 fingerprint of an addon's source tree."""
    sha = hashlib.sha1()
    files = _walk_files_for_fingerprint(root, list(exclude_patterns))
    for rel, full in files:
        sha.update(rel.replace("\\", "/").encode("utf-8"))
        sha.update(b":")
        try:
            size = full.stat().st_size
        except OSError:
            size = 0
        sha.update(str(size).encode("ascii"))
        sha.update(b":")
        _hash_file_into(sha, full)
        sha.update(b"\n")
    return sha.hexdigest()


def _walk_files_for_fingerprint(root: Path, patterns: list[str]) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if not matches_any(name, patterns))
        for name in sorted(filenames):
            if matches_any(name, patterns):
                continue
            full = Path(dirpath) / name
            rel = str(full.relative_to(root))
            found.append((rel, full))
    return found


def _hash_file_into(sha: "hashlib._Hash", path: Path, chunk_size: int = 1 << 20) -> None:
    try:
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break
                sha.update(chunk)
    except OSError:
        sha.update(b"<unreadable>")


def is_unchanged(key: CacheKey, fingerprint: str) -> bool:
    path = cache_dir() / key.filename()
    if not path.is_file():
        return False
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and data.get("fingerprint") == fingerprint


def remember(key: CacheKey, fingerprint: str, extras: dict | None = None) -> None:
    payload = {"fingerprint": fingerprint, "addon": key.addon_path, "output": key.output_path}
    if extras:
        payload.update(extras)
    path = cache_dir() / key.filename()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def forget(key: CacheKey) -> None:
    path = cache_dir() / key.filename()
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def clear_all() -> int:
    """Delete every cache record. Returns the number of records removed."""
    count = 0
    for entry in cache_dir().iterdir():
        if entry.is_file() and entry.suffix == ".json":
            try:
                entry.unlink()
                count += 1
            except OSError:
                pass
    return count
