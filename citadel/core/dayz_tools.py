"""DayZ Tools discovery and external tool runners.

DayZ Tools ship under Steam at ``steamapps/common/DayZ Tools``. Steam can
install games on any drive via libraryfolders.vdf, so we scan every declared
library, not just the default C-drive location.

The tools we care about live in fixed paths under the DayZ Tools root:

  - Bin/Binarize/Binarize.exe
  - Bin/CfgConvert/CfgConvert.exe
  - Bin/ImageToPAA/ImageToPAA.exe
  - Bin/DsUtils/DSSignFile.exe
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


DAYZTOOLS_FOLDER = "DayZ Tools"
TOOL_SUBPATHS = {
    "binarize": Path("Bin") / "Binarize" / "Binarize.exe",
    "cfgconvert": Path("Bin") / "CfgConvert" / "CfgConvert.exe",
    "imagetopaa": Path("Bin") / "ImageToPAA" / "ImageToPAA.exe",
    "dssignfile": Path("Bin") / "DsUtils" / "DSSignFile.exe",
}


@dataclass
class DayZToolsPaths:
    root: Path | None = None
    binarize: Path | None = None
    cfgconvert: Path | None = None
    imagetopaa: Path | None = None
    dssignfile: Path | None = None

    @property
    def is_complete(self) -> bool:
        return all([self.binarize, self.cfgconvert, self.imagetopaa, self.dssignfile])

    def as_settings_dict(self) -> dict[str, str]:
        return {
            "binarize_exe": str(self.binarize) if self.binarize else "",
            "cfgconvert_exe": str(self.cfgconvert) if self.cfgconvert else "",
            "imagetopaa_exe": str(self.imagetopaa) if self.imagetopaa else "",
            "dssignfile_exe": str(self.dssignfile) if self.dssignfile else "",
        }


def detect() -> DayZToolsPaths:
    """Walk every Steam library and return the first DayZ Tools install we find."""
    for root in _enumerate_dayztools_roots():
        paths = _resolve_tools_in_root(root)
        if paths.is_complete:
            return paths
        # If even partially populated, return what we have.
        if any([paths.binarize, paths.cfgconvert, paths.imagetopaa, paths.dssignfile]):
            return paths
    return DayZToolsPaths()


def _enumerate_dayztools_roots() -> list[Path]:
    roots: list[Path] = []
    for library in _steam_libraries():
        candidate = library / "steamapps" / "common" / DAYZTOOLS_FOLDER
        if candidate.is_dir():
            roots.append(candidate)
    # Common fallback installs outside Steam libraries.
    for env_var in ("ProgramFiles", "ProgramFiles(x86)"):
        env_val = os.environ.get(env_var)
        if env_val:
            candidate = Path(env_val) / DAYZTOOLS_FOLDER
            if candidate.is_dir() and candidate not in roots:
                roots.append(candidate)
    return roots


def _steam_libraries() -> list[Path]:
    """Return every directory listed as a Steam library, including custom drives."""
    libraries: list[Path] = []
    steam_root = _find_steam_root()
    if steam_root is None:
        return libraries
    libraries.append(steam_root)

    vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
    if not vdf_path.is_file():
        return libraries
    try:
        text = vdf_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return libraries

    # libraryfolders.vdf uses "path" "C:\\Some\\Path" lines per library entry.
    for match in re.finditer(r'"path"\s+"([^"]+)"', text, flags=re.IGNORECASE):
        raw = match.group(1).replace("\\\\", "\\")
        path = Path(raw)
        if path.is_dir() and path not in libraries:
            libraries.append(path)
    return libraries


def _find_steam_root() -> Path | None:
    # Registry lookup first
    try:
        import winreg  # type: ignore
        for hive, key_name in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        ):
            try:
                with winreg.OpenKey(hive, key_name) as key:
                    for value_name in ("SteamPath", "InstallPath"):
                        try:
                            value, _ = winreg.QueryValueEx(key, value_name)
                        except FileNotFoundError:
                            continue
                        candidate = Path(str(value))
                        if candidate.is_dir():
                            return candidate
            except FileNotFoundError:
                continue
    except ImportError:
        # Non-Windows fallback (mostly for CI test runs)
        pass

    for env_var in ("ProgramFiles(x86)", "ProgramFiles"):
        env_val = os.environ.get(env_var)
        if env_val:
            candidate = Path(env_val) / "Steam"
            if candidate.is_dir():
                return candidate
    return None


def _resolve_tools_in_root(root: Path) -> DayZToolsPaths:
    paths = DayZToolsPaths(root=root)
    for attr, rel in TOOL_SUBPATHS.items():
        candidate = root / rel
        if candidate.is_file():
            setattr(paths, attr, candidate)
    return paths


# ---------------------------------------------------------------------------
# Tool runners
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


def run_tool(exe: Path, args: list[str], timeout: int = 600,
             cwd: Path | None = None) -> ToolResult:
    """Run an external DayZ Tool with no console window and decoded output.

    Output decoding is forgiving: DayZ Tools occasionally emit bytes outside
    cp1252 and a strict decode would crash the builder. We decode with
    ``errors='replace'`` so the build log keeps flowing.
    """
    completed = subprocess.run(
        [str(exe), *args],
        capture_output=True,
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
        creationflags=_no_console_flags(),
    )
    return ToolResult(
        returncode=completed.returncode,
        stdout=_decode_safe(completed.stdout),
        stderr=_decode_safe(completed.stderr),
    )


def _decode_safe(raw: bytes) -> str:
    if not raw:
        return ""
    for encoding in ("utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _no_console_flags() -> int:
    try:
        return subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    except AttributeError:
        return 0
