"""Reusable Tk widgets used by both Builder and Inspector."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from citadel.core import theme


class StatusBadge(ttk.Frame):
    """Pill-shaped status indicator that recolors based on state.

    Visually mirrors the ``.status-badge`` pills in DayzServerController:
    capsule, soft-tinted background, colored text in small caps.
    """

    def __init__(self, parent: tk.Misc, *, initial: str = "Ready") -> None:
        super().__init__(parent, style="Surface.TFrame")
        self._label = tk.Label(self, text=initial.upper(), padx=14, pady=5,
                               font=(theme.FONT_FAMILY, theme.FONT_SIZE_TINY, "bold"),
                               borderwidth=0)
        self._label.pack()
        self.set_state("ready", initial)

    def set_state(self, state: str, text: str | None = None) -> None:
        bg, fg = theme.status_palette(state)
        self._label.configure(bg=bg, fg=fg)
        if text is not None:
            self._label.configure(text=text.upper())


class LogView(ttk.Frame):
    """Severity-aware log widget driven by the Logger broadcast."""

    def __init__(self, parent: tk.Misc, on_filter_change: Callable[[str], None] | None = None) -> None:
        super().__init__(parent)
        self._filter_callback = on_filter_change

        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(toolbar, text="FILTER", style="Header.TLabel").pack(side=tk.LEFT)
        self._filter = tk.StringVar(value="All")
        combo = ttk.Combobox(toolbar, textvariable=self._filter, state="readonly", width=20,
                              values=("All", "Hide INFO", "Warnings + Errors", "Errors Only"))
        combo.pack(side=tk.LEFT, padx=(10, 0))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_filter())

        self._summary = ttk.Label(toolbar, text="", style="Muted.TLabel")
        self._summary.pack(side=tk.RIGHT)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True)
        self._text = tk.Text(body, wrap=tk.NONE, height=18,
                             bg=theme.BG_DEEP, fg=theme.TEXT_PRIMARY,
                             insertbackground=theme.ACCENT_BLUE,
                             selectbackground=theme.ACCENT_BLUE,
                             selectforeground="#0d1218",
                             font=(theme.FONT_MONO, theme.FONT_SIZE_LOG),
                             borderwidth=0, highlightthickness=1,
                             highlightbackground=theme.BORDER,
                             padx=12, pady=10)
        self._text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self._text.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._text.configure(yscrollcommand=vsb.set, state=tk.DISABLED)

        for tag_name, config in theme.log_tag_palette().items():
            self._text.tag_configure(tag_name, **config)

    def _filter_name(self) -> str:
        return {
            "All": "All",
            "Hide INFO": "HideInfo",
            "Warnings + Errors": "WarnError",
            "Errors Only": "ErrorOnly",
        }[self._filter.get()]

    def _on_filter(self) -> None:
        if self._filter_callback is not None:
            self._filter_callback(self._filter_name())

    def current_filter(self) -> str:
        return self._filter_name()

    def append(self, text: str, tag: str = "info") -> None:
        self._text.configure(state=tk.NORMAL)
        self._text.insert(tk.END, text + "\n", tag)
        self._text.see(tk.END)
        self._text.configure(state=tk.DISABLED)

    def replace(self, lines: list[tuple[str, str]]) -> None:
        self._text.configure(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        for text, tag in lines:
            self._text.insert(tk.END, text + "\n", tag)
        self._text.see(tk.END)
        self._text.configure(state=tk.DISABLED)

    def clear(self) -> None:
        self._text.configure(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        self._text.configure(state=tk.DISABLED)

    def set_summary(self, text: str) -> None:
        self._summary.configure(text=text)


class HeaderBar(ttk.Frame):
    """Top app bar with brand title, subtitle, and right-side action slot.

    Styled to match the DayzServerController main header — surface bg, 1px
    bottom separator, generous vertical padding, modest title.
    """

    def __init__(self, parent: tk.Misc, *, title: str, subtitle: str) -> None:
        super().__init__(parent, style="Surface.TFrame")
        inner = ttk.Frame(self, style="Surface.TFrame")
        inner.pack(fill=tk.X, padx=28, pady=18)
        left = ttk.Frame(inner, style="Surface.TFrame")
        left.pack(side=tk.LEFT)
        ttk.Label(left, text=title, style="TitleDeep.TLabel").pack(anchor=tk.W)
        ttk.Label(left, text=subtitle, style="Subtitle.TLabel").pack(anchor=tk.W, pady=(2, 0))
        self.actions = ttk.Frame(inner, style="Surface.TFrame")
        self.actions.pack(side=tk.RIGHT)
        # 1px separator below the bar
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X)


class PathField(ttk.Frame):
    """Label + entry + Browse + Open-folder button row.

    Section label sits above in uppercase muted text. Browse/Open buttons
    are evenly spaced with the standard 8px Citadel rhythm.
    """

    def __init__(self, parent: tk.Misc, label: str,
                 on_browse: Callable[[], str | None],
                 on_open: Callable[[str], None]) -> None:
        super().__init__(parent)
        self._variable = tk.StringVar()
        self._on_open = on_open

        ttk.Label(self, text=label.upper(), style="Header.TLabel").pack(anchor=tk.W)
        row = ttk.Frame(self)
        row.pack(fill=tk.X, pady=(6, 0))
        entry = ttk.Entry(row, textvariable=self._variable)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="Browse", style="TButton",
                   command=lambda: self._handle_browse(on_browse)).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(row, text="Open", style="Ghost.TButton",
                   command=self._handle_open).pack(side=tk.LEFT, padx=(4, 0))

    def _handle_browse(self, callback: Callable[[], str | None]) -> None:
        result = callback()
        if result:
            self._variable.set(result)

    def _handle_open(self) -> None:
        value = self._variable.get().strip()
        if value:
            self._on_open(value)

    def get(self) -> str:
        return self._variable.get().strip()

    def set(self, value: str) -> None:
        self._variable.set(value)

    def variable(self) -> tk.StringVar:
        return self._variable


class CheckboxRow(ttk.Frame):
    """Compact group of named boolean toggles."""

    def __init__(self, parent: tk.Misc, options: dict[str, str], style: str = "TCheckbutton") -> None:
        super().__init__(parent)
        self._vars: dict[str, tk.BooleanVar] = {}
        for index, (key, label) in enumerate(options.items()):
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(self, text=label, variable=var, style=style)
            cb.grid(row=index // 2, column=index % 2, sticky=tk.W, padx=4, pady=2)
            self._vars[key] = var

    def value(self, key: str) -> bool:
        return self._vars[key].get()

    def set_value(self, key: str, value: bool) -> None:
        if key in self._vars:
            self._vars[key].set(bool(value))

    def values(self) -> dict[str, bool]:
        return {k: v.get() for k, v in self._vars.items()}

    def load(self, values: dict[str, bool]) -> None:
        for key, value in values.items():
            self.set_value(key, value)
