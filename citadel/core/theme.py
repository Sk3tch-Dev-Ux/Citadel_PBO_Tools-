"""Citadel theme — shared with the DayzServerController palette.

A cool blue-gray dark theme with blue as the primary accent and a touch of
Citadel purple reserved for brand moments. Tuned for a modern, professional
look in Tkinter that does not feel like a Windows-98 application.

Palette taken from DayzServerController's ``global.css`` so the Citadel
desktop tools and the DSC web console share a single visual language.
"""

from __future__ import annotations

from tkinter import ttk
import tkinter as tk


# ---------------------------------------------------------------------------
# Background ramp (deepest -> elevated)
# ---------------------------------------------------------------------------
BG_DEEP = "#1b1e24"        # outermost chrome / page background
BG_SURFACE = "#22262e"     # header bar, sidebar
BG_CARD = "#2a2e37"        # raised panels and cards
BG_ELEVATED = "#323843"    # entry fields, hover surface
BORDER = "#3c4250"         # 1px dividers
BORDER_ACTIVE = "#515a6b"  # focused / hovered border

# Text ramp
TEXT_PRIMARY = "#dce0e8"
TEXT_SECONDARY = "#9ba3b0"
TEXT_MUTED = "#7d8595"
TEXT_DIM = "#5f6779"

# Accents (semantic)
ACCENT_BLUE = "#6cb4f0"
ACCENT_BLUE_DIM = "#539be0"
ACCENT_GREEN = "#5cb85c"
ACCENT_GREEN_DIM = "#4cae4c"
ACCENT_RED = "#e06c75"
ACCENT_RED_DIM = "#c85a63"
ACCENT_YELLOW = "#e5c07b"
ACCENT_ORANGE = "#e0976b"

# Citadel brand purple — used sparingly for brand moments
ACCENT_PURPLE = "#c49bff"

# ---------------------------------------------------------------------------
# Legacy aliases retained so existing modules keep importing without churn.
# These point at the new ramp.
# ---------------------------------------------------------------------------
VIOLET_DEEP = BG_DEEP
VIOLET_BASE = BG_SURFACE
VIOLET_PANEL = BG_CARD
VIOLET_FIELD = BG_ELEVATED
VIOLET_BORDER = BORDER
PURPLE_PRIMARY = ACCENT_BLUE          # primary CTA color is now blue
PURPLE_BRIGHT = ACCENT_BLUE           # hover/highlight
PURPLE_DEEP = ACCENT_BLUE_DIM         # pressed
PURPLE_DIM = ACCENT_BLUE_DIM
PURPLE_GLOW = ACCENT_PURPLE

# Log severity colors (kept legible on BG_DEEP)
LOG_INFO = TEXT_PRIMARY
LOG_WARN = ACCENT_YELLOW
LOG_ERROR = ACCENT_RED
LOG_SUCCESS = ACCENT_GREEN
LOG_SECTION = ACCENT_BLUE
LOG_TOOL = ACCENT_PURPLE

# Status badge palettes (bg, fg)
STATUS_READY = (BG_ELEVATED, TEXT_SECONDARY)
STATUS_BUILDING = ("#3a3520", ACCENT_YELLOW)
STATUS_PREFLIGHT = ("#1f2f44", ACCENT_BLUE)
STATUS_DONE = ("#1f3024", ACCENT_GREEN)
STATUS_ERROR = ("#3a1f23", ACCENT_RED)

# Typography
FONT_FAMILY = "Segoe UI"
FONT_FAMILY_DISPLAY = "Segoe UI Variable"  # falls back to Segoe UI if absent
FONT_MONO = "Consolas"

FONT_SIZE_TINY = 9
FONT_SIZE_BASE = 10
FONT_SIZE_BODY = 11
FONT_SIZE_HEADER = 12
FONT_SIZE_TITLE = 18
FONT_SIZE_LOG = 10


# ---------------------------------------------------------------------------
# Theme application
# ---------------------------------------------------------------------------

def apply_theme(root: tk.Misc) -> ttk.Style:
    """Apply the Citadel/DSC theme to ``root`` and return the configured style."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=BG_DEEP)

    base_font = (FONT_FAMILY, FONT_SIZE_BASE)
    body_font = (FONT_FAMILY, FONT_SIZE_BODY)
    bold_font = (FONT_FAMILY, FONT_SIZE_BODY, "bold")
    header_font = (FONT_FAMILY, FONT_SIZE_HEADER, "bold")
    section_font = (FONT_FAMILY, FONT_SIZE_TINY, "bold")  # used like uppercase section labels
    title_font = (FONT_FAMILY, FONT_SIZE_TITLE, "bold")
    subtitle_font = (FONT_FAMILY, FONT_SIZE_BODY)

    # ----- Defaults -----
    style.configure(".",
                    background=BG_DEEP,
                    foreground=TEXT_PRIMARY,
                    fieldbackground=BG_ELEVATED,
                    bordercolor=BORDER,
                    lightcolor=BORDER,
                    darkcolor=BORDER,
                    troughcolor=BG_DEEP,
                    focuscolor=ACCENT_BLUE,
                    font=body_font)

    # ----- Frames -----
    style.configure("TFrame", background=BG_DEEP)
    style.configure("Surface.TFrame", background=BG_SURFACE)
    style.configure("Card.TFrame", background=BG_CARD)
    style.configure("Panel.TFrame", background=BG_CARD)   # legacy alias
    style.configure("Deep.TFrame", background=BG_SURFACE) # legacy alias

    # ----- Labels -----
    style.configure("TLabel", background=BG_DEEP, foreground=TEXT_PRIMARY, font=body_font)
    style.configure("Card.TLabel", background=BG_CARD, foreground=TEXT_PRIMARY, font=body_font)
    style.configure("Panel.TLabel", background=BG_CARD, foreground=TEXT_PRIMARY, font=body_font)
    style.configure("Surface.TLabel", background=BG_SURFACE, foreground=TEXT_PRIMARY, font=body_font)
    style.configure("Muted.TLabel", background=BG_DEEP, foreground=TEXT_MUTED, font=body_font)
    style.configure("MutedSurface.TLabel", background=BG_SURFACE, foreground=TEXT_MUTED, font=body_font)
    style.configure("MutedPanel.TLabel", background=BG_CARD, foreground=TEXT_MUTED, font=body_font)
    style.configure("Secondary.TLabel", background=BG_DEEP, foreground=TEXT_SECONDARY, font=body_font)

    # Section header — small caps style for "PROJECT SOURCE", "ADDONS", etc.
    style.configure("Header.TLabel", background=BG_DEEP, foreground=TEXT_MUTED, font=section_font)
    style.configure("HeaderSurface.TLabel", background=BG_SURFACE, foreground=TEXT_MUTED, font=section_font)
    style.configure("HeaderCard.TLabel", background=BG_CARD, foreground=TEXT_MUTED, font=section_font)

    # Title styles — big bold headers
    style.configure("Title.TLabel", background=BG_DEEP, foreground=TEXT_PRIMARY, font=title_font)
    style.configure("TitleDeep.TLabel", background=BG_SURFACE, foreground=TEXT_PRIMARY, font=title_font)
    style.configure("Subtitle.TLabel", background=BG_SURFACE, foreground=TEXT_MUTED, font=subtitle_font)

    # ----- Buttons -----
    style.configure("TButton",
                    background=BG_ELEVATED,
                    foreground=TEXT_PRIMARY,
                    bordercolor=BORDER,
                    focuscolor=ACCENT_BLUE,
                    padding=(14, 8),
                    relief="flat",
                    font=body_font)
    style.map("TButton",
              background=[("active", BG_CARD), ("pressed", BG_DEEP), ("disabled", BG_DEEP)],
              foreground=[("disabled", TEXT_DIM)],
              bordercolor=[("focus", ACCENT_BLUE), ("active", BORDER_ACTIVE)])

    # Primary — blue CTA
    style.configure("Primary.TButton",
                    background=ACCENT_BLUE,
                    foreground="#0d1218",
                    bordercolor=ACCENT_BLUE_DIM,
                    padding=(20, 10),
                    relief="flat",
                    font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"))
    style.map("Primary.TButton",
              background=[("active", ACCENT_BLUE_DIM), ("pressed", ACCENT_BLUE_DIM), ("disabled", BG_CARD)],
              foreground=[("disabled", TEXT_DIM)])

    # Secondary — outlined blue
    style.configure("Secondary.TButton",
                    background=BG_ELEVATED,
                    foreground=ACCENT_BLUE,
                    bordercolor=ACCENT_BLUE,
                    padding=(16, 9),
                    relief="flat",
                    font=bold_font)
    style.map("Secondary.TButton",
              background=[("active", BG_CARD), ("pressed", BG_DEEP)],
              foreground=[("disabled", TEXT_DIM)])

    # Ghost — borderless minimal chrome
    style.configure("Ghost.TButton",
                    background=BG_DEEP,
                    foreground=TEXT_SECONDARY,
                    bordercolor=BG_DEEP,
                    padding=(10, 6),
                    relief="flat",
                    font=body_font)
    style.map("Ghost.TButton",
              background=[("active", BG_CARD)],
              foreground=[("active", TEXT_PRIMARY)])

    # Danger
    style.configure("Danger.TButton",
                    background=ACCENT_RED,
                    foreground="#0d1218",
                    bordercolor=ACCENT_RED_DIM,
                    padding=(16, 9),
                    relief="flat",
                    font=bold_font)
    style.map("Danger.TButton",
              background=[("active", ACCENT_RED_DIM), ("pressed", ACCENT_RED_DIM)])

    # ----- Entry -----
    style.configure("TEntry",
                    fieldbackground=BG_ELEVATED,
                    foreground=TEXT_PRIMARY,
                    insertcolor=ACCENT_BLUE,
                    bordercolor=BORDER,
                    lightcolor=BORDER,
                    darkcolor=BORDER,
                    relief="flat",
                    padding=8)
    style.map("TEntry",
              bordercolor=[("focus", ACCENT_BLUE)],
              lightcolor=[("focus", ACCENT_BLUE)],
              darkcolor=[("focus", ACCENT_BLUE)])

    # ----- Combobox -----
    style.configure("TCombobox",
                    fieldbackground=BG_ELEVATED,
                    background=BG_CARD,
                    foreground=TEXT_PRIMARY,
                    arrowcolor=TEXT_SECONDARY,
                    bordercolor=BORDER,
                    relief="flat",
                    padding=6)
    style.map("TCombobox",
              fieldbackground=[("readonly", BG_ELEVATED)],
              foreground=[("readonly", TEXT_PRIMARY)],
              bordercolor=[("focus", ACCENT_BLUE)],
              arrowcolor=[("active", TEXT_PRIMARY)])
    root.option_add("*TCombobox*Listbox*Background", BG_ELEVATED)
    root.option_add("*TCombobox*Listbox*Foreground", TEXT_PRIMARY)
    root.option_add("*TCombobox*Listbox*selectBackground", ACCENT_BLUE)
    root.option_add("*TCombobox*Listbox*selectForeground", "#0d1218")
    root.option_add("*TCombobox*Listbox*Font", body_font)

    # ----- Checkbutton -----
    style.configure("TCheckbutton",
                    background=BG_DEEP,
                    foreground=TEXT_PRIMARY,
                    indicatorcolor=BG_ELEVATED,
                    focuscolor=ACCENT_BLUE,
                    padding=4,
                    font=body_font)
    style.map("TCheckbutton",
              indicatorcolor=[("selected", ACCENT_BLUE), ("pressed", ACCENT_BLUE_DIM)],
              background=[("active", BG_DEEP)],
              foreground=[("disabled", TEXT_DIM)])

    style.configure("Card.TCheckbutton",
                    background=BG_CARD,
                    foreground=TEXT_PRIMARY,
                    indicatorcolor=BG_ELEVATED,
                    padding=4,
                    font=body_font)
    style.map("Card.TCheckbutton",
              indicatorcolor=[("selected", ACCENT_BLUE)],
              background=[("active", BG_CARD)])
    # Legacy alias
    style.configure("Panel.TCheckbutton",
                    background=BG_CARD,
                    foreground=TEXT_PRIMARY,
                    indicatorcolor=BG_ELEVATED,
                    padding=4,
                    font=body_font)
    style.map("Panel.TCheckbutton",
              indicatorcolor=[("selected", ACCENT_BLUE)],
              background=[("active", BG_CARD)])

    style.configure("TRadiobutton",
                    background=BG_DEEP,
                    foreground=TEXT_PRIMARY,
                    indicatorcolor=BG_ELEVATED,
                    padding=4,
                    font=body_font)
    style.map("TRadiobutton", indicatorcolor=[("selected", ACCENT_BLUE)])

    # ----- LabelFrame -----
    style.configure("TLabelframe",
                    background=BG_DEEP,
                    bordercolor=BORDER,
                    lightcolor=BORDER,
                    darkcolor=BORDER,
                    relief="solid",
                    padding=14)
    style.configure("TLabelframe.Label",
                    background=BG_DEEP,
                    foreground=TEXT_MUTED,
                    font=section_font)

    style.configure("Card.TLabelframe",
                    background=BG_CARD,
                    bordercolor=BORDER,
                    relief="solid",
                    padding=14)
    style.configure("Card.TLabelframe.Label",
                    background=BG_CARD,
                    foreground=TEXT_MUTED,
                    font=section_font)
    # Legacy alias
    style.configure("Panel.TLabelframe",
                    background=BG_CARD,
                    bordercolor=BORDER,
                    relief="solid",
                    padding=14)
    style.configure("Panel.TLabelframe.Label",
                    background=BG_CARD,
                    foreground=TEXT_MUTED,
                    font=section_font)

    # ----- Notebook -----
    style.configure("TNotebook", background=BG_SURFACE, bordercolor=BORDER,
                    tabmargins=(8, 6, 8, 0))
    style.configure("TNotebook.Tab",
                    background=BG_SURFACE,
                    foreground=TEXT_MUTED,
                    bordercolor=BORDER,
                    padding=(18, 8),
                    font=bold_font)
    style.map("TNotebook.Tab",
              background=[("selected", BG_ELEVATED), ("active", BG_CARD)],
              foreground=[("selected", ACCENT_BLUE), ("active", TEXT_PRIMARY)])

    # ----- Treeview -----
    style.configure("Treeview",
                    background=BG_CARD,
                    fieldbackground=BG_CARD,
                    foreground=TEXT_PRIMARY,
                    bordercolor=BORDER,
                    rowheight=26,
                    relief="flat",
                    font=body_font)
    style.configure("Treeview.Heading",
                    background=BG_SURFACE,
                    foreground=TEXT_MUTED,
                    bordercolor=BORDER,
                    relief="flat",
                    font=section_font,
                    padding=(10, 6))
    style.map("Treeview",
              background=[("selected", ACCENT_BLUE)],
              foreground=[("selected", "#0d1218")])
    style.map("Treeview.Heading",
              background=[("active", BG_ELEVATED)],
              foreground=[("active", TEXT_PRIMARY)])

    # ----- Progressbar -----
    style.configure("Horizontal.TProgressbar",
                    background=ACCENT_BLUE,
                    troughcolor=BG_ELEVATED,
                    bordercolor=BG_ELEVATED,
                    lightcolor=ACCENT_BLUE,
                    darkcolor=ACCENT_BLUE_DIM)

    # ----- Scrollbar -----
    style.configure("Vertical.TScrollbar",
                    background=BG_CARD,
                    troughcolor=BG_DEEP,
                    bordercolor=BG_DEEP,
                    arrowcolor=TEXT_SECONDARY,
                    relief="flat")
    style.map("Vertical.TScrollbar",
              background=[("active", BG_ELEVATED), ("pressed", BORDER_ACTIVE)],
              arrowcolor=[("active", TEXT_PRIMARY)])
    style.configure("Horizontal.TScrollbar",
                    background=BG_CARD,
                    troughcolor=BG_DEEP,
                    bordercolor=BG_DEEP,
                    arrowcolor=TEXT_SECONDARY,
                    relief="flat")
    style.map("Horizontal.TScrollbar",
              background=[("active", BG_ELEVATED)],
              arrowcolor=[("active", TEXT_PRIMARY)])

    # ----- Separator -----
    style.configure("TSeparator", background=BORDER)

    # ----- Spinbox -----
    style.configure("TSpinbox",
                    fieldbackground=BG_ELEVATED,
                    foreground=TEXT_PRIMARY,
                    bordercolor=BORDER,
                    arrowcolor=TEXT_SECONDARY,
                    relief="flat",
                    padding=6)

    return style


def status_palette(state: str) -> tuple[str, str]:
    state = (state or "").lower()
    return {
        "ready": STATUS_READY,
        "building": STATUS_BUILDING,
        "preflight": STATUS_PREFLIGHT,
        "done": STATUS_DONE,
        "error": STATUS_ERROR,
    }.get(state, STATUS_READY)


def log_tag_palette() -> dict[str, dict[str, str]]:
    return {
        "info": {"foreground": LOG_INFO},
        "warn": {"foreground": LOG_WARN},
        "error": {"foreground": LOG_ERROR},
        "success": {"foreground": LOG_SUCCESS},
        "section": {"foreground": LOG_SECTION,
                    "font": (FONT_MONO, FONT_SIZE_LOG, "bold")},
        "tool": {"foreground": LOG_TOOL},
    }
