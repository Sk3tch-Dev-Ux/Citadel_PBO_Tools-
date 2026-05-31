"""Entry point for Citadel PBO Inspector.

Run from source with ``python citadel_pbo_inspector.py``. PyInstaller packages
this file into ``Citadel_PBO_Inspector.exe``.

We attempt to use ``tkinterdnd2`` so the user can drop ``.pbo`` files into the
window, but fall back to plain Tkinter if the bundled ``tkdnd`` DLL is
incompatible with the Python interpreter's Tcl/Tk runtime (a known issue with
the Microsoft Store Python 3.13 which ships Tcl/Tk 9.x while ``tkinterdnd2``
ships a tkdnd built for Tcl/Tk 8.6). In the fallback path, browsing and
Reload still work — only the drop-into-window shortcut is unavailable.
"""

from __future__ import annotations

import sys
import tkinter as tk


def _make_root() -> tk.Tk:
    try:
        from tkinterdnd2 import TkinterDnD
        return TkinterDnD.Tk()
    except Exception:
        # tkdnd DLL refused to load (ABI mismatch, missing, or non-Windows).
        # Drop-into-window is degraded gracefully — the rest of the app is
        # unaffected.
        return tk.Tk()


def main() -> int:
    root = _make_root()
    from citadel.core.theme import apply_theme
    from citadel.gui.inspector_app import InspectorApp

    apply_theme(root)
    app = InspectorApp(parent=root)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
