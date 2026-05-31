"""Build pipeline orchestration.

Pipeline per addon:

  1. Stage selected files into a per-addon temp folder.
  2. Apply exclude patterns and drop prefix helper files.
  3. (Optional) Update missing/stale .paa files from .png/.tga sources.
  4. (Optional) Binarize .p3d and .wrp files via DayZ Tools.
  5. (Optional) Convert root + nested config.cpp files to config.bin.
  6. Pack the staged folder into a .pbo using PboWriter.
  7. (Optional) Sign the .pbo via DSSignFile.
  8. Safe-publish into the final output folder (with backup/restore).
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from citadel.builder.discovery import AddonTarget
from citadel.core import cache, dayz_tools, pbo, prefix, signing
from citadel.core.log import Logger
from citadel.core.paths import ensure_dir, is_excluded, iter_files, matches_any
from citadel_version import VERSION_STRING


@dataclass
class BuildOptions:
    """User-controlled flags driving the pipeline."""

    binarize_p3d: bool = True
    binarize_wrp: bool = True
    convert_cpp_to_bin: bool = True
    update_paa: bool = False
    sign_pbos: bool = True
    copy_bikey: bool = True
    force_rebuild: bool = False
    skip_unchanged: bool = True
    safe_publish: bool = True
    verify_outputs: bool = True
    binarize_workers: int = 0  # 0 = auto
    exclude_patterns: list[str] = field(default_factory=list)
    binarize_addon_folders: list[str] = field(default_factory=list)


@dataclass
class ToolPaths:
    """All external DayZ Tool paths the pipeline needs."""

    binarize: Path | None = None
    cfgconvert: Path | None = None
    imagetopaa: Path | None = None
    dssignfile: Path | None = None
    private_key: Path | None = None


@dataclass
class AddonBuildResult:
    addon: AddonTarget
    pbo_path: Path | None = None
    bisign_path: Path | None = None
    bikey_path: Path | None = None
    skipped: bool = False
    success: bool = False
    error: str | None = None
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.finished_at - self.started_at)


class CancelToken:
    """Cooperative cancellation handle for long-running builds."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def request_cancel(self) -> None:
        self._event.set()

    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise BuildCancelled()


class BuildCancelled(Exception):
    pass


ProgressCallback = Callable[[str, float], None]  # (status text, fraction 0..1)


class BuildPipeline:
    """Orchestrate per-addon builds end-to-end."""

    def __init__(self, output_root: Path, temp_root: Path,
                 tools: ToolPaths, options: BuildOptions, logger: Logger) -> None:
        self.output_root = output_root
        self.temp_root = temp_root
        self.tools = tools
        self.options = options
        self.logger = logger

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def build_many(self, addons: list[AddonTarget],
                   cancel: CancelToken | None = None,
                   progress: ProgressCallback | None = None) -> list[AddonBuildResult]:
        cancel = cancel or CancelToken()
        results: list[AddonBuildResult] = []
        addons_dir = ensure_dir(self.output_root / "Addons")
        keys_dir = ensure_dir(self.output_root / "Keys") if self.options.copy_bikey else None

        total = len(addons)
        for index, addon in enumerate(addons):
            cancel.check()
            if progress:
                progress(f"Building {addon.name}", index / max(1, total))
            result = self.build_one(addon, addons_dir, keys_dir, cancel)
            results.append(result)

        if progress:
            progress("Build complete", 1.0)
        return results

    # ------------------------------------------------------------------
    # Single-addon build
    # ------------------------------------------------------------------
    def build_one(self, addon: AddonTarget, addons_dir: Path,
                  keys_dir: Path | None, cancel: CancelToken) -> AddonBuildResult:
        result = AddonBuildResult(addon=addon, started_at=time.time())
        self.logger.section(f"Building {addon.name}")
        try:
            cache_key = cache.CacheKey(
                addon_path=str(addon.source.resolve()),
                output_path=str(self.output_root.resolve()),
            )
            fingerprint = cache.fingerprint_addon(addon.source, self.options.exclude_patterns)

            if (self.options.skip_unchanged and not self.options.force_rebuild
                    and cache.is_unchanged(cache_key, fingerprint)
                    and self._published_outputs_exist(addons_dir, addon.name)):
                self.logger.info(f"{addon.name}: unchanged, skipped (use Force rebuild to override)")
                result.skipped = True
                result.success = True
                result.pbo_path = addons_dir / f"{addon.name}.pbo"
                result.finished_at = time.time()
                return result

            # 1. Stage
            staging = self._fresh_addon_temp(addon.name) / "staging"
            ensure_dir(staging)
            staged_files = self._stage_files(addon, staging)
            cancel.check()

            # 2. PAA update (in staging)
            if self.options.update_paa and self.tools.imagetopaa:
                self._update_paa(staging)
                cancel.check()

            # 3. Binarize
            if self.options.binarize_p3d or self.options.binarize_wrp:
                if self.tools.binarize:
                    self._binarize(staging, addon, cancel)
                else:
                    self.logger.warn("Binarize.exe is not configured — skipping binarize step")
            cancel.check()

            # 4. CfgConvert
            if self.options.convert_cpp_to_bin:
                if self.tools.cfgconvert:
                    self._convert_configs(staging)
                else:
                    self.logger.warn("CfgConvert.exe is not configured — leaving config.cpp as-is")
            cancel.check()

            # 5. Pack
            built_pbo = self._pack(addon, staging, cancel)
            cancel.check()

            # 6. Sign
            sign_result = None
            if self.options.sign_pbos and self.tools.dssignfile and self.tools.private_key:
                sign_result = signing.sign_pbo(
                    built_pbo,
                    self.tools.private_key,
                    self.tools.dssignfile,
                    keys_dir if self.options.copy_bikey else None,
                )
                self.logger.success(f"Signed: {sign_result.bisign_path.name}")
                if sign_result.bikey_path:
                    self.logger.info(f"Copied .bikey: {sign_result.bikey_path.name}")
            elif self.options.sign_pbos:
                self.logger.warn(f"{addon.name}: signing requested but DSSignFile/private key missing")

            # 7. Publish
            published = self._publish(built_pbo, sign_result, addons_dir)
            result.pbo_path = published
            if sign_result:
                result.bisign_path = published.with_name(f"{published.name}.{self.tools.private_key.stem}.bisign")  # type: ignore[union-attr]
                result.bikey_path = sign_result.bikey_path

            cache.remember(cache_key, fingerprint, {"pbo": str(published)})
            result.success = True
            self.logger.success(f"{addon.name} built in {time.time() - result.started_at:.1f}s")
        except BuildCancelled:
            self.logger.warn(f"{addon.name}: build cancelled")
            result.error = "Cancelled"
        except Exception as exc:
            self.logger.error(f"{addon.name}: {exc}")
            result.error = str(exc)
            # Always clean per-addon temp on failure so half-built junk does not leak.
            self._cleanup_addon_temp_safely(addon.name)
        finally:
            result.finished_at = time.time()
        return result

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------
    def _fresh_addon_temp(self, addon_name: str) -> Path:
        addon_temp = self.temp_root / "addons" / addon_name
        if addon_temp.exists():
            shutil.rmtree(addon_temp, ignore_errors=True)
        ensure_dir(addon_temp)
        return addon_temp

    def _cleanup_addon_temp_safely(self, addon_name: str) -> None:
        addon_temp = self.temp_root / "addons" / addon_name
        if addon_temp.exists():
            shutil.rmtree(addon_temp, ignore_errors=True)

    def _stage_files(self, addon: AddonTarget, staging: Path) -> list[Path]:
        """Copy addon sources into ``staging`` honoring exclude patterns and dropping prefix files."""
        staged: list[Path] = []
        excludes = list(self.options.exclude_patterns)
        prefix_names_lower = {p.name.lower() for p in addon.prefix_files}

        for path in iter_files(addon.source, excludes):
            rel = path.relative_to(addon.source)
            rel_str = str(rel)
            if path.name.lower() in prefix_names_lower:
                continue  # prefix helper files do not get packed
            if is_excluded(rel_str, excludes):
                continue
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            staged.append(target)
        self.logger.info(f"{addon.name}: staged {len(staged)} files")
        return staged

    def _update_paa(self, staging: Path) -> None:
        """Convert stale or missing .paa files in staging from .png/.tga sources."""
        if not self.tools.imagetopaa:
            return
        converted = 0
        for image in list(iter_files(staging, [])):
            if image.suffix.lower() not in (".png", ".tga"):
                continue
            paa = image.with_suffix(".paa")
            if paa.is_file() and paa.stat().st_mtime >= image.stat().st_mtime:
                continue
            self.logger.tool(f"ImageToPAA: {image.relative_to(staging)}")
            result = dayz_tools.run_tool(self.tools.imagetopaa, [str(image), str(paa)])
            if result.succeeded:
                converted += 1
            else:
                self.logger.warn(f"ImageToPAA failed for {image.name}: {result.stderr.strip() or result.stdout.strip()}")
        if converted:
            self.logger.info(f"Updated {converted} .paa file(s) in staging")

    def _binarize(self, staging: Path, addon: AddonTarget, cancel: CancelToken) -> None:
        """Run Binarize on .p3d (and .wrp) files inside the staging folder."""
        if not self.tools.binarize:
            return
        # ODOL .p3d files are already binarized — skip them to avoid access violations.
        targets: list[Path] = []
        for path in iter_files(staging, []):
            suffix = path.suffix.lower()
            if suffix == ".p3d" and self.options.binarize_p3d and not _is_odol_p3d(path):
                targets.append(path)
            elif suffix == ".wrp" and self.options.binarize_wrp:
                targets.append(path)
        if not targets:
            return

        worker_count = self.options.binarize_workers or (os.cpu_count() or 4)
        worker_count = max(1, min(worker_count, len(targets)))
        self.logger.info(f"Binarize: {len(targets)} file(s) with {worker_count} worker(s)")

        binarize_exe = self.tools.binarize
        scan_args = []
        for folder in self.options.binarize_addon_folders:
            scan_args.extend(["-addonsPath", folder])

        warn_count = 0
        err_count = 0

        def _run_one(target: Path) -> tuple[Path, dayz_tools.ToolResult]:
            tmp_out = target.with_suffix(target.suffix + ".bin.tmp")
            args = [*scan_args, str(target), str(tmp_out)]
            result = dayz_tools.run_tool(binarize_exe, args, timeout=900)
            if result.succeeded and tmp_out.is_file() and tmp_out.stat().st_size > 0:
                # Replace original with binarized output in place.
                target.unlink(missing_ok=True)
                tmp_out.rename(target)
            else:
                # Clean up partial output.
                tmp_out.unlink(missing_ok=True)
            return target, result

        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = [pool.submit(_run_one, t) for t in targets]
            for future in as_completed(futures):
                cancel.check()
                target, result = future.result()
                if result.succeeded:
                    self.logger.tool(f"Binarized {target.name}")
                else:
                    err_count += 1
                    detail = result.stderr.strip() or result.stdout.strip()
                    self.logger.error(f"Binarize failed for {target.name}: {detail or 'no output'}")
                # Surface non-fatal warnings.
                if result.stdout:
                    for line in result.stdout.splitlines():
                        low = line.lower()
                        if "warning" in low:
                            warn_count += 1

        if warn_count:
            self.logger.warn(f"Binarize emitted {warn_count} warning(s)")
        if err_count:
            raise RuntimeError(f"Binarize failed for {err_count} file(s)")

        # Terrain WRP verification — refuse suspiciously tiny WRP output.
        if self.options.binarize_wrp and self.options.verify_outputs:
            for target in targets:
                if target.suffix.lower() == ".wrp" and target.stat().st_size < 1024:
                    raise RuntimeError(
                        f"Binarize produced a suspiciously small {target.name} ({target.stat().st_size} bytes); refusing to pack"
                    )

    def _convert_configs(self, staging: Path) -> None:
        """Convert root and nested config.cpp files into config.bin."""
        if not self.tools.cfgconvert:
            return
        configs = [p for p in iter_files(staging, []) if p.name.lower() == "config.cpp"]
        if not configs:
            return
        self.logger.info(f"CfgConvert: {len(configs)} config.cpp file(s)")
        for cfg in configs:
            output = cfg.with_name("config.bin")
            args = ["-bin", "-dst", str(output), str(cfg)]
            result = dayz_tools.run_tool(self.tools.cfgconvert, args)
            if result.succeeded and output.is_file() and output.stat().st_size > 0:
                self.logger.tool(f"Converted {cfg.relative_to(staging)} -> config.bin")
                cfg.unlink(missing_ok=True)
            else:
                detail = result.stderr.strip() or result.stdout.strip() or "no output"
                raise RuntimeError(f"CfgConvert failed for {cfg.relative_to(staging)}: {detail}")

    def _pack(self, addon: AddonTarget, staging: Path, cancel: CancelToken) -> Path:
        """Pack ``staging`` into a temporary .pbo and return its path."""
        addon_temp = self.temp_root / "addons" / addon.name
        temp_pbo = addon_temp / f"{addon.name}.pbo"
        prefix_info = prefix.read_prefix(addon.source, fallback_name=addon.name)

        writer = pbo.PboWriter(
            prefix=prefix_info.prefix,
            product=f"Citadel PBO Builder v{VERSION_STRING}",
            version=VERSION_STRING,
        )
        for path in iter_files(staging, []):
            rel = path.relative_to(staging)
            writer.add_file(path, str(rel))
        cancel.check()
        writer.write(temp_pbo)
        self.logger.info(f"Packed {writer.entry_count()} entries into {temp_pbo.name}")
        return temp_pbo

    # ------------------------------------------------------------------
    # Safe publishing
    # ------------------------------------------------------------------
    def _publish(self, built_pbo: Path, sign_result: signing.SignResult | None,
                 addons_dir: Path) -> Path:
        """Replace any prior PBO + signatures with the new build, backing up first."""
        final_pbo = addons_dir / built_pbo.name
        backups: list[tuple[Path, Path]] = []  # (final, backup)

        # ---- Backup existing artifacts ----
        if self.options.safe_publish:
            for candidate in _publish_set(addons_dir, built_pbo.name):
                if candidate.is_file():
                    backup_path = candidate.with_suffix(candidate.suffix + ".citadel-bak")
                    try:
                        shutil.copy2(candidate, backup_path)
                        backups.append((candidate, backup_path))
                    except OSError as exc:
                        raise RuntimeError(f"Backup failed for {candidate.name}: {exc}") from exc
            # Validation: every backup must really exist before we touch published outputs.
            for _, backup_path in backups:
                if not backup_path.is_file():
                    raise RuntimeError(f"Backup missing pre-publish: {backup_path.name}")

        try:
            # ---- Replace ----
            shutil.copy2(built_pbo, final_pbo)
            if sign_result is not None:
                shutil.copy2(sign_result.bisign_path,
                             final_pbo.with_name(sign_result.bisign_path.name))

            if self.options.verify_outputs and not final_pbo.is_file():
                raise RuntimeError(f"Published PBO missing after publish: {final_pbo.name}")
        except Exception:
            # Try to restore backups so we leave the published folder in its prior state.
            for original, backup_path in backups:
                try:
                    shutil.copy2(backup_path, original)
                except OSError:
                    self.logger.error(f"Failed to restore backup for {original.name}")
            raise
        finally:
            # Cleanup backups on success.
            for _, backup_path in backups:
                try:
                    backup_path.unlink(missing_ok=True)
                except OSError:
                    pass

        return final_pbo

    def _published_outputs_exist(self, addons_dir: Path, addon_name: str) -> bool:
        return (addons_dir / f"{addon_name}.pbo").is_file()


def _publish_set(addons_dir: Path, pbo_name: str) -> list[Path]:
    """Files that should be backed up + replaced together as a publish set."""
    result = [addons_dir / pbo_name]
    base = pbo_name + "."
    for child in addons_dir.iterdir():
        if child.is_file() and child.name.startswith(base) and child.suffix.lower() == ".bisign":
            result.append(child)
    return result


def _is_odol_p3d(path: Path) -> bool:
    """Detect already-binarized ODOL .p3d files by magic bytes."""
    try:
        with path.open("rb") as fh:
            head = fh.read(8)
    except OSError:
        return False
    return head.startswith(b"ODOL")
