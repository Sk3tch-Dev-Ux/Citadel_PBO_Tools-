"""JSON-backed persistent settings for Builder and Inspector.

Settings live under ``%APPDATA%/Citadel/PBO_Tools/`` so they survive uninstall
and EXE updates. Two separate files keep the Builder and Inspector independent.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _appdata_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata)
    else:
        base = Path.home() / ".citadel"
    folder = base / "Citadel" / "PBO_Tools"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def builder_settings_path() -> Path:
    return _appdata_dir() / "builder_settings.json"


def inspector_settings_path() -> Path:
    return _appdata_dir() / "inspector_settings.json"


def presets_path() -> Path:
    return _appdata_dir() / "path_presets.json"


def cache_dir() -> Path:
    folder = _appdata_dir() / "cache"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load JSON from ``path``; return ``default`` (or empty dict) if missing or unreadable."""
    if default is None:
        default = {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return dict(default)


def save_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically write ``data`` to ``path`` as pretty JSON.

    Writes to a sibling temp file and replaces atomically, so a crash mid-write
    cannot corrupt an existing settings file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------- Builder defaults ----------

BUILDER_DEFAULTS: dict[str, Any] = {
    "project_source": "",
    "build_output": "",
    "private_key": "",
    "binarize_exe": "",
    "cfgconvert_exe": "",
    "imagetopaa_exe": "",
    "dssignfile_exe": "",
    "temp_dir": "",
    "exclude_patterns": [
        "*.bak", "*.tmp", ".vs", ".vscode", ".git", ".gitignore",
        "*.psd", "*.kra",
    ],
    "binarize_addon_folders": [],
    "pipeline": {
        "binarize_p3d": True,
        "binarize_wrp": True,
        "convert_cpp_to_bin": True,
        "update_paa": False,
        "sign_pbos": True,
        "copy_bikey": True,
        "preflight_before_build": False,
    },
    "safety": {
        "force_rebuild": False,
        "skip_unchanged": True,
        "safe_publish": True,
        "verify_outputs": True,
        "content_safe_cache": True,
    },
    "performance": {
        "binarize_workers": 0,  # 0 = auto = all logical threads
        "batch_log_updates": True,
    },
    "preflight": {
        "required_addons_hints": True,
        "texture_freshness": True,
        "risky_path_names": True,
        "case_conflicts": True,
        "p3d_internal_scan": True,
        "terrain_wrp_checks": True,
        "terrain_navmesh_checks": True,
        "wrp_internal_scan": False,
        "terrain_source_export_warnings": True,
        "terrain_layer_checks": True,
        "map_2d_config_checks": True,
        "terrain_size_checks": True,
        "script_checks": True,
    },
    "log_filter": "All",  # All | HideInfo | WarnError | ErrorOnly
    "window": {"w": 1280, "h": 860, "x": -1, "y": -1, "maximized": False},
}

INSPECTOR_DEFAULTS: dict[str, Any] = {
    "last_pbo": "",
    "cfgconvert_exe": "",
    "convert_bin_to_cpp": True,
    "convert_rapified_materials": True,
    "extract_root": "",
    "window": {"w": 1180, "h": 780, "x": -1, "y": -1, "maximized": False},
}


def load_builder_settings() -> dict[str, Any]:
    data = load_json(builder_settings_path(), BUILDER_DEFAULTS)
    return _merge_defaults(data, BUILDER_DEFAULTS)


def save_builder_settings(data: dict[str, Any]) -> None:
    save_json(builder_settings_path(), data)


def load_inspector_settings() -> dict[str, Any]:
    data = load_json(inspector_settings_path(), INSPECTOR_DEFAULTS)
    return _merge_defaults(data, INSPECTOR_DEFAULTS)


def save_inspector_settings(data: dict[str, Any]) -> None:
    save_json(inspector_settings_path(), data)


def _merge_defaults(data: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Recursively fill in missing keys from defaults so old setting files keep working."""
    result = dict(data)
    for key, default_value in defaults.items():
        if key not in result:
            result[key] = default_value if not isinstance(default_value, dict) else dict(default_value)
        elif isinstance(default_value, dict) and isinstance(result[key], dict):
            result[key] = _merge_defaults(result[key], default_value)
    return result
