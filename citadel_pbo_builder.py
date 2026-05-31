"""Entry point for Citadel PBO Builder.

Run from source with ``python citadel_pbo_builder.py``; PyInstaller packages
this file into ``Citadel_PBO_Builder.exe``.

The Builder has no drag-and-drop feature, so it always uses plain Tkinter and
never imports tkinterdnd2. This keeps the EXE small and avoids the tkdnd /
Tcl 9 ABI conflict that bites Microsoft Store Python builds.
"""

from __future__ import annotations

import sys
import tkinter as tk


def main() -> int:
    root = tk.Tk()
    from citadel.core.theme import apply_theme
    from citadel.gui.builder_app import BuilderApp

    apply_theme(root)
    app = BuilderApp(parent=root)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
