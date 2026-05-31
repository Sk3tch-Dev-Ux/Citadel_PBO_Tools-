"""Locate bundled assets in both source-mode and PyInstaller-frozen mode.

When running from source the assets live at ``<repo>/assets/``. When packaged
with PyInstaller they are extracted into ``sys._MEIPASS/assets/`` at runtime.
This module hides that difference behind one resolver.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _bundle_root() -> Path:
    """Return the directory that holds the bundled ``assets/`` folder.

    Frozen EXE: PyInstaller exposes the temp extraction dir as ``sys._MEIPASS``.
    Source mode: walk up from this file's parent to the repo root.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent.parent


def asset_path(*parts: str) -> Path:
    """Build the absolute path of an asset shipped alongside the app."""
    return _bundle_root() / "assets" / Path(*parts)


def icon_path() -> Path | None:
    """Return the Citadel shield ICO if it exists, else ``None``."""
    candidate = asset_path("citadel.ico")
    return candidate if candidate.is_file() else None
