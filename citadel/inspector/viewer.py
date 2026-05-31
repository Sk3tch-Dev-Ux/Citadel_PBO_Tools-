"""Read-only text viewer for previewing PBO entries.

Supports lightweight C/config-style syntax highlighting for ``.cpp``, ``.hpp``,
``.h``, ``.c``, ``.rvmat``, ``.sqf``, ``.cfg``, and decompiled ``.bin`` text.
Plain text and other formats are shown without highlighting.
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk

from citadel.core import theme


C_LIKE_EXTENSIONS = {".cpp", ".hpp", ".h", ".c", ".rvmat", ".sqf", ".cfg"}


HL_KEYWORDS = {
    "class", "struct", "enum", "if", "else", "while", "for", "switch", "case",
    "default", "break", "continue", "return", "true", "false", "null", "nil",
    "extends", "private", "protected", "public", "static", "const", "auto",
    "new", "delete", "void", "int", "float", "double", "bool", "string",
    "array", "ref", "this", "super", "params", "modded", "scriptModule",
    "registerEntities", "missionScriptModule", "gameLibScriptModule",
}


class TextViewer(tk.Toplevel):
    """A free-floating modal-ish window that displays text with optional highlighting."""

    def __init__(self, parent: tk.Misc, title: str, content: str,
                 file_extension: str = "") -> None:
        super().__init__(parent)
        self.title(title)
        self.configure(bg=theme.VIOLET_DEEP)
        self.geometry("960x720")
        self.minsize(560, 360)

        toolbar = ttk.Frame(self, style="Deep.TFrame")
        toolbar.pack(fill=tk.X, padx=8, pady=(8, 0))
        ttk.Label(toolbar, text=title, style="TitleDeep.TLabel").pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Close", style="Ghost.TButton",
                   command=self.destroy).pack(side=tk.RIGHT)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self._text = tk.Text(body, wrap=tk.NONE,
                              bg=theme.VIOLET_DEEP, fg=theme.TEXT_PRIMARY,
                              insertbackground=theme.PURPLE_BRIGHT,
                              selectbackground=theme.PURPLE_PRIMARY,
                              selectforeground="#ffffff",
                              font=(theme.FONT_MONO, theme.FONT_SIZE_LOG),
                              borderwidth=0, highlightthickness=0)
        self._text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self._text.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self._text.xview)
        hsb.pack(fill=tk.X, padx=8, pady=(0, 8))
        self._text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._configure_tags()
        self._text.insert("1.0", content)
        if file_extension.lower() in C_LIKE_EXTENSIONS or file_extension == "":
            self._apply_highlight()
        self._text.configure(state=tk.DISABLED)

        self.transient(parent)
        self.focus_set()

    def _configure_tags(self) -> None:
        # Syntax highlight palette tuned for Citadel violet-noir background.
        self._text.tag_configure("keyword", foreground=theme.PURPLE_BRIGHT,
                                 font=(theme.FONT_MONO, theme.FONT_SIZE_LOG, "bold"))
        self._text.tag_configure("string", foreground="#7bd88f")
        self._text.tag_configure("number", foreground="#f4c750")
        self._text.tag_configure("comment", foreground="#8b7da8",
                                 font=(theme.FONT_MONO, theme.FONT_SIZE_LOG, "italic"))
        self._text.tag_configure("preprocessor", foreground="#74d3ff")

    def _apply_highlight(self) -> None:
        content = self._text.get("1.0", tk.END)

        # Single-line comments
        for match in re.finditer(r"//[^\n]*", content):
            self._tag_range("comment", match.start(), match.end())
        # Block comments (multi-line) — naive but adequate
        for match in re.finditer(r"/\*.*?\*/", content, flags=re.DOTALL):
            self._tag_range("comment", match.start(), match.end())
        # Strings
        for match in re.finditer(r'"[^"\n]*"', content):
            self._tag_range("string", match.start(), match.end())
        # Numbers
        for match in re.finditer(r"\b\d+(?:\.\d+)?\b", content):
            self._tag_range("number", match.start(), match.end())
        # Preprocessor lines
        for match in re.finditer(r"^\s*#\w+[^\n]*", content, flags=re.MULTILINE):
            self._tag_range("preprocessor", match.start(), match.end())
        # Keywords
        keyword_alt = r"\b(?:" + "|".join(re.escape(k) for k in HL_KEYWORDS) + r")\b"
        for match in re.finditer(keyword_alt, content):
            self._tag_range("keyword", match.start(), match.end())

    def _tag_range(self, tag: str, start_offset: int, end_offset: int) -> None:
        start_index = self._offset_to_index(start_offset)
        end_index = self._offset_to_index(end_offset)
        self._text.tag_add(tag, start_index, end_index)

    def _offset_to_index(self, offset: int) -> str:
        # Tk indexes are 1-based line numbers and 0-based column counts. Convert
        # a string offset by inspecting newlines up to the position.
        return f"1.0+{offset}c"
