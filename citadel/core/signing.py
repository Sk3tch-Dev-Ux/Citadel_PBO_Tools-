"""Wrapper for DayZ Tools ``DSSignFile.exe`` and ``.bikey`` management.

Signing is delegated to DSSignFile because that is the only signature
implementation accepted by the engine. We:

  - Resolve the matching ``.bikey`` from the configured ``.biprivatekey``.
  - Call ``DSSignFile.exe <privkey> <pbo>``.
  - Verify the resulting ``.bisign`` exists next to the PBO.
  - Copy the ``.bikey`` into the build output's ``Keys/`` folder.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SignResult:
    pbo_path: Path
    bisign_path: Path
    bikey_path: Path | None


class SigningError(Exception):
    """Raised when signing fails (missing tools, missing keys, non-zero exit)."""


def find_matching_bikey(privatekey: Path) -> Path | None:
    """Try to locate the ``.bikey`` next to a ``.biprivatekey``.

    DayZ Tools' ``KeysGen.exe`` produces both keys side-by-side and they share
    a base name. We accept either ``X.bikey`` next to ``X.biprivatekey`` or
    the conventional sibling.
    """
    candidate = privatekey.with_suffix(".bikey")
    if candidate.is_file():
        return candidate
    # Some workflows store the .bikey in a sibling directory.
    parent = privatekey.parent
    stem = privatekey.stem
    for sibling in parent.iterdir():
        if sibling.is_file() and sibling.suffix.lower() == ".bikey" and sibling.stem == stem:
            return sibling
    return None


def sign_pbo(pbo: Path, privatekey: Path, dssignfile_exe: Path,
             keys_output_dir: Path | None = None,
             timeout: int = 120) -> SignResult:
    """Sign ``pbo`` and optionally copy the matching ``.bikey`` to ``keys_output_dir``."""
    if not dssignfile_exe.is_file():
        raise SigningError(f"DSSignFile.exe not found: {dssignfile_exe}")
    if not privatekey.is_file():
        raise SigningError(f"Private key not found: {privatekey}")
    if not pbo.is_file():
        raise SigningError(f"PBO not found for signing: {pbo}")

    completed = subprocess.run(
        [str(dssignfile_exe), str(privatekey), str(pbo)],
        capture_output=True,
        timeout=timeout,
        creationflags=_no_console_flags(),
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        stdout = completed.stdout.decode("utf-8", errors="replace").strip()
        raise SigningError(
            f"DSSignFile returned {completed.returncode}: "
            f"{stderr or stdout or 'no output'}"
        )

    bisign = _expected_bisign_path(pbo, privatekey)
    if not bisign.is_file():
        # DSSignFile may produce a slightly different filename in older versions.
        # Search the pbo's directory for the newest .bisign matching the pbo name.
        bisign = _find_bisign_for_pbo(pbo, privatekey)
        if bisign is None or not bisign.is_file():
            raise SigningError(f"DSSignFile reported success but no .bisign found for {pbo.name}")

    bikey_copied: Path | None = None
    if keys_output_dir is not None:
        bikey_copied = _copy_bikey(privatekey, keys_output_dir)

    return SignResult(pbo_path=pbo, bisign_path=bisign, bikey_path=bikey_copied)


def _expected_bisign_path(pbo: Path, privatekey: Path) -> Path:
    """DSSignFile names the output ``<pbo>.<keyname>.bisign``."""
    return pbo.with_name(f"{pbo.name}.{privatekey.stem}.bisign")


def _find_bisign_for_pbo(pbo: Path, privatekey: Path) -> Path | None:
    parent = pbo.parent
    prefix = f"{pbo.name}."
    newest: Path | None = None
    newest_mtime = -1.0
    for child in parent.iterdir():
        if not child.is_file():
            continue
        if child.suffix.lower() == ".bisign" and child.name.startswith(prefix):
            try:
                mtime = child.stat().st_mtime
            except OSError:
                continue
            if mtime > newest_mtime:
                newest_mtime = mtime
                newest = child
    return newest


def _copy_bikey(privatekey: Path, keys_output_dir: Path) -> Path | None:
    bikey = find_matching_bikey(privatekey)
    if bikey is None:
        return None
    keys_output_dir.mkdir(parents=True, exist_ok=True)
    target = keys_output_dir / bikey.name
    if target.exists():
        # Preserve existing .bikey — the spec says do not overwrite.
        return target
    shutil.copy2(bikey, target)
    return target


def _no_console_flags() -> int:
    """Return Windows subprocess creation flags to suppress a flashing console."""
    try:
        return subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    except AttributeError:
        return 0
