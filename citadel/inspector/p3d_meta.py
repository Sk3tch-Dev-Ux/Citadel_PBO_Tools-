"""Best-effort metadata inspection for .p3d (ODOL / MLOD) files.

This is intentionally a metadata scan, not a debinarizer. We expose:

  - Format (MLOD or ODOL) and version number
  - LOD count and resolution list when ODOL exposes it
  - Strings that look like texture / material / proxy paths
  - Animation reference strings

For full model.cfg recovery use Mikero DeP3d / ExtractModelCfg.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class P3dInfo:
    path: Path
    format: str = "Unknown"
    version: int | None = None
    lod_count: int | None = None
    lod_resolutions: list[float] = field(default_factory=list)
    textures: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    proxies: list[str] = field(default_factory=list)
    animations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Path:        {self.path}",
            f"Format:      {self.format}{' v' + str(self.version) if self.version is not None else ''}",
        ]
        if self.lod_count is not None:
            lines.append(f"LODs:        {self.lod_count}")
        if self.lod_resolutions:
            lines.append("LOD list:    " + ", ".join(f"{r:.1f}" for r in self.lod_resolutions))
        if self.textures:
            lines.append(f"Textures ({len(self.textures)}):")
            lines.extend(f"  {t}" for t in self.textures[:64])
            if len(self.textures) > 64:
                lines.append(f"  ... +{len(self.textures) - 64} more")
        if self.materials:
            lines.append(f"Materials ({len(self.materials)}):")
            lines.extend(f"  {m}" for m in self.materials[:64])
            if len(self.materials) > 64:
                lines.append(f"  ... +{len(self.materials) - 64} more")
        if self.proxies:
            lines.append(f"Proxies ({len(self.proxies)}):")
            lines.extend(f"  {p}" for p in self.proxies[:32])
            if len(self.proxies) > 32:
                lines.append(f"  ... +{len(self.proxies) - 32} more")
        if self.animations:
            lines.append(f"Animations ({len(self.animations)}):")
            lines.extend(f"  {a}" for a in self.animations[:32])
        if self.notes:
            lines.append("")
            lines.extend(self.notes)
        return "\n".join(lines)


_STRING_RE = re.compile(rb"[\x20-\x7e]{4,}")
_TEXTURE_EXTS = (".paa", ".pac")
_MATERIAL_EXTS = (".rvmat",)
_PROXY_PREFIX = "proxy:"
_ANIM_HINTS = ("anim", "rtm", "skeleton")


def inspect_p3d(path: Path) -> P3dInfo:
    info = P3dInfo(path=path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        info.notes.append(f"Could not read file: {exc}")
        return info

    head = data[:8]
    if head.startswith(b"ODOL"):
        info.format = "ODOL"
        try:
            info.version = struct.unpack_from("<I", data, 4)[0]
        except struct.error:
            info.version = None
        _try_parse_odol_resolutions(info, data)
    elif head.startswith(b"MLOD"):
        info.format = "MLOD"
        try:
            info.version = struct.unpack_from("<I", data, 4)[0]
        except struct.error:
            info.version = None
        info.notes.append("MLOD models are source-form; use Object Builder to inspect LODs.")
    else:
        info.notes.append("Unknown header signature; falling back to string scan only.")

    # String harvest — categorize what looks like content references.
    seen_tex: set[str] = set()
    seen_mat: set[str] = set()
    seen_proxy: set[str] = set()
    seen_anim: set[str] = set()
    for match in _STRING_RE.finditer(data):
        try:
            text = match.group(0).decode("latin-1", errors="replace")
        except Exception:
            continue
        low = text.lower()
        if low.endswith(_TEXTURE_EXTS):
            seen_tex.add(text)
        elif low.endswith(_MATERIAL_EXTS):
            seen_mat.add(text)
        elif low.startswith(_PROXY_PREFIX):
            seen_proxy.add(text)
        elif any(hint in low for hint in _ANIM_HINTS) and low.endswith(".rtm"):
            seen_anim.add(text)
    info.textures = sorted(seen_tex)
    info.materials = sorted(seen_mat)
    info.proxies = sorted(seen_proxy)
    info.animations = sorted(seen_anim)
    return info


def _try_parse_odol_resolutions(info: P3dInfo, data: bytes) -> None:
    """Pull the LOD resolution float array out of an ODOL header if possible.

    The exact ODOL layout varies by version. We restrict ourselves to versions
    where the resolution array is straightforward (v40+). For older or
    unrecognized versions we skip silently and rely on the string scan.
    """
    if info.version is None:
        return
    if info.version < 40 or info.version > 73:
        return
    try:
        # Layout for many ODOL versions:
        #   "ODOL" (4) + version u32 (4) + useLodFlag u32 (4) + lod_count u32 (4)
        # then float[lod_count] of LOD resolutions.
        lod_count = struct.unpack_from("<I", data, 12)[0]
        if 0 < lod_count <= 256:
            resolutions = struct.unpack_from(f"<{lod_count}f", data, 16)
            if all(-1e9 < r < 1e9 for r in resolutions):
                info.lod_count = lod_count
                info.lod_resolutions = list(resolutions)
    except struct.error:
        return
