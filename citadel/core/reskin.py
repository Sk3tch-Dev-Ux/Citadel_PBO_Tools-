"""DayZ retexture (reskin) support.

A *reskin* replaces one or more ``.paa`` textures inside an existing (vanilla or
mod) PBO with your own images, then repacks the result so DayZ loads your art in
place of the original. This composes the pieces the toolkit already has —
:mod:`citadel.core.pbo` (extract/pack), DayZ Tools ``ImageToPAA`` (image → .paa),
and :mod:`citadel.core.signing` (DSSignFile) — behind a small registry.

Model
-----
* :class:`ReskinEntry` — one mapping: an internal ``.paa`` path inside the source
  PBO → a local replacement image (``.paa``/``.png``/``.tga``).
* :class:`ReskinTarget` — a source PBO plus its entries. A :func:`save_registry`
  / :func:`load_registry` pair persists a list of targets as JSON.
* :func:`build_reskin` — extract the source, overwrite the mapped textures
  (converting non-``.paa`` images via an injected converter), repack preserving
  the original prefix/properties, and optionally sign.

Image conversion and signing are injected as callables so the core is unit-
testable without DayZ Tools installed; :func:`make_image_converter` wires the
real ``ImageToPAA`` when you have it.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from citadel.core import pbo
from citadel.core.paths import normalize_pbo_path

PAA_SUFFIX = ".paa"
IMAGE_SUFFIXES = {".paa", ".png", ".tga"}


class ReskinError(Exception):
    """Raised when a reskin cannot be built."""


@dataclass
class ReskinEntry:
    """Replace the texture at ``internal_path`` (inside the source PBO) with the
    image at ``replacement`` (a local ``.paa``/``.png``/``.tga`` file)."""

    internal_path: str
    replacement: str


@dataclass
class ReskinTarget:
    name: str
    source_pbo: str
    entries: list[ReskinEntry] = field(default_factory=list)


@dataclass
class ReskinResult:
    output_pbo: Path
    applied: list[str]
    missing: list[str]
    signed: bool = False
    bisign: Path | None = None


# ---------------------------------------------------------------------------
# Registry persistence
# ---------------------------------------------------------------------------

def save_registry(path: str | Path, targets: list[ReskinTarget]) -> None:
    """Persist a list of reskin targets to ``path`` as JSON."""
    data = [
        {"name": t.name, "source_pbo": t.source_pbo,
         "entries": [asdict(e) for e in t.entries]}
        for t in targets
    ]
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_registry(path: str | Path) -> list[ReskinTarget]:
    """Load reskin targets previously written by :func:`save_registry`."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    targets: list[ReskinTarget] = []
    for t in raw:
        entries = [
            ReskinEntry(internal_path=e["internal_path"], replacement=e["replacement"])
            for e in t.get("entries", [])
        ]
        targets.append(ReskinTarget(name=t.get("name", ""), source_pbo=t["source_pbo"], entries=entries))
    return targets


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_target(target: ReskinTarget, *, archive: pbo.PboArchive | None = None) -> list[str]:
    """Return a list of human-readable problems with ``target`` (empty = OK).

    Pass an already-parsed ``archive`` of the source PBO to also verify that each
    ``internal_path`` actually exists in it.
    """
    errors: list[str] = []
    src = Path(target.source_pbo)
    if not src.is_file():
        errors.append(f"Source PBO not found: {src}")
    if not target.entries:
        errors.append("No reskin entries defined")

    names_in_pbo = None
    if archive is not None:
        names_in_pbo = {normalize_pbo_path(e.name).lower() for e in archive.entries}

    for e in target.entries:
        if not e.internal_path.lower().endswith(PAA_SUFFIX):
            errors.append(f"Target is not a .paa texture: {e.internal_path}")
        rep = Path(e.replacement)
        if not rep.is_file():
            errors.append(f"Replacement image not found: {rep}")
        elif rep.suffix.lower() not in IMAGE_SUFFIXES:
            errors.append(f"Unsupported replacement image type: {rep.name}")
        if names_in_pbo is not None and normalize_pbo_path(e.internal_path).lower() not in names_in_pbo:
            errors.append(f"Texture not present in source PBO: {e.internal_path}")

    return errors


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_reskin(
    target: ReskinTarget,
    output_pbo: str | Path,
    *,
    work_dir: str | Path | None = None,
    convert_image: Callable[[Path, Path], None] | None = None,
    sign: Callable[[Path], object] | None = None,
) -> ReskinResult:
    """Build a reskinned copy of ``target.source_pbo`` at ``output_pbo``.

    :param work_dir: scratch directory for extraction; a temp dir is created and
        removed automatically when omitted.
    :param convert_image: ``(src_image, dest_paa) -> None`` used for non-``.paa``
        replacements. Required only if any replacement isn't already a ``.paa``.
    :param sign: ``(pbo_path) -> result`` invoked after packing (e.g. wrapping
        :func:`citadel.core.signing.sign_pbo`). Only called when at least one
        texture was applied.
    :raises ReskinError: if a non-``.paa`` replacement is given without a
        converter.
    """
    source = Path(target.source_pbo)
    if not source.is_file():
        raise FileNotFoundError(f"Source PBO not found: {source}")
    output_pbo = Path(output_pbo)

    tmp_created = work_dir is None
    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="citadel_reskin_"))
    try:
        extracted = work / "extracted"
        archive = pbo.read_pbo(source)
        pbo.extract_all(archive, extracted)

        present = {normalize_pbo_path(e.name).lower() for e in archive.entries}
        applied: list[str] = []
        missing: list[str] = []

        for entry in target.entries:
            norm = normalize_pbo_path(entry.internal_path)
            if norm.lower() not in present:
                missing.append(entry.internal_path)
                continue
            dest = extracted / norm.replace("\\", os.sep)
            rep = Path(entry.replacement)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if rep.suffix.lower() == PAA_SUFFIX:
                shutil.copyfile(rep, dest)
            elif convert_image is not None:
                convert_image(rep, dest)
                if not dest.is_file():
                    raise ReskinError(f"Converter did not produce {dest}")
            else:
                raise ReskinError(
                    f"{rep.name} needs .paa conversion but no converter was provided"
                )
            applied.append(entry.internal_path)

        # Repack preserving the original prefix/product/version (carried in the
        # archive properties) so the reskin loads exactly where the original did.
        writer = pbo.PboWriter(properties=dict(archive.properties))
        writer.add_folder(extracted)
        writer.write(output_pbo)

        signed = False
        bisign = None
        if sign is not None and applied:
            res = sign(output_pbo)
            signed = True
            bisign = getattr(res, "bisign", None)

        return ReskinResult(output_pbo=output_pbo, applied=applied, missing=missing,
                            signed=signed, bisign=bisign)
    finally:
        if tmp_created:
            shutil.rmtree(work, ignore_errors=True)


def make_image_converter(image_to_paa_exe: str | Path) -> Callable[[Path, Path], None]:
    """Build a ``convert_image`` callable driving DayZ Tools' ImageToPAA.

    Kept out of :func:`build_reskin` so the core stays testable without the
    toolchain installed.
    """
    from citadel.core.dayz_tools import run_tool

    def _convert(src: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        result = run_tool(Path(image_to_paa_exe), [str(src), str(dest)])
        if not dest.is_file():
            stderr = getattr(result, "stderr", "") or ""
            raise ReskinError(f"ImageToPAA failed for {src.name}: {stderr[:300]}")

    return _convert
