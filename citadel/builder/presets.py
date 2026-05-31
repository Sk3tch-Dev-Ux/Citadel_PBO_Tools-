"""Named Project Source and Build Output presets.

Presets are stored separately so source and output paths can be mixed freely
(matches RaG's UX). Loading a Project Source preset does not change Build
Output, and vice versa.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from citadel.core.settings import load_json, presets_path, save_json


PresetKind = Literal["source", "output"]


@dataclass
class Preset:
    kind: PresetKind
    name: str
    path: str


def _load_all() -> dict:
    data = load_json(presets_path(), {"source": {}, "output": {}})
    data.setdefault("source", {})
    data.setdefault("output", {})
    return data


def _save_all(data: dict) -> None:
    save_json(presets_path(), data)


def list_presets(kind: PresetKind) -> list[Preset]:
    data = _load_all()
    section = data.get(kind, {})
    return [Preset(kind=kind, name=name, path=path)
            for name, path in sorted(section.items(), key=lambda kv: kv[0].lower())]


def add_preset(kind: PresetKind, name: str, path: str) -> None:
    name = name.strip()
    if not name:
        raise ValueError("Preset name cannot be empty")
    data = _load_all()
    data[kind][name] = path
    _save_all(data)


def remove_preset(kind: PresetKind, name: str) -> bool:
    data = _load_all()
    if name in data.get(kind, {}):
        del data[kind][name]
        _save_all(data)
        return True
    return False


def rename_preset(kind: PresetKind, old_name: str, new_name: str) -> bool:
    new_name = new_name.strip()
    if not new_name:
        return False
    data = _load_all()
    section = data.get(kind, {})
    if old_name not in section:
        return False
    section[new_name] = section.pop(old_name)
    _save_all(data)
    return True


def get_preset(kind: PresetKind, name: str) -> Preset | None:
    data = _load_all()
    path = data.get(kind, {}).get(name)
    if path is None:
        return None
    return Preset(kind=kind, name=name, path=path)
