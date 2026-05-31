"""Citadel PBO Builder main window."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from citadel.builder import discovery, pipeline, preflight, presets
from citadel.core import assets, cache, dayz_tools, settings, theme
from citadel.core.log import Logger, Severity, filtered
from citadel.gui.options_dialog import OptionsDialog
from citadel.gui.widgets import HeaderBar, LogView, PathField, StatusBadge
from citadel_version import VERSION_STRING, builder_title


class BuilderApp:
    """Main controller for the Builder GUI."""

    def __init__(self, parent: tk.Tk | None = None) -> None:
        self._owns_root = parent is None
        self.root = parent or tk.Tk()
        if self._owns_root:
            theme.apply_theme(self.root)
        self.root.title(builder_title())
        self.root.minsize(1024, 720)
        _apply_window_icon(self.root)

        self.settings = settings.load_builder_settings()
        self._apply_window_geometry()

        self.logger = Logger()
        self.cancel_token: pipeline.CancelToken | None = None
        self._build_thread: threading.Thread | None = None

        # Addon discovery state. A monotonic counter rejects stale results when
        # the user types fast or browses repeatedly; the debounce id lets us
        # cancel a queued scan when a newer change comes in.
        self._discovered_targets: list[discovery.AddonTarget] = []
        self._discovery_seq = 0
        self._discovery_after_id: str | None = None

        self._build_ui()
        self._wire_logger()
        self._refresh_addons()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        header = HeaderBar(self.root,
                           title="Citadel PBO Builder",
                           subtitle=f"v{VERSION_STRING}  -  Pack, binarize, sign, and ship DayZ addons")
        header.pack(fill=tk.X)
        ttk.Button(header.actions, text="About", style="Ghost.TButton",
                   command=self._show_about).pack(side=tk.RIGHT, padx=4)
        ttk.Button(header.actions, text="Options", style="Secondary.TButton",
                   command=self._show_options).pack(side=tk.RIGHT, padx=4)

        # Top: paths + presets
        top = ttk.Frame(self.root)
        top.pack(fill=tk.X, padx=28, pady=(20, 8))

        self._source_field = PathField(
            top, "Project Source",
            on_browse=lambda: self._pick_dir(self.settings.get("project_source", ""), "Select project source"),
            on_open=self._open_in_explorer,
        )
        self._source_field.pack(fill=tk.X, pady=(0, 8))
        self._source_field.set(self.settings.get("project_source", ""))
        self._source_field.variable().trace_add("write", lambda *_: self._on_source_changed())

        source_presets_row = ttk.Frame(top)
        source_presets_row.pack(fill=tk.X, pady=(0, 16))
        ttk.Label(source_presets_row, text="PRESETS", style="Header.TLabel").pack(side=tk.LEFT)
        self._source_preset_var = tk.StringVar()
        self._source_preset_combo = ttk.Combobox(source_presets_row, textvariable=self._source_preset_var,
                                                  state="readonly", width=32)
        self._source_preset_combo.pack(side=tk.LEFT, padx=(10, 8))
        self._source_preset_combo.bind("<<ComboboxSelected>>",
                                        lambda _e: self._load_preset("source", self._source_preset_var.get()))
        ttk.Button(source_presets_row, text="Save", style="Ghost.TButton",
                   command=lambda: self._save_preset_dialog("source")).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(source_presets_row, text="Delete", style="Ghost.TButton",
                   command=lambda: self._delete_preset_dialog("source")).pack(side=tk.LEFT)

        self._output_field = PathField(
            top, "Build Output",
            on_browse=lambda: self._pick_dir(self.settings.get("build_output", ""), "Select build output"),
            on_open=self._open_in_explorer,
        )
        self._output_field.pack(fill=tk.X, pady=(0, 8))
        self._output_field.set(self.settings.get("build_output", ""))

        output_presets_row = ttk.Frame(top)
        output_presets_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(output_presets_row, text="PRESETS", style="Header.TLabel").pack(side=tk.LEFT)
        self._output_preset_var = tk.StringVar()
        self._output_preset_combo = ttk.Combobox(output_presets_row, textvariable=self._output_preset_var,
                                                  state="readonly", width=32)
        self._output_preset_combo.pack(side=tk.LEFT, padx=(10, 8))
        self._output_preset_combo.bind("<<ComboboxSelected>>",
                                        lambda _e: self._load_preset("output", self._output_preset_var.get()))
        ttk.Button(output_presets_row, text="Save", style="Ghost.TButton",
                   command=lambda: self._save_preset_dialog("output")).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(output_presets_row, text="Delete", style="Ghost.TButton",
                   command=lambda: self._delete_preset_dialog("output")).pack(side=tk.LEFT)

        # Body: addon list left, controls/log right
        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, padx=28, pady=(8, 20))

        # Addons list
        addon_frame = ttk.Labelframe(body, text="ADDONS", style="TLabelframe")
        addon_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)
        addon_inner = ttk.Frame(addon_frame)
        addon_inner.pack(fill=tk.BOTH, expand=True)
        self._addon_list = tk.Listbox(addon_inner, selectmode=tk.EXTENDED, width=36, height=20,
                                       bg=theme.BG_ELEVATED, fg=theme.TEXT_PRIMARY,
                                       selectbackground=theme.ACCENT_BLUE,
                                       selectforeground="#0d1218",
                                       borderwidth=0, highlightthickness=0,
                                       activestyle="none",
                                       font=(theme.FONT_FAMILY, theme.FONT_SIZE_BODY))
        self._addon_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        addon_vsb = ttk.Scrollbar(addon_inner, orient=tk.VERTICAL, command=self._addon_list.yview)
        addon_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._addon_list.configure(yscrollcommand=addon_vsb.set)

        addon_actions = ttk.Frame(addon_frame)
        addon_actions.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(addon_actions, text="Select all", style="Ghost.TButton",
                   command=lambda: self._addon_list.selection_set(0, tk.END)).pack(side=tk.LEFT)
        ttk.Button(addon_actions, text="Clear", style="Ghost.TButton",
                   command=lambda: self._addon_list.selection_clear(0, tk.END)).pack(side=tk.LEFT, padx=4)
        ttk.Button(addon_actions, text="Refresh", style="Ghost.TButton",
                   command=self._refresh_addons).pack(side=tk.RIGHT)

        # Right side: status, action buttons, log
        right = ttk.Frame(body)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(20, 0))

        # Status badge + progress
        status_row = ttk.Frame(right)
        status_row.pack(fill=tk.X)
        ttk.Label(status_row, text="STATUS", style="Header.TLabel").pack(side=tk.LEFT)
        self.status_badge = StatusBadge(status_row)
        self.status_badge.pack(side=tk.LEFT, padx=(10, 12))
        self._status_text = tk.StringVar(value="Idle")
        ttk.Label(status_row, textvariable=self._status_text, style="Muted.TLabel").pack(side=tk.LEFT)

        self._progress = ttk.Progressbar(right, mode="determinate", maximum=100)
        self._progress.pack(fill=tk.X, pady=(12, 16))

        # Action buttons
        actions = ttk.Frame(right)
        actions.pack(fill=tk.X, pady=(0, 16))
        self._build_btn = ttk.Button(actions, text="Build PBOs", style="Primary.TButton",
                                      command=self._start_build)
        self._build_btn.pack(side=tk.LEFT)
        self._preflight_btn = ttk.Button(actions, text="Preflight", style="Secondary.TButton",
                                          command=self._start_preflight)
        self._preflight_btn.pack(side=tk.LEFT, padx=10)
        self._cancel_btn = ttk.Button(actions, text="Cancel", style="TButton",
                                       command=self._cancel_build, state=tk.DISABLED)
        self._cancel_btn.pack(side=tk.LEFT)
        ttk.Button(actions, text="Clear log", style="Ghost.TButton",
                   command=self._clear_log).pack(side=tk.RIGHT)
        ttk.Button(actions, text="Clear cache", style="Ghost.TButton",
                   command=self._clear_cache).pack(side=tk.RIGHT, padx=(0, 6))

        # Log view
        log_frame = ttk.Labelframe(right, text="LOG", style="TLabelframe")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_view = LogView(log_frame, on_filter_change=self._on_log_filter_change)
        self.log_view.pack(fill=tk.BOTH, expand=True)

        # Refresh preset combos
        self._refresh_preset_combos()

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    def _wire_logger(self) -> None:
        def on_record(record):
            self.root.after(0, lambda r=record: self._render_record(r))
        self.logger.add_listener(on_record)

    def _render_record(self, record) -> None:
        from citadel.core.log import SEVERITY_FILTERS
        predicate = SEVERITY_FILTERS.get(self.log_view.current_filter(), SEVERITY_FILTERS["All"])
        if predicate(record):
            self.log_view.append(record.formatted(), record.tag())
        warn, err = self.logger.counts()
        self.log_view.set_summary(f"{warn} warning(s)  /  {err} error(s)")

    def _on_log_filter_change(self, _name: str) -> None:
        # Re-render all records under the new filter.
        records = self.logger.all_records()
        filtered_records = list(filtered(records, self.log_view.current_filter()))
        self.log_view.replace([(r.formatted(), r.tag()) for r in filtered_records])
        self.settings["log_filter"] = self.log_view.current_filter()

    def _clear_log(self) -> None:
        self.logger.clear()
        self.log_view.clear()
        self.log_view.set_summary("0 warning(s)  /  0 error(s)")

    # ------------------------------------------------------------------
    # Addons
    # ------------------------------------------------------------------
    def _on_source_changed(self) -> None:
        self.settings["project_source"] = self._source_field.get()
        # Debounce rapid key presses (and the trace-fire burst when Browse
        # populates the field) so we don't spawn a discovery thread per char.
        if self._discovery_after_id is not None:
            try:
                self.root.after_cancel(self._discovery_after_id)
            except tk.TclError:
                pass
        self._discovery_after_id = self.root.after(200, self._refresh_addons)

    def _refresh_addons(self) -> None:
        """Start a background scan of the project source for addons.

        Discovery walks the file system (and for terrain projects, walks
        children up to 3 levels deep), which can take noticeable time on real
        project folders. Running it on the UI thread freezes the window;
        running it under a thread keeps the GUI responsive and lets us drop
        stale results when the user picks another folder mid-scan.
        """
        self._discovery_after_id = None
        self._addon_list.delete(0, tk.END)
        self._discovered_targets = []
        source = self._source_field.get()
        if not source:
            return
        path = Path(source)
        if not path.is_dir():
            return

        self._discovery_seq += 1
        scan_id = self._discovery_seq
        exclude_patterns = list(self.settings.get("exclude_patterns", []))
        previous_status = self._status_text.get()
        self._status_text.set(f"Scanning {path.name}...")

        def worker(seq: int = scan_id) -> None:
            try:
                targets = discovery.discover_addons(path, exclude_patterns)
            except Exception as exc:
                self.root.after(0, lambda e=exc: self._on_discovery_failed(seq, e, previous_status))
                return
            self.root.after(0, lambda: self._on_discovery_complete(seq, targets, previous_status))

        threading.Thread(target=worker, daemon=True).start()

    def _on_discovery_complete(self, seq: int, targets: list[discovery.AddonTarget],
                                previous_status: str) -> None:
        # Drop late results so the user always sees the latest source's addons.
        if seq != self._discovery_seq:
            return
        self._addon_list.delete(0, tk.END)
        for target in targets:
            if target.has_wrp and not target.has_config:
                suffix = "  [WRP]"
            elif target.has_wrp:
                suffix = "  [terrain]"
            else:
                suffix = ""
            self._addon_list.insert(tk.END, target.name + suffix)
        if targets:
            self._addon_list.selection_set(0, tk.END)
        self._discovered_targets = targets
        if targets:
            self._status_text.set(f"{len(targets)} addon(s) found")
        else:
            self._status_text.set(previous_status or "No addons found")

    def _on_discovery_failed(self, seq: int, exc: Exception, previous_status: str) -> None:
        if seq != self._discovery_seq:
            return
        self.logger.error(f"Addon discovery failed: {exc}")
        self._status_text.set(previous_status or "Discovery failed")

    def _selected_addons(self) -> list[discovery.AddonTarget]:
        if not self._discovered_targets:
            return []
        indices = self._addon_list.curselection()
        return [self._discovered_targets[i] for i in indices]

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _start_build(self) -> None:
        if self._build_thread and self._build_thread.is_alive():
            return
        selected = self._selected_addons()
        if not selected:
            messagebox.showinfo("Build PBOs", "Select at least one addon to build.")
            return
        output = self._output_field.get()
        if not output:
            messagebox.showinfo("Build PBOs", "Choose a build output folder first.")
            return
        self.settings["project_source"] = self._source_field.get()
        self.settings["build_output"] = output
        settings.save_builder_settings(self.settings)

        output_root = Path(output)
        temp_root = Path(self.settings.get("temp_dir") or output_root / "_citadel_build_tmp")
        temp_root.mkdir(parents=True, exist_ok=True)
        tools = pipeline.ToolPaths(
            binarize=_path_or_none(self.settings.get("binarize_exe")),
            cfgconvert=_path_or_none(self.settings.get("cfgconvert_exe")),
            imagetopaa=_path_or_none(self.settings.get("imagetopaa_exe")),
            dssignfile=_path_or_none(self.settings.get("dssignfile_exe")),
            private_key=_path_or_none(self.settings.get("private_key")),
        )
        options = pipeline.BuildOptions(
            binarize_p3d=self.settings["pipeline"].get("binarize_p3d", True),
            binarize_wrp=self.settings["pipeline"].get("binarize_wrp", True),
            convert_cpp_to_bin=self.settings["pipeline"].get("convert_cpp_to_bin", True),
            update_paa=self.settings["pipeline"].get("update_paa", False),
            sign_pbos=self.settings["pipeline"].get("sign_pbos", True),
            copy_bikey=self.settings["pipeline"].get("copy_bikey", True),
            force_rebuild=self.settings["safety"].get("force_rebuild", False),
            skip_unchanged=self.settings["safety"].get("skip_unchanged", True),
            safe_publish=self.settings["safety"].get("safe_publish", True),
            verify_outputs=self.settings["safety"].get("verify_outputs", True),
            binarize_workers=int(self.settings["performance"].get("binarize_workers", 0)),
            exclude_patterns=list(self.settings.get("exclude_patterns", [])),
            binarize_addon_folders=list(self.settings.get("binarize_addon_folders", [])),
        )

        # Optional preflight first
        if self.settings["pipeline"].get("preflight_before_build", False):
            self._run_preflight_inline(selected)

        build_pipe = pipeline.BuildPipeline(output_root, temp_root, tools, options, self.logger)
        self.cancel_token = pipeline.CancelToken()
        self._set_busy(True, "Building")

        def worker():
            try:
                results = build_pipe.build_many(
                    selected,
                    cancel=self.cancel_token,
                    progress=self._progress_callback,
                )
                ok = sum(1 for r in results if r.success and not r.skipped)
                skipped = sum(1 for r in results if r.skipped)
                failed = sum(1 for r in results if not r.success)
                self.root.after(0, lambda: self._on_build_finished(ok, skipped, failed))
            except Exception as exc:
                self.logger.error(f"Build crashed: {exc}")
                self.root.after(0, lambda: self._on_build_finished(0, 0, len(selected)))

        self._build_thread = threading.Thread(target=worker, daemon=True)
        self._build_thread.start()

    def _on_build_finished(self, ok: int, skipped: int, failed: int) -> None:
        self._set_busy(False)
        if failed:
            self.status_badge.set_state("error", f"Done with errors ({failed})")
        elif ok or skipped:
            self.status_badge.set_state("done", "Build complete")
        else:
            self.status_badge.set_state("ready", "Ready")
        self._status_text.set(f"Built {ok}, skipped {skipped}, failed {failed}")
        self._save_log_to_disk()

    def _progress_callback(self, status_text: str, fraction: float) -> None:
        def apply():
            self._status_text.set(status_text)
            self._progress["value"] = max(0, min(100, int(fraction * 100)))
        self.root.after(0, apply)

    def _cancel_build(self) -> None:
        if self.cancel_token:
            self.cancel_token.request_cancel()
            self.logger.warn("Cancel requested; finishing current step...")

    def _set_busy(self, busy: bool, status: str = "Ready") -> None:
        self._build_btn.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self._preflight_btn.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self._cancel_btn.configure(state=tk.NORMAL if busy else tk.DISABLED)
        if busy:
            self.status_badge.set_state("building", status)
        else:
            self.status_badge.set_state("ready", "Ready")
            self._progress["value"] = 0

    # ------------------------------------------------------------------
    # Preflight
    # ------------------------------------------------------------------
    def _start_preflight(self) -> None:
        selected = self._selected_addons()
        if not selected:
            messagebox.showinfo("Preflight", "Select at least one addon to check.")
            return
        self._set_busy(True, "Preflight")
        self.status_badge.set_state("preflight", "Preflight")

        def worker():
            try:
                self._run_preflight_inline(selected, write_report=True)
            finally:
                self.root.after(0, lambda: self._set_busy(False))
                self.root.after(0, lambda: self.status_badge.set_state("done", "Preflight complete"))

        threading.Thread(target=worker, daemon=True).start()

    def _run_preflight_inline(self, addons: list[discovery.AddonTarget],
                              write_report: bool = False) -> None:
        opts = preflight.PreflightOptions(
            required_addons_hints=self.settings["preflight"].get("required_addons_hints", True),
            texture_freshness=self.settings["preflight"].get("texture_freshness", True),
            risky_path_names=self.settings["preflight"].get("risky_path_names", True),
            case_conflicts=self.settings["preflight"].get("case_conflicts", True),
            p3d_internal_scan=self.settings["preflight"].get("p3d_internal_scan", True),
            terrain_wrp_checks=self.settings["preflight"].get("terrain_wrp_checks", True),
            terrain_navmesh_checks=self.settings["preflight"].get("terrain_navmesh_checks", True),
            wrp_internal_scan=self.settings["preflight"].get("wrp_internal_scan", False),
            terrain_source_export_warnings=self.settings["preflight"].get("terrain_source_export_warnings", True),
            terrain_layer_checks=self.settings["preflight"].get("terrain_layer_checks", True),
            map_2d_config_checks=self.settings["preflight"].get("map_2d_config_checks", True),
            terrain_size_checks=self.settings["preflight"].get("terrain_size_checks", True),
            script_checks=self.settings["preflight"].get("script_checks", True),
            exclude_patterns=list(self.settings.get("exclude_patterns", [])),
        )
        cfgconvert = _path_or_none(self.settings.get("cfgconvert_exe"))
        output_root = Path(self._output_field.get()) if self._output_field.get() else Path.cwd()
        report_dir = output_root / "_citadel_preflight_reports"
        for addon in addons:
            findings = preflight.run_preflight(addon, opts, cfgconvert, self.logger)
            if write_report:
                txt, json_path = preflight.export_report(findings, addon.name, report_dir)
                self.logger.info(f"Preflight report: {txt.name}")

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------
    def _refresh_preset_combos(self) -> None:
        sources = [p.name for p in presets.list_presets("source")]
        outputs = [p.name for p in presets.list_presets("output")]
        self._source_preset_combo["values"] = sources
        self._output_preset_combo["values"] = outputs

    def _load_preset(self, kind, name: str) -> None:
        if not name:
            return
        preset = presets.get_preset(kind, name)
        if preset is None:
            return
        if kind == "source":
            self._source_field.set(preset.path)
            self.settings["project_source"] = preset.path
            self._refresh_addons()
            if self._discovered_targets:
                self._addon_list.selection_set(0, tk.END)
        else:
            self._output_field.set(preset.path)
            self.settings["build_output"] = preset.path
        self.logger.info(f"Loaded {kind} preset '{name}'")

    def _save_preset_dialog(self, kind) -> None:
        field = self._source_field if kind == "source" else self._output_field
        current = field.get()
        if not current:
            messagebox.showinfo("Save preset", f"Set a {kind} path before saving a preset.")
            return
        name = _ask_string(self.root, "Save preset", f"Name for this {kind} preset:")
        if not name:
            return
        presets.add_preset(kind, name, current)
        self._refresh_preset_combos()
        self.logger.success(f"Saved {kind} preset '{name}'")

    def _delete_preset_dialog(self, kind) -> None:
        var = self._source_preset_var if kind == "source" else self._output_preset_var
        name = var.get()
        if not name:
            return
        if messagebox.askyesno("Delete preset", f"Delete {kind} preset '{name}'?"):
            presets.remove_preset(kind, name)
            var.set("")
            self._refresh_preset_combos()
            self.logger.info(f"Deleted {kind} preset '{name}'")

    # ------------------------------------------------------------------
    # Options + window
    # ------------------------------------------------------------------
    def _show_options(self) -> None:
        OptionsDialog(self.root, dict(self.settings), self._on_options_saved)

    def _on_options_saved(self, new_data: dict) -> None:
        self.settings.update(new_data)
        self._refresh_addons()
        self.logger.info("Builder options updated")

    def _show_about(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("About")
        dlg.configure(bg=theme.VIOLET_DEEP)
        dlg.geometry("440x300")
        dlg.transient(self.root)
        ttk.Label(dlg, text="Citadel PBO Builder", style="TitleDeep.TLabel").pack(padx=16, pady=(16, 4), anchor=tk.W)
        ttk.Label(dlg, text=f"Version {VERSION_STRING}", style="Subtitle.TLabel").pack(padx=16, anchor=tk.W)
        ttk.Label(dlg,
                  text=("Citadel-branded DayZ addon packer.\n\n"
                        "Pack, binarize, convert, sign, and publish PBO archives\n"
                        "with safe output handling and preflight checks."),
                  style="Subtitle.TLabel",
                  wraplength=400, justify=tk.LEFT).pack(padx=16, pady=12, anchor=tk.W)
        ttk.Button(dlg, text="Close", style="Primary.TButton",
                   command=dlg.destroy).pack(pady=12)

    def _save_log_to_disk(self) -> None:
        if not self._output_field.get():
            return
        log_dir = Path(self._output_field.get()) / "_citadel_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        log_path = log_dir / f"build_{datetime.now():%Y%m%d_%H%M%S}.log"
        try:
            self.logger.save_to(log_path)
            self.logger.info(f"Saved log: {log_path}")
        except OSError as exc:
            self.logger.warn(f"Could not save log: {exc}")

    def _clear_cache(self) -> None:
        if messagebox.askyesno("Clear cache", "Clear all build cache records? Next build will rebuild everything."):
            count = cache.clear_all()
            self.logger.success(f"Cleared {count} cache record(s)")

    def _pick_dir(self, initial: str, title: str) -> str | None:
        result = filedialog.askdirectory(title=title, initialdir=initial or None)
        return result or None

    def _open_in_explorer(self, path: str) -> None:
        if not path or not Path(path).exists():
            self.logger.warn(f"Cannot open: {path}")
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except AttributeError:
            subprocess.Popen(["xdg-open", path])

    # ------------------------------------------------------------------
    # Geometry persistence
    # ------------------------------------------------------------------
    def _apply_window_geometry(self) -> None:
        win = self.settings.get("window", {})
        w, h = int(win.get("w", 1280)), int(win.get("h", 860))
        x, y = int(win.get("x", -1)), int(win.get("y", -1))
        if x >= 0 and y >= 0:
            self.root.geometry(f"{w}x{h}+{x}+{y}")
        else:
            self.root.geometry(f"{w}x{h}")
        if win.get("maximized"):
            try:
                self.root.state("zoomed")
            except tk.TclError:
                pass

    def _save_window_geometry(self) -> None:
        try:
            geo = self.root.winfo_geometry()
            maximized = self.root.state() == "zoomed"
            size, _, pos = geo.partition("+")
            w, h = (int(v) for v in size.split("x"))
            x_str, _, y_str = pos.partition("+")
            x = int(x_str) if x_str else -1
            y = int(y_str) if y_str else -1
            self.settings["window"] = {"w": w, "h": h, "x": x, "y": y, "maximized": maximized}
        except (tk.TclError, ValueError):
            pass

    def _on_close(self) -> None:
        # Persist state, cancel any in-flight build, then tear the window down
        # unconditionally. (Previously this only destroyed when the app
        # constructed its own root; entry-point usage passes a root in, which
        # left the X button as a no-op.)
        try:
            self._save_window_geometry()
            self.settings["project_source"] = self._source_field.get()
            self.settings["build_output"] = self._output_field.get()
            settings.save_builder_settings(self.settings)
        except Exception:
            pass
        if self.cancel_token is not None:
            self.cancel_token.request_cancel()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self) -> None:
        self.root.mainloop()


def _apply_window_icon(root: tk.Misc) -> None:
    """Replace the default Tk feather icon with the Citadel shield."""
    icon = assets.icon_path()
    if icon is None:
        return
    try:
        root.iconbitmap(default=str(icon))
    except tk.TclError:
        # Fallback for environments where iconbitmap is rejected.
        try:
            from tkinter import PhotoImage
            png = assets.asset_path("citadel_logo.png")
            if png.is_file():
                image = PhotoImage(file=str(png))
                root.iconphoto(True, image)
                root._citadel_icon_ref = image  # type: ignore[attr-defined]
        except Exception:
            pass


def _path_or_none(raw: str | None) -> Path | None:
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def _ask_string(parent: tk.Misc, title: str, prompt: str) -> str | None:
    """Small Citadel-themed string-input dialog."""
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.configure(bg=theme.VIOLET_DEEP)
    dlg.geometry("400x150")
    dlg.transient(parent)
    dlg.grab_set()
    ttk.Label(dlg, text=prompt, style="TitleDeep.TLabel").pack(padx=16, pady=(16, 4), anchor=tk.W)
    var = tk.StringVar()
    entry = ttk.Entry(dlg, textvariable=var)
    entry.pack(fill=tk.X, padx=16, pady=8)
    entry.focus_set()
    result = {"value": None}

    def ok() -> None:
        result["value"] = var.get().strip()
        dlg.destroy()

    def cancel() -> None:
        dlg.destroy()

    buttons = ttk.Frame(dlg, style="Deep.TFrame")
    buttons.pack(fill=tk.X, padx=16, pady=8)
    ttk.Button(buttons, text="Cancel", command=cancel).pack(side=tk.RIGHT)
    ttk.Button(buttons, text="OK", style="Primary.TButton", command=ok).pack(side=tk.RIGHT, padx=4)
    entry.bind("<Return>", lambda _e: ok())
    parent.wait_window(dlg)
    return result["value"]
