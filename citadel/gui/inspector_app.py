"""Citadel PBO Inspector main window."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from citadel.core import assets, dayz_tools, pbo, settings, theme
from citadel.core.log import Logger
from citadel.core.paths import human_size, normalize_pbo_path
from citadel.gui.widgets import HeaderBar, LogView, StatusBadge
from citadel.inspector.p3d_meta import inspect_p3d
from citadel.inspector.viewer import TextViewer
from citadel_version import VERSION_STRING, inspector_title


_TEXT_PREVIEW_EXTENSIONS = {
    ".cpp", ".hpp", ".h", ".c", ".cfg", ".rvmat", ".sqf", ".txt", ".xml",
    ".json", ".layout", ".log", ".md", ".py", ".lua",
}


class InspectorApp:
    def __init__(self, parent: tk.Tk | None = None) -> None:
        self._owns_root = parent is None
        self.root = parent or tk.Tk()
        if self._owns_root:
            theme.apply_theme(self.root)
        self.root.title(inspector_title())
        self.root.minsize(900, 600)
        _apply_window_icon(self.root)

        self.settings = settings.load_inspector_settings()
        self._apply_window_geometry()

        self.logger = Logger()
        self.archive: pbo.PboArchive | None = None
        self._dnd_enabled = False
        self._iid_to_entry: dict[str, pbo.PboEntry] = {}

        self._build_ui()
        self._wire_logger()
        self._enable_drag_drop()

    # ---------------- UI construction ----------------
    def _build_ui(self) -> None:
        header = HeaderBar(self.root,
                           title="Citadel PBO Inspector",
                           subtitle=f"v{VERSION_STRING}  -  Inspect, preview, and extract DayZ PBOs")
        header.pack(fill=tk.X)
        ttk.Button(header.actions, text="About", style="Ghost.TButton",
                   command=self._show_about).pack(side=tk.RIGHT, padx=4)
        ttk.Button(header.actions, text="Options", style="Secondary.TButton",
                   command=self._show_options).pack(side=tk.RIGHT, padx=4)

        # Path row
        path_row = ttk.Frame(self.root)
        path_row.pack(fill=tk.X, padx=28, pady=(20, 12))
        ttk.Label(path_row, text="PBO PATH", style="Header.TLabel").pack(anchor=tk.W)
        sub = ttk.Frame(path_row)
        sub.pack(fill=tk.X, pady=(6, 0))
        self._pbo_path = tk.StringVar(value=self.settings.get("last_pbo", ""))
        entry = ttk.Entry(sub, textvariable=self._pbo_path)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entry.bind("<Return>", lambda _e: self._reload_pbo())
        ttk.Button(sub, text="Browse", command=self._browse_pbo).pack(side=tk.LEFT, padx=(8, 4))
        ttk.Button(sub, text="Reload", style="Secondary.TButton",
                   command=self._reload_pbo).pack(side=tk.LEFT)

        # Header info strip — card with PBO metadata
        info = ttk.Frame(self.root, style="Card.TFrame")
        info.pack(fill=tk.X, padx=28, pady=(0, 16))
        info_inner = ttk.Frame(info, style="Card.TFrame")
        info_inner.pack(fill=tk.X, padx=18, pady=14)
        self._prefix_var = tk.StringVar(value="Prefix  -")
        self._product_var = tk.StringVar(value="Product  -")
        self._count_var = tk.StringVar(value="Entries  0")
        self._size_var = tk.StringVar(value="Total  0 B")
        for var in (self._prefix_var, self._product_var, self._count_var, self._size_var):
            ttk.Label(info_inner, textvariable=var, style="MutedPanel.TLabel").pack(side=tk.LEFT, padx=(0, 24))
        self.status_badge = StatusBadge(info_inner)
        self.status_badge.pack(side=tk.RIGHT)

        # Body: tree + actions + log
        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, padx=28, pady=(0, 20))

        left = ttk.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(left, text="CONTENTS", style="Header.TLabel").pack(anchor=tk.W)
        tree_frame = ttk.Frame(left)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 8))

        self.tree = ttk.Treeview(tree_frame,
                                  columns=("size", "packing", "timestamp"),
                                  show="tree headings",
                                  selectmode="extended")
        self.tree.heading("#0", text="Path")
        self.tree.heading("size", text="Size")
        self.tree.heading("packing", text="Packing")
        self.tree.heading("timestamp", text="Modified")
        self.tree.column("#0", width=420, stretch=True)
        self.tree.column("size", width=90, anchor=tk.E)
        self.tree.column("packing", width=130)
        self.tree.column("timestamp", width=160)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.bind("<Double-1>", lambda _e: self._view_selected())

        # Action buttons under the tree
        actions = ttk.Frame(left)
        actions.pack(fill=tk.X, pady=(8, 16))
        ttk.Button(actions, text="View selected", style="Secondary.TButton",
                   command=self._view_selected).pack(side=tk.LEFT)
        ttk.Button(actions, text="Inspect P3D", style="TButton",
                   command=self._inspect_selected_p3d).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="Extract selected", style="TButton",
                   command=lambda: self._extract(selected_only=True)).pack(side=tk.LEFT)
        ttk.Button(actions, text="Extract all", style="Primary.TButton",
                   command=lambda: self._extract(selected_only=False)).pack(side=tk.RIGHT)

        # Log area
        ttk.Label(left, text="LOG", style="Header.TLabel").pack(anchor=tk.W)
        self.log_view = LogView(left)
        self.log_view.pack(fill=tk.BOTH, expand=False, pady=(8, 0))

        # If we already have a path remembered, try loading it.
        if self._pbo_path.get():
            self.root.after(120, self._reload_pbo)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- Logger wiring ----------------
    def _wire_logger(self) -> None:
        def on_record(record):
            self.root.after(0, lambda r=record: self.log_view.append(r.formatted(), r.tag()))
        self.logger.add_listener(on_record)

    def _enable_drag_drop(self) -> None:
        # tkinterdnd2 is optional — only enabled when the parent root supports it.
        try:
            from tkinterdnd2 import DND_FILES  # type: ignore
            if hasattr(self.root, "drop_target_register"):
                self.root.drop_target_register(DND_FILES)
                self.root.dnd_bind("<<Drop>>", self._on_drop)
                self._dnd_enabled = True
        except Exception:
            # Silently skip when DnD isn't available — Browse still works.
            self._dnd_enabled = False

    def _on_drop(self, event: tk.Event) -> None:  # type: ignore[override]
        raw = event.data.strip() if hasattr(event, "data") else ""
        # Drop payloads may be space-separated with brace-quoted paths.
        path = raw.strip("{}").split("} {")[0].strip("{}")
        if path.lower().endswith(".pbo"):
            self._pbo_path.set(path)
            self._reload_pbo()

    # ---------------- Window geometry ----------------
    def _apply_window_geometry(self) -> None:
        win = self.settings.get("window", {})
        w, h = int(win.get("w", 1180)), int(win.get("h", 780))
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
            if "x" in size:
                w, h = (int(v) for v in size.split("x"))
            else:
                w, h = 1180, 780
            x_str, _, y_str = pos.partition("+")
            x = int(x_str) if x_str else -1
            y = int(y_str) if y_str else -1
            self.settings["window"] = {"w": w, "h": h, "x": x, "y": y, "maximized": maximized}
        except (tk.TclError, ValueError):
            pass

    def _on_close(self) -> None:
        try:
            self._save_window_geometry()
            settings.save_inspector_settings(self.settings)
        except Exception:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # ---------------- PBO loading ----------------
    def _browse_pbo(self) -> None:
        last = self._pbo_path.get()
        initial_dir = str(Path(last).parent) if last else ""
        path = filedialog.askopenfilename(
            title="Select PBO",
            filetypes=[("PBO archives", "*.pbo"), ("All files", "*.*")],
            initialdir=initial_dir,
        )
        if path:
            self._pbo_path.set(path)
            self._reload_pbo()

    def _reload_pbo(self) -> None:
        path_str = self._pbo_path.get().strip().strip('"').strip("'")
        if not path_str:
            return
        path = Path(path_str)
        try:
            self.archive = pbo.read_pbo(path)
        except pbo.PboError as exc:
            self.archive = None
            self.logger.error(f"Failed to read PBO: {exc}")
            self.status_badge.set_state("error", "Error")
            messagebox.showerror("PBO error", str(exc))
            return
        except OSError as exc:
            self.archive = None
            self.logger.error(f"Could not open file: {exc}")
            self.status_badge.set_state("error", "Error")
            return

        self.settings["last_pbo"] = str(path)
        self._populate_tree()
        self._update_header_info()
        self.status_badge.set_state("done", "Loaded")
        self.logger.success(f"Loaded {path.name} ({self.archive.file_count} entries)")

    def _populate_tree(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._iid_to_entry.clear()
        if not self.archive:
            return

        folder_ids: dict[str, str] = {}
        for entry in self.archive.entries:
            parts = normalize_pbo_path(entry.name).split("\\")
            parent_id = ""
            accumulated = ""
            for index, part in enumerate(parts):
                accumulated = part if not accumulated else f"{accumulated}\\{part}"
                if index == len(parts) - 1:
                    iid = self.tree.insert(parent_id, "end", text=part,
                                            values=(human_size(entry.original_size),
                                                    entry.packing_name(),
                                                    _fmt_ts(entry.timestamp)),
                                            tags=("file",))
                    self._iid_to_entry[iid] = entry
                else:
                    if accumulated not in folder_ids:
                        folder_ids[accumulated] = self.tree.insert(
                            parent_id, "end", text=part,
                            values=("", "", ""), tags=("folder",))
                    parent_id = folder_ids[accumulated]

    def _update_header_info(self) -> None:
        if not self.archive:
            return
        self._prefix_var.set(f"Prefix:  {self.archive.prefix or '-'}")
        self._product_var.set(f"Product: {self.archive.product or '-'}")
        self._count_var.set(f"Entries: {self.archive.file_count}")
        self._size_var.set(f"Total:   {human_size(self.archive.total_unpacked_size)}")

    # ---------------- View / preview ----------------
    def _view_selected(self) -> None:
        if not self.archive:
            return
        selection = self.tree.selection()
        if not selection:
            return
        iid = selection[0]
        entry = self._iid_to_entry.get(iid)
        if entry is None:
            return  # folder

        suffix = Path(entry.name).suffix.lower()
        try:
            data = pbo.read_entry_bytes(self.archive, entry)
        except pbo.PboError as exc:
            self.logger.error(f"Cannot read {entry.name}: {exc}")
            return

        # CfgConvert preview for .bin and rapified materials, if configured.
        cfgconvert = self._cfgconvert_path()
        if suffix == ".bin" and entry.name.lower() != "texheaders.bin" and cfgconvert:
            text = self._cfgconvert_to_text(data, cfgconvert, suffix=".bin")
            if text is not None:
                self._show_text(entry.name, text, ".cpp")
                return
        if suffix in (".rvmat", ".bisurf", ".surface", ".mat") and cfgconvert:
            text = self._cfgconvert_to_text(data, cfgconvert, suffix=suffix)
            if text is not None:
                self._show_text(entry.name, text, ".rvmat")
                return

        if suffix in _TEXT_PREVIEW_EXTENSIONS:
            self._show_text(entry.name, data.decode("utf-8", errors="replace"), suffix)
            return

        if suffix == ".p3d":
            info = inspect_p3d(self._extract_to_temp(entry, data))
            self._show_text(entry.name, info.summary(), ".txt")
            return

        # Generic fallback: hex peek of first 512 bytes
        preview = data[:512]
        hex_lines: list[str] = []
        for offset in range(0, len(preview), 16):
            chunk = preview[offset:offset + 16]
            hex_part = " ".join(f"{b:02X}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            hex_lines.append(f"{offset:08X}  {hex_part:<48}  {ascii_part}")
        self._show_text(entry.name, "\n".join(hex_lines) or "<empty>", "")

    def _inspect_selected_p3d(self) -> None:
        if not self.archive:
            return
        selection = self.tree.selection()
        if not selection:
            return
        iid = selection[0]
        entry = self._iid_to_entry.get(iid)
        if entry is None or Path(entry.name).suffix.lower() != ".p3d":
            messagebox.showinfo("Inspect P3D", "Select a .p3d entry first.")
            return
        try:
            data = pbo.read_entry_bytes(self.archive, entry)
        except pbo.PboError as exc:
            self.logger.error(f"Cannot read {entry.name}: {exc}")
            return
        info = inspect_p3d(self._extract_to_temp(entry, data))
        self._show_text(entry.name + "  (info)", info.summary(), ".txt")

    def _show_text(self, name: str, content: str, ext: str) -> None:
        TextViewer(self.root, name, content, file_extension=ext)

    # ---------------- Extraction ----------------
    def _extract(self, *, selected_only: bool) -> None:
        if not self.archive:
            messagebox.showinfo("Extract", "Load a PBO first.")
            return

        # No prompts — always extract next to the PBO into a
        # <pbo-stem>_extracted/ subfolder. If the folder already exists we
        # merge into it so repeated extracts behave intuitively.
        pbo_stem = self.archive.source_path.stem  # e.g. "AP_equipment_PUBLIC"
        target = self.archive.source_path.parent / f"{pbo_stem}_extracted"
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Extract", f"Could not create folder:\n{target}\n\n{exc}")
            return

        entries: list[pbo.PboEntry]
        if selected_only:
            entries = self._entries_from_selection()
            if not entries:
                messagebox.showinfo("Extract", "Select one or more entries first.")
                return
        else:
            entries = list(self.archive.entries)

        self.logger.info(f"Extracting to: {target}")
        self.status_badge.set_state("building", "Extracting")
        thread = threading.Thread(target=self._extract_worker,
                                   args=(entries, target),
                                   daemon=True)
        thread.start()

    def _extract_worker(self, entries: list[pbo.PboEntry], target: Path) -> None:
        ok = 0
        skipped = 0
        for entry in entries:
            if not entry.is_supported_for_extract:
                skipped += 1
                self.logger.warn(f"Skipping unsupported entry: {entry.name}")
                continue
            try:
                written = pbo.extract_entry(self.archive, entry, target)  # type: ignore[arg-type]
                ok += 1
                if self.settings.get("convert_bin_to_cpp", True) and self._cfgconvert_path():
                    self._maybe_convert_in_place(written)
            except pbo.PboError as exc:
                self.logger.error(f"{entry.name}: {exc}")

        # Preserve the PBO prefix so a Builder rebuild round-trips correctly.
        # The prefix lives in the PBO Vers header, not as a file entry, so
        # without this step the extracted folder would have no $PBOPREFIX$
        # and the Builder would fall back to the folder name.
        if self.archive is not None:
            try:
                prefix_path = pbo.write_prefix_file(self.archive, target)
                if prefix_path is not None:
                    self.logger.info(
                        f"Wrote $PBOPREFIX$ (prefix='{self.archive.prefix}') "
                        f"so rebuilding round-trips correctly"
                    )
            except OSError as exc:
                self.logger.warn(f"Could not write $PBOPREFIX$: {exc}")

        self.logger.success(f"Extracted {ok} file(s) to {target}")
        if skipped:
            self.logger.warn(f"Skipped {skipped} unsupported entry/entries")
        self.root.after(0, lambda: self.status_badge.set_state("done", "Extracted"))

    def _maybe_convert_in_place(self, written: Path) -> None:
        suffix = written.suffix.lower()
        cfgconvert = self._cfgconvert_path()
        if cfgconvert is None:
            return
        if suffix == ".bin":
            if written.name.lower() == "texheaders.bin":
                return
            cpp = written.with_suffix(".cpp")
            result = dayz_tools.run_tool(cfgconvert, ["-txt", "-dst", str(cpp), str(written)])
            if result.succeeded and cpp.is_file() and cpp.stat().st_size > 0:
                written.unlink(missing_ok=True)
                self.logger.tool(f"Converted {written.name} -> {cpp.name}")
        elif suffix in (".rvmat", ".bisurf", ".surface", ".mat"):
            tmp = written.with_suffix(written.suffix + ".txt.tmp")
            result = dayz_tools.run_tool(cfgconvert, ["-txt", "-dst", str(tmp), str(written)])
            if result.succeeded and tmp.is_file() and tmp.stat().st_size > 0:
                written.unlink(missing_ok=True)
                tmp.rename(written)
                self.logger.tool(f"Derapified {written.name}")
            else:
                tmp.unlink(missing_ok=True)

    def _entries_from_selection(self) -> list[pbo.PboEntry]:
        selected_ids = self.tree.selection()
        if not selected_ids:
            return []
        result: list[pbo.PboEntry] = []
        for iid in selected_ids:
            entry = self._iid_to_entry.get(iid)
            if entry is not None:
                result.append(entry)
            else:
                # Folder: collect every descendant entry.
                result.extend(self._descendants_entries(iid))
        # Unique by name.
        seen: set[str] = set()
        unique: list[pbo.PboEntry] = []
        for entry in result:
            key = entry.name.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(entry)
        return unique

    def _descendants_entries(self, iid: str) -> list[pbo.PboEntry]:
        collected: list[pbo.PboEntry] = []
        stack = [iid]
        while stack:
            current = stack.pop()
            for child in self.tree.get_children(current):
                entry = self._iid_to_entry.get(child)
                if entry is not None:
                    collected.append(entry)
                else:
                    stack.append(child)
        return collected

    # ---------------- Helpers ----------------
    def _cfgconvert_path(self) -> Path | None:
        value = self.settings.get("cfgconvert_exe", "").strip()
        if value:
            path = Path(value)
            if path.is_file():
                return path
        detected = dayz_tools.detect().cfgconvert
        return detected

    def _cfgconvert_to_text(self, data: bytes, cfgconvert: Path, suffix: str) -> str | None:
        """Run CfgConvert on raw bytes to produce a text preview."""
        import tempfile
        with tempfile.TemporaryDirectory(prefix="citadel_inspect_") as tmpdir:
            tmp_root = Path(tmpdir)
            input_path = tmp_root / ("input" + suffix)
            input_path.write_bytes(data)
            output_path = tmp_root / "output.txt"
            result = dayz_tools.run_tool(cfgconvert, ["-txt", "-dst", str(output_path), str(input_path)])
            if result.succeeded and output_path.is_file():
                try:
                    return output_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return None
        return None

    def _extract_to_temp(self, entry: pbo.PboEntry, data: bytes) -> Path:
        import tempfile
        fd, name = tempfile.mkstemp(prefix="citadel_p3d_", suffix=Path(entry.name).suffix)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
        except Exception:
            try:
                os.unlink(name)
            except OSError:
                pass
            raise
        return Path(name)

    # ---------------- Menus ----------------
    def _show_options(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("Inspector Options")
        dlg.configure(bg=theme.VIOLET_DEEP)
        dlg.geometry("520x320")
        dlg.transient(self.root)

        ttk.Label(dlg, text="Inspector Options", style="TitleDeep.TLabel").pack(anchor=tk.W, padx=16, pady=(12, 6))

        body = ttk.Frame(dlg)
        body.pack(fill=tk.BOTH, expand=True, padx=16)

        ttk.Label(body, text="CfgConvert.exe (optional, for .bin/.rvmat preview):",
                  style="Header.TLabel").pack(anchor=tk.W, pady=(4, 0))
        cfg_row = ttk.Frame(body)
        cfg_row.pack(fill=tk.X, pady=(2, 8))
        cfg_var = tk.StringVar(value=self.settings.get("cfgconvert_exe", ""))
        ttk.Entry(cfg_row, textvariable=cfg_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        def browse_cfg() -> None:
            path = filedialog.askopenfilename(title="Locate CfgConvert.exe",
                                              filetypes=[("CfgConvert", "CfgConvert.exe"), ("All", "*.*")])
            if path:
                cfg_var.set(path)

        ttk.Button(cfg_row, text="Browse...", command=browse_cfg).pack(side=tk.LEFT, padx=4)
        ttk.Button(cfg_row, text="Auto-detect", style="Secondary.TButton",
                   command=lambda: cfg_var.set(str(dayz_tools.detect().cfgconvert or ""))).pack(side=tk.LEFT)

        convert_var = tk.BooleanVar(value=self.settings.get("convert_bin_to_cpp", True))
        ttk.Checkbutton(body, text="Convert .bin to .cpp on extract",
                        variable=convert_var).pack(anchor=tk.W, pady=4)
        convert_rvmat_var = tk.BooleanVar(value=self.settings.get("convert_rapified_materials", True))
        ttk.Checkbutton(body, text="Derapify .rvmat / .bisurf / .mat on extract",
                        variable=convert_rvmat_var).pack(anchor=tk.W)

        # Buttons
        buttons = ttk.Frame(dlg)
        buttons.pack(fill=tk.X, padx=16, pady=12)

        def save_and_close() -> None:
            self.settings["cfgconvert_exe"] = cfg_var.get().strip()
            self.settings["convert_bin_to_cpp"] = convert_var.get()
            self.settings["convert_rapified_materials"] = convert_rvmat_var.get()
            settings.save_inspector_settings(self.settings)
            dlg.destroy()

        ttk.Button(buttons, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Save", style="Primary.TButton",
                   command=save_and_close).pack(side=tk.RIGHT, padx=8)

    def _show_about(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("About")
        dlg.configure(bg=theme.VIOLET_DEEP)
        dlg.geometry("420x260")
        dlg.transient(self.root)
        ttk.Label(dlg, text="Citadel PBO Inspector", style="TitleDeep.TLabel").pack(padx=16, pady=(16, 4), anchor=tk.W)
        ttk.Label(dlg, text=f"Version {VERSION_STRING}", style="Subtitle.TLabel").pack(padx=16, anchor=tk.W)
        ttk.Label(dlg,
                  text=("Built for Citadel.\n\n"
                        "Inspect, preview, and extract DayZ PBO archives.\n"
                        "Drag a .pbo onto this window or click Browse... to begin."),
                  style="Subtitle.TLabel",
                  wraplength=380, justify=tk.LEFT).pack(padx=16, pady=12, anchor=tk.W)
        ttk.Button(dlg, text="Close", style="Primary.TButton",
                   command=dlg.destroy).pack(pady=12)

    # ---------------- Entry point ----------------
    def run(self) -> None:
        self.root.mainloop()


def _fmt_ts(epoch: int) -> str:
    if not epoch:
        return ""
    from datetime import datetime
    try:
        return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, ValueError):
        return ""


def _apply_window_icon(root: tk.Misc) -> None:
    """Replace the default Tk feather icon with the Citadel shield."""
    icon = assets.icon_path()
    if icon is None:
        return
    try:
        root.iconbitmap(default=str(icon))
    except tk.TclError:
        try:
            from tkinter import PhotoImage
            png = assets.asset_path("citadel_logo.png")
            if png.is_file():
                image = PhotoImage(file=str(png))
                root.iconphoto(True, image)
                root._citadel_icon_ref = image  # type: ignore[attr-defined]
        except Exception:
            pass
