"""Preflight checks for DayZ addons.

A preflight catches the common addon problems before a broken PBO is
produced. Each check produces zero or more :class:`Finding` records that the
GUI/log/report consumers display.

The design is a small rule engine: each check is a function that takes a
:class:`PreflightContext` and yields findings. Toggles in
:class:`PreflightOptions` decide which checks run.

This implementation focuses on practical text-mode checks that do not need
the actual binarize/cfgconvert tools. Heavier checks (config.cpp syntax via
CfgConvert) are gated on the tool being available.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Iterable

from citadel.builder.discovery import AddonTarget
from citadel.core import dayz_tools, prefix as prefix_mod
from citadel.core.log import Logger
from citadel.core.paths import is_excluded, iter_files


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Level(IntEnum):
    INFO = 0
    WARN = 1
    ERROR = 2


@dataclass
class Finding:
    level: Level
    message: str
    rule: str
    addon: str
    file: str = ""
    line: int | None = None

    def formatted(self) -> str:
        location = ""
        if self.file:
            location = f" [{self.file}"
            if self.line:
                location += f":{self.line}"
            location += "]"
        level_label = {Level.INFO: "INFO", Level.WARN: "WARNING", Level.ERROR: "ERROR"}[self.level]
        return f"{level_label}: {self.message}{location}"

    def to_dict(self) -> dict:
        return {
            "level": ["info", "warning", "error"][int(self.level)],
            "message": self.message,
            "rule": self.rule,
            "addon": self.addon,
            "file": self.file,
            "line": self.line,
        }


@dataclass
class PreflightOptions:
    required_addons_hints: bool = True
    texture_freshness: bool = True
    risky_path_names: bool = True
    case_conflicts: bool = True
    p3d_internal_scan: bool = True
    terrain_wrp_checks: bool = True
    terrain_navmesh_checks: bool = True
    wrp_internal_scan: bool = False
    terrain_source_export_warnings: bool = True
    terrain_layer_checks: bool = True
    map_2d_config_checks: bool = True
    terrain_size_checks: bool = True
    script_checks: bool = True
    exclude_patterns: list[str] = field(default_factory=list)


@dataclass
class PreflightContext:
    addon: AddonTarget
    options: PreflightOptions
    cfgconvert: Path | None = None
    findings: list[Finding] = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)


# ---------------------------------------------------------------------------
# Reference scanning patterns
# ---------------------------------------------------------------------------

# Path-like literals inside text configs / scripts. We capture quoted strings
# that look like file paths with one of the recognized extensions.
REFERENCE_EXTENSIONS = (
    ".paa", ".rvmat", ".p3d", ".wss", ".ogg", ".cfg", ".cpp", ".hpp", ".h",
    ".emat", ".edds", ".ptc", ".shp", ".dbf", ".shx", ".prj",
)

REFERENCE_RE = re.compile(
    r'"((?:[A-Za-z]:[\\/])?[A-Za-z0-9_\-./\\]+\.(?:' +
    "|".join(ext[1:] for ext in REFERENCE_EXTENSIONS) +
    r'))"',
    flags=re.IGNORECASE,
)

LINE_NUMBER_TEXT_EXTENSIONS = {".cpp", ".h", ".hpp", ".rvmat", ".cfg", ".c",
                               ".layout", ".xml", ".json"}

# Common terrain source/export file types we want to warn about.
SOURCE_EXPORT_EXTENSIONS = {".pew", ".tv4p", ".tv4l", ".asc", ".xyz", ".raw",
                            ".tif", ".tiff", ".psd", ".png", ".tga", ".lbt"}

RISKY_PATH_PATTERN = re.compile(r'[<>:"|?*\x00-\x1f]')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_preflight(addon: AddonTarget, options: PreflightOptions,
                  cfgconvert: Path | None, logger: Logger | None = None) -> list[Finding]:
    ctx = PreflightContext(addon=addon, options=options, cfgconvert=cfgconvert)

    if logger:
        logger.section(f"Preflight {addon.name}")

    # Run each rule. Failure in one rule must not stop the rest.
    for rule in _ALL_RULES:
        try:
            rule(ctx)
        except Exception as exc:
            ctx.add(Finding(Level.ERROR, f"Preflight rule crashed: {exc}",
                            rule=rule.__name__, addon=addon.name))

    if logger:
        warn = sum(1 for f in ctx.findings if f.level == Level.WARN)
        err = sum(1 for f in ctx.findings if f.level == Level.ERROR)
        for finding in ctx.findings:
            line = finding.formatted()
            if finding.level == Level.ERROR:
                logger.error(line)
            elif finding.level == Level.WARN:
                logger.warn(line)
            else:
                logger.info(line)
        if err:
            logger.error(f"{addon.name}: preflight produced {err} error(s), {warn} warning(s)")
        elif warn:
            logger.warn(f"{addon.name}: preflight produced {warn} warning(s)")
        else:
            logger.success(f"{addon.name}: preflight clean")

    return ctx.findings


def export_report(findings: list[Finding], addon_name: str, out_dir: Path) -> tuple[Path, Path]:
    """Write a ``.txt`` + ``.json`` report and return both paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = out_dir / f"preflight_{addon_name}_{stamp}"

    txt_path = base.with_suffix(".txt")
    with txt_path.open("w", encoding="utf-8") as fh:
        fh.write(f"Citadel PBO Tools - Preflight report\n")
        fh.write(f"Addon: {addon_name}\n")
        fh.write(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
        fh.write(f"Findings: {len(findings)}\n")
        fh.write("=" * 64 + "\n\n")
        for finding in findings:
            fh.write(finding.formatted() + "\n")

    json_path = base.with_suffix(".json")
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump({
            "addon": addon_name,
            "generated": datetime.now().isoformat(timespec="seconds"),
            "findings": [f.to_dict() for f in findings],
            "summary": {
                "total": len(findings),
                "errors": sum(1 for f in findings if f.level == Level.ERROR),
                "warnings": sum(1 for f in findings if f.level == Level.WARN),
                "infos": sum(1 for f in findings if f.level == Level.INFO),
            },
        }, fh, indent=2)

    return txt_path, json_path


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def _rule_prefix_sanity(ctx: PreflightContext) -> None:
    info = prefix_mod.read_prefix(ctx.addon.source, fallback_name=ctx.addon.name)
    if info.is_multiple:
        names = ", ".join(p.name for p in info.source_files)
        ctx.add(Finding(Level.WARN, f"Multiple PBO prefix files present: {names}",
                        rule="prefix.multiple", addon=ctx.addon.name))
    if not info.prefix:
        ctx.add(Finding(Level.WARN, "No PBO prefix detected; falling back to addon name",
                        rule="prefix.missing", addon=ctx.addon.name))
        return
    if prefix_mod.looks_like_drive_path(info.prefix):
        ctx.add(Finding(Level.ERROR, f"Prefix '{info.prefix}' looks like a drive path",
                        rule="prefix.drive_path", addon=ctx.addon.name))
    if prefix_mod.has_forward_slashes(info.prefix):
        ctx.add(Finding(Level.WARN, f"Prefix '{info.prefix}' contains forward slashes (use backslashes)",
                        rule="prefix.slashes", addon=ctx.addon.name))
    if prefix_mod.has_leading_or_trailing_slash(info.prefix):
        ctx.add(Finding(Level.WARN, f"Prefix '{info.prefix}' has leading or trailing slashes",
                        rule="prefix.surrounding_slash", addon=ctx.addon.name))


def _rule_config_present(ctx: PreflightContext) -> None:
    root_cfg = ctx.addon.source / "config.cpp"
    root_bin = ctx.addon.source / "config.bin"
    if not root_cfg.is_file() and not root_bin.is_file() and not ctx.addon.has_wrp:
        ctx.add(Finding(Level.WARN, "No root config.cpp, config.bin, or .wrp found",
                        rule="config.missing", addon=ctx.addon.name))


def _rule_config_syntax(ctx: PreflightContext) -> None:
    if ctx.cfgconvert is None:
        return
    for cfg in _find_configs(ctx.addon.source, ctx.options.exclude_patterns):
        result = dayz_tools.run_tool(ctx.cfgconvert, ["-txt", "-dst", str(cfg.with_suffix(".cpp.preflight.tmp")), str(cfg)])
        tmp = cfg.with_suffix(".cpp.preflight.tmp")
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        if not result.succeeded:
            detail = (result.stderr.strip() or result.stdout.strip())
            ctx.add(Finding(Level.ERROR, f"config.cpp syntax error: {detail}",
                            rule="config.syntax", addon=ctx.addon.name,
                            file=str(cfg.relative_to(ctx.addon.source))))


def _rule_cfg_patches(ctx: PreflightContext) -> None:
    root_cfg = ctx.addon.source / "config.cpp"
    if not root_cfg.is_file():
        return
    text = _safe_read(root_cfg)
    if "class CfgPatches" not in text:
        ctx.add(Finding(Level.WARN, "config.cpp has no CfgPatches block",
                        rule="config.cfg_patches.missing", addon=ctx.addon.name,
                        file="config.cpp"))
        return
    if not ctx.options.required_addons_hints:
        return
    # Look for a requiredAddons[] inside CfgPatches.
    if not re.search(r"requiredAddons\s*\[\s*\]\s*=\s*\{", text):
        ctx.add(Finding(Level.WARN, "CfgPatches: requiredAddons[] not found",
                        rule="config.required_addons.missing", addon=ctx.addon.name,
                        file="config.cpp"))


def _rule_modded_class_no_base(ctx: PreflightContext) -> None:
    if not ctx.options.script_checks:
        return
    # `modded class` in DayZ script files should NOT declare a base class.
    pattern = re.compile(r"^\s*modded\s+class\s+\w+\s*(?:extends|:)", re.IGNORECASE)
    for path in iter_files(ctx.addon.source, ctx.options.exclude_patterns):
        if path.suffix.lower() != ".c":
            continue
        text = _safe_read(path)
        for line_no, line in enumerate(text.splitlines(), start=1):
            if pattern.match(line):
                ctx.add(Finding(Level.ERROR, "modded class declaration must not specify a base class",
                                rule="script.modded_class.base", addon=ctx.addon.name,
                                file=str(path.relative_to(ctx.addon.source)),
                                line=line_no))


def _rule_references_exist(ctx: PreflightContext) -> None:
    excludes = ctx.options.exclude_patterns
    file_index = _build_file_index(ctx.addon.source, excludes)
    pbo_paths_present = {key.lower() for key in file_index}

    for path in iter_files(ctx.addon.source, excludes):
        suffix = path.suffix.lower()
        if suffix not in (".cpp", ".hpp", ".h", ".rvmat", ".cfg", ".c", ".layout"):
            continue
        text = _safe_read(path)
        rel_str = str(path.relative_to(ctx.addon.source))
        for match in REFERENCE_RE.finditer(text):
            referenced = match.group(1)
            referenced_clean = referenced.replace("/", "\\")
            line_no = text.count("\n", 0, match.start()) + 1 if suffix in {f".{ext}".lstrip(".") for ext in LINE_NUMBER_TEXT_EXTENSIONS} else None
            normalized = referenced_clean.lower()
            # Heuristic: anything beginning with a known top-level addon prefix
            # such as ``rag_xxx\foo.paa`` is checked against the addon-relative
            # paths. We do not warn for external addon refs (we have no project
            # root to resolve them).
            if "\\" in normalized:
                last_seg = normalized.split("\\")[-1]
            else:
                last_seg = normalized
            if last_seg in pbo_paths_present:
                continue
            # Try addon-relative resolve.
            candidate = (path.parent / referenced_clean.replace("\\", "/")).resolve()
            try:
                candidate_rel = candidate.relative_to(ctx.addon.source.resolve())
                if str(candidate_rel).replace("\\", "/").lower() in {k.replace("\\", "/").lower() for k in file_index}:
                    continue
            except ValueError:
                pass
            # Looks like a same-addon reference (starts with addon name) and missing.
            if normalized.startswith(ctx.addon.name.lower() + "\\"):
                ctx.add(Finding(Level.ERROR,
                                f"Missing referenced file: {referenced}",
                                rule="references.missing", addon=ctx.addon.name,
                                file=rel_str, line=line_no))


def _rule_excluded_references(ctx: PreflightContext) -> None:
    excludes = ctx.options.exclude_patterns
    if not excludes:
        return
    all_files = {str(p.relative_to(ctx.addon.source)).replace("\\", "/").lower()
                 for p in iter_files(ctx.addon.source, [])}
    packed = {str(p.relative_to(ctx.addon.source)).replace("\\", "/").lower()
              for p in iter_files(ctx.addon.source, excludes)}
    excluded_paths = all_files - packed
    if not excluded_paths:
        return
    for path in iter_files(ctx.addon.source, excludes):
        if path.suffix.lower() not in (".cpp", ".hpp", ".h", ".rvmat", ".cfg", ".c"):
            continue
        text = _safe_read(path)
        for match in REFERENCE_RE.finditer(text):
            referenced = match.group(1).replace("/", "\\")
            normalized = referenced.lower().replace("\\", "/")
            if normalized in excluded_paths:
                line_no = text.count("\n", 0, match.start()) + 1
                ctx.add(Finding(Level.WARN,
                                f"Referenced file is excluded from the PBO: {referenced}",
                                rule="references.excluded", addon=ctx.addon.name,
                                file=str(path.relative_to(ctx.addon.source)),
                                line=line_no))


def _rule_risky_paths(ctx: PreflightContext) -> None:
    if not ctx.options.risky_path_names:
        return
    for path in iter_files(ctx.addon.source, ctx.options.exclude_patterns):
        rel = str(path.relative_to(ctx.addon.source))
        if RISKY_PATH_PATTERN.search(rel):
            ctx.add(Finding(Level.WARN, f"Risky character(s) in path: {rel}",
                            rule="paths.risky", addon=ctx.addon.name, file=rel))
        if " " in rel:
            # Spaces are legal but worth flagging for terrain dependency lookups.
            pass


def _rule_case_conflicts(ctx: PreflightContext) -> None:
    if not ctx.options.case_conflicts:
        return
    seen: dict[str, str] = {}
    for path in iter_files(ctx.addon.source, ctx.options.exclude_patterns):
        rel = str(path.relative_to(ctx.addon.source))
        key = rel.lower()
        if key in seen and seen[key] != rel:
            ctx.add(Finding(Level.ERROR,
                            f"Case-only path conflict: {rel} vs {seen[key]}",
                            rule="paths.case_conflict", addon=ctx.addon.name, file=rel))
        else:
            seen[key] = rel


def _rule_texture_freshness(ctx: PreflightContext) -> None:
    if not ctx.options.texture_freshness:
        return
    for path in iter_files(ctx.addon.source, ctx.options.exclude_patterns):
        if path.suffix.lower() not in (".png", ".tga"):
            continue
        paa = path.with_suffix(".paa")
        if paa.is_file() and paa.stat().st_mtime < path.stat().st_mtime - 1:
            rel = str(path.relative_to(ctx.addon.source))
            ctx.add(Finding(Level.WARN,
                            f".paa older than source texture: {rel}",
                            rule="textures.stale", addon=ctx.addon.name, file=rel))


def _rule_odol_p3d(ctx: PreflightContext) -> None:
    if not ctx.options.p3d_internal_scan:
        return
    for path in iter_files(ctx.addon.source, ctx.options.exclude_patterns):
        if path.suffix.lower() != ".p3d":
            continue
        try:
            with path.open("rb") as fh:
                head = fh.read(4)
        except OSError:
            continue
        if head.startswith(b"ODOL"):
            rel = str(path.relative_to(ctx.addon.source))
            ctx.add(Finding(Level.INFO,
                            f"Pre-binarized ODOL .p3d in source tree: {rel}",
                            rule="p3d.odol_source", addon=ctx.addon.name, file=rel))


def _rule_terrain_source_export(ctx: PreflightContext) -> None:
    if not ctx.options.terrain_source_export_warnings or not ctx.addon.has_wrp:
        return
    risky_total = 0
    for path in iter_files(ctx.addon.source, ctx.options.exclude_patterns):
        suffix = path.suffix.lower()
        if suffix in SOURCE_EXPORT_EXTENSIONS:
            risky_total += 1
            top = _top_level_folder(path, ctx.addon.source)
            if top.lower() in {"source", "export", "exports", "terrainbuilder", "tb"}:
                rel = str(path.relative_to(ctx.addon.source))
                ctx.add(Finding(Level.WARN,
                                f"Terrain source/export file may bloat PBO: {rel}",
                                rule="terrain.source_file", addon=ctx.addon.name, file=rel))
    if risky_total > 0 and ctx.options.terrain_size_checks:
        ctx.add(Finding(Level.INFO, f"{risky_total} potential source/export file(s) detected",
                        rule="terrain.source_total", addon=ctx.addon.name))


def _rule_terrain_size_breakdown(ctx: PreflightContext) -> None:
    if not ctx.options.terrain_size_checks or not ctx.addon.has_wrp:
        return
    sizes: dict[str, int] = {}
    for path in iter_files(ctx.addon.source, ctx.options.exclude_patterns):
        top = _top_level_folder(path, ctx.addon.source) or "<root>"
        try:
            sizes[top] = sizes.get(top, 0) + path.stat().st_size
        except OSError:
            continue
    if not sizes:
        return
    for folder, size in sorted(sizes.items(), key=lambda kv: -kv[1])[:10]:
        if size >= 1 << 30:
            level = Level.WARN
        else:
            level = Level.INFO
        ctx.add(Finding(level, f"Size: {folder}: {_human_size(size)}",
                        rule="terrain.size", addon=ctx.addon.name))


def _rule_terrain_world_name(ctx: PreflightContext) -> None:
    if not ctx.options.terrain_wrp_checks or not ctx.addon.has_wrp:
        return
    config = ctx.addon.source / "config.cpp"
    if not config.is_file():
        return
    text = _safe_read(config)
    if "CfgWorlds" not in text:
        ctx.add(Finding(Level.WARN, "Terrain addon has no CfgWorlds block",
                        rule="terrain.cfg_worlds.missing", addon=ctx.addon.name,
                        file="config.cpp"))
    matches = list(re.finditer(r'worldName\s*=\s*"([^"]+)"', text))
    if len(matches) > 1:
        ctx.add(Finding(Level.WARN, f"Multiple worldName entries in config.cpp ({len(matches)})",
                        rule="terrain.world_name.multiple", addon=ctx.addon.name,
                        file="config.cpp"))
    for match in matches:
        world_name = match.group(1).replace("/", "\\")
        wrp_target_name = Path(world_name.split("\\")[-1])
        line_no = text.count("\n", 0, match.start()) + 1
        # Confirm the referenced .wrp exists somewhere in the addon tree.
        found = False
        for path in iter_files(ctx.addon.source, ctx.options.exclude_patterns):
            if path.name.lower() == wrp_target_name.name.lower() and path.suffix.lower() == ".wrp":
                found = True
                break
        if not found:
            ctx.add(Finding(Level.ERROR,
                            f"worldName points to non-existent .wrp: {world_name}",
                            rule="terrain.world_name.missing_wrp", addon=ctx.addon.name,
                            file="config.cpp", line=line_no))


def _rule_terrain_navmesh(ctx: PreflightContext) -> None:
    if not ctx.options.terrain_navmesh_checks or not ctx.addon.has_wrp:
        return
    navmesh_dir = None
    for candidate in ("navmesh", "data/navmesh", "world/navmesh"):
        path = ctx.addon.source / candidate
        if path.is_dir():
            navmesh_dir = path
            break
    if navmesh_dir is None:
        ctx.add(Finding(Level.WARN, "No navmesh folder detected (development build OK)",
                        rule="terrain.navmesh.missing", addon=ctx.addon.name))
        return
    files = list(iter_files(navmesh_dir, ctx.options.exclude_patterns))
    if not files:
        ctx.add(Finding(Level.WARN, "Navmesh folder is empty after exclusions",
                        rule="terrain.navmesh.empty", addon=ctx.addon.name))


_ALL_RULES = (
    _rule_prefix_sanity,
    _rule_config_present,
    _rule_config_syntax,
    _rule_cfg_patches,
    _rule_modded_class_no_base,
    _rule_references_exist,
    _rule_excluded_references,
    _rule_risky_paths,
    _rule_case_conflicts,
    _rule_texture_freshness,
    _rule_odol_p3d,
    _rule_terrain_source_export,
    _rule_terrain_size_breakdown,
    _rule_terrain_world_name,
    _rule_terrain_navmesh,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_configs(root: Path, excludes: list[str]) -> Iterable[Path]:
    for path in iter_files(root, excludes):
        if path.name.lower() == "config.cpp":
            yield path


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _build_file_index(root: Path, excludes: list[str]) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in iter_files(root, excludes):
        rel = str(path.relative_to(root)).replace("\\", "/")
        index[rel] = path
        index[path.name] = path  # bare-name lookup
    return index


def _top_level_folder(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return ""
    parts = rel.parts
    return parts[0] if len(parts) > 1 else ""


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
