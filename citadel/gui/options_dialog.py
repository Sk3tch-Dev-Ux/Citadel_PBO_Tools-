"""Builder Options dialog — scrollable so it fits small screens."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from citadel.core import dayz_tools, settings, theme


class OptionsDialog(tk.Toplevel):
    """Scrollable settings window with DayZ Tools paths and preflight toggles."""

    def __init__(self, parent: tk.Misc, data: dict, on_save):
        super().__init__(parent)
        self.title("Builder Options")
        self.configure(bg=theme.VIOLET_DEEP)
        self.geometry("760x720")
        self.minsize(620, 520)
        self.transient(parent)
        self._data = data
        self._on_save = on_save

        # Scrollable body
        canvas = tk.Canvas(self, bg=theme.VIOLET_BASE, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0), pady=12)
        vsb.pack(side=tk.LEFT, fill=tk.Y, pady=12)

        scroll_frame = ttk.Frame(canvas)
        scroll_window = canvas.create_window((0, 0), window=scroll_frame, anchor=tk.NW)
        scroll_frame.bind("<Configure>",
                          lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(scroll_window, width=e.width))

        self._build_tools_section(scroll_frame)
        self._build_signing_section(scroll_frame)
        self._build_pipeline_section(scroll_frame)
        self._build_safety_section(scroll_frame)
        self._build_performance_section(scroll_frame)
        self._build_excludes_section(scroll_frame)
        self._build_preflight_section(scroll_frame)
        self._build_binarize_addons_section(scroll_frame)

        # Footer
        footer = ttk.Frame(self, style="Deep.TFrame")
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 12), padx=12)
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(footer, text="Save", style="Primary.TButton",
                   command=self._save).pack(side=tk.RIGHT, padx=8)

        # Mouse wheel scroll
        def on_mousewheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        self.protocol("WM_DELETE_WINDOW", self._cleanup)

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------
    def _section(self, parent: tk.Misc, title: str) -> ttk.Labelframe:
        frame = ttk.Labelframe(parent, text=title, style="TLabelframe")
        frame.pack(fill=tk.X, padx=8, pady=8)
        return frame

    def _build_tools_section(self, parent: tk.Misc) -> None:
        frame = self._section(parent, "DayZ Tools paths")
        self._tool_vars: dict[str, tk.StringVar] = {}
        for key, label in (
            ("binarize_exe", "Binarize.exe"),
            ("cfgconvert_exe", "CfgConvert.exe"),
            ("imagetopaa_exe", "ImageToPAA.exe"),
            ("dssignfile_exe", "DSSignFile.exe"),
        ):
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=label, width=18).pack(side=tk.LEFT)
            var = tk.StringVar(value=self._data.get(key, ""))
            self._tool_vars[key] = var
            ttk.Entry(row, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
            ttk.Button(row, text="Browse...",
                       command=lambda v=var, name=label: self._browse_exe(v, name)
                       ).pack(side=tk.LEFT)
        action = ttk.Frame(frame)
        action.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(action, text="Auto-detect from Steam", style="Secondary.TButton",
                   command=self._auto_detect).pack(side=tk.LEFT)
        self._detect_status = ttk.Label(action, text="", style="Muted.TLabel")
        self._detect_status.pack(side=tk.LEFT, padx=8)

    def _build_signing_section(self, parent: tk.Misc) -> None:
        frame = self._section(parent, "Signing")
        row = ttk.Frame(frame)
        row.pack(fill=tk.X)
        ttk.Label(row, text=".biprivatekey", width=18).pack(side=tk.LEFT)
        self._key_var = tk.StringVar(value=self._data.get("private_key", ""))
        ttk.Entry(row, textvariable=self._key_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row, text="Browse...",
                   command=lambda: self._browse_key()).pack(side=tk.LEFT)
        ttk.Label(frame, text="Never share .biprivatekey — only distribute the matching .bikey.",
                  style="Muted.TLabel").pack(anchor=tk.W, pady=(6, 0))

    def _build_pipeline_section(self, parent: tk.Misc) -> None:
        frame = self._section(parent, "Pipeline")
        self._pipeline_vars: dict[str, tk.BooleanVar] = {}
        pipeline = self._data.get("pipeline", {})
        options = {
            "binarize_p3d": "Binarize .p3d files",
            "binarize_wrp": "Binarize .wrp terrain files",
            "convert_cpp_to_bin": "Convert config.cpp -> config.bin",
            "update_paa": "Update .paa from newer .png/.tga sources",
            "sign_pbos": "Sign PBOs",
            "copy_bikey": "Copy .bikey to Keys folder",
            "preflight_before_build": "Run Preflight before every build",
        }
        for index, (key, label) in enumerate(options.items()):
            var = tk.BooleanVar(value=bool(pipeline.get(key, False)))
            self._pipeline_vars[key] = var
            ttk.Checkbutton(frame, text=label, variable=var).grid(
                row=index // 2, column=index % 2, sticky=tk.W, padx=4, pady=2)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

    def _build_safety_section(self, parent: tk.Misc) -> None:
        frame = self._section(parent, "Safety")
        self._safety_vars: dict[str, tk.BooleanVar] = {}
        safety = self._data.get("safety", {})
        options = {
            "skip_unchanged": "Skip unchanged addons (build cache)",
            "force_rebuild": "Force rebuild (ignore cache)",
            "safe_publish": "Safe publish (backup before replace)",
            "verify_outputs": "Verify outputs after each step",
            "content_safe_cache": "Content-safe cache checks",
        }
        for index, (key, label) in enumerate(options.items()):
            var = tk.BooleanVar(value=bool(safety.get(key, False)))
            self._safety_vars[key] = var
            ttk.Checkbutton(frame, text=label, variable=var).grid(
                row=index // 2, column=index % 2, sticky=tk.W, padx=4, pady=2)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

    def _build_performance_section(self, parent: tk.Misc) -> None:
        frame = self._section(parent, "Performance")
        perf = self._data.get("performance", {})
        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Binarize workers (0 = auto)", width=28).pack(side=tk.LEFT)
        self._workers_var = tk.IntVar(value=int(perf.get("binarize_workers", 0)))
        ttk.Spinbox(row, from_=0, to=64, textvariable=self._workers_var, width=8).pack(side=tk.LEFT)

        self._batch_log_var = tk.BooleanVar(value=bool(perf.get("batch_log_updates", True)))
        ttk.Checkbutton(frame, text="Batch GUI log updates (smoother UI)",
                        variable=self._batch_log_var).pack(anchor=tk.W, pady=2)

    def _build_excludes_section(self, parent: tk.Misc) -> None:
        frame = self._section(parent, "Exclude patterns (one per line)")
        self._excludes_text = tk.Text(frame, height=6,
                                       bg=theme.VIOLET_FIELD, fg=theme.TEXT_PRIMARY,
                                       insertbackground=theme.PURPLE_PRIMARY,
                                       borderwidth=0, highlightthickness=1,
                                       highlightcolor=theme.PURPLE_PRIMARY,
                                       highlightbackground=theme.VIOLET_BORDER,
                                       font=(theme.FONT_MONO, theme.FONT_SIZE_BASE))
        self._excludes_text.pack(fill=tk.X, pady=4)
        existing = self._data.get("exclude_patterns", [])
        self._excludes_text.insert("1.0", "\n".join(existing))

    def _build_preflight_section(self, parent: tk.Misc) -> None:
        frame = self._section(parent, "Preflight checks")
        self._preflight_vars: dict[str, tk.BooleanVar] = {}
        pre = self._data.get("preflight", {})
        options = {
            "required_addons_hints": "requiredAddons hints",
            "texture_freshness": "Texture freshness",
            "risky_path_names": "Risky path names",
            "case_conflicts": "Case-only path conflicts",
            "p3d_internal_scan": "P3D internal scan",
            "terrain_wrp_checks": "Terrain / WRP checks",
            "terrain_navmesh_checks": "Terrain navmesh checks",
            "wrp_internal_scan": "WRP internal scan (slower)",
            "terrain_source_export_warnings": "Terrain source/export warnings",
            "terrain_layer_checks": "Terrain layer checks",
            "map_2d_config_checks": "2D map config checks",
            "terrain_size_checks": "Terrain size checks",
            "script_checks": "Script checks (modded class etc.)",
        }
        for index, (key, label) in enumerate(options.items()):
            var = tk.BooleanVar(value=bool(pre.get(key, False)))
            self._preflight_vars[key] = var
            ttk.Checkbutton(frame, text=label, variable=var).grid(
                row=index // 2, column=index % 2, sticky=tk.W, padx=4, pady=2)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

    def _build_binarize_addons_section(self, parent: tk.Misc) -> None:
        frame = self._section(parent, "Binarize addon scan folders (terrain dependencies; one per line)")
        self._binarize_addons_text = tk.Text(frame, height=4,
                                              bg=theme.VIOLET_FIELD, fg=theme.TEXT_PRIMARY,
                                              insertbackground=theme.PURPLE_PRIMARY,
                                              borderwidth=0, highlightthickness=1,
                                              highlightcolor=theme.PURPLE_PRIMARY,
                                              highlightbackground=theme.VIOLET_BORDER,
                                              font=(theme.FONT_MONO, theme.FONT_SIZE_BASE))
        self._binarize_addons_text.pack(fill=tk.X, pady=4)
        existing = self._data.get("binarize_addon_folders", [])
        self._binarize_addons_text.insert("1.0", "\n".join(existing))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _browse_exe(self, var: tk.StringVar, label: str) -> None:
        path = filedialog.askopenfilename(title=f"Locate {label}",
                                          filetypes=[(label, label), ("All", "*.*")])
        if path:
            var.set(path)

    def _browse_key(self) -> None:
        path = filedialog.askopenfilename(title="Locate .biprivatekey",
                                          filetypes=[("Private key", "*.biprivatekey"),
                                                     ("All files", "*.*")])
        if path:
            self._key_var.set(path)

    def _auto_detect(self) -> None:
        paths = dayz_tools.detect()
        any_found = False
        for key, value in paths.as_settings_dict().items():
            if value:
                self._tool_vars[key].set(value)
                any_found = True
        if paths.root:
            self._detect_status.configure(text=f"Detected at: {paths.root}")
        elif not any_found:
            self._detect_status.configure(text="No DayZ Tools install found in Steam libraries.")

    def _save(self) -> None:
        # DayZ tool paths
        for key, var in self._tool_vars.items():
            self._data[key] = var.get().strip()
        self._data["private_key"] = self._key_var.get().strip()

        # Pipeline / safety / performance
        self._data["pipeline"] = {k: v.get() for k, v in self._pipeline_vars.items()}
        self._data["safety"] = {k: v.get() for k, v in self._safety_vars.items()}
        self._data["performance"] = {
            "binarize_workers": int(self._workers_var.get()),
            "batch_log_updates": bool(self._batch_log_var.get()),
        }

        # Excludes
        excludes_text = self._excludes_text.get("1.0", tk.END)
        self._data["exclude_patterns"] = [line.strip() for line in excludes_text.splitlines() if line.strip()]

        # Preflight
        self._data["preflight"] = {k: v.get() for k, v in self._preflight_vars.items()}

        # Binarize addon folders
        bin_text = self._binarize_addons_text.get("1.0", tk.END)
        self._data["binarize_addon_folders"] = [line.strip() for line in bin_text.splitlines() if line.strip()]

        settings.save_builder_settings(self._data)
        self._on_save(self._data)
        self._cleanup()

    def _cleanup(self) -> None:
        try:
            self.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass
        self.destroy()
