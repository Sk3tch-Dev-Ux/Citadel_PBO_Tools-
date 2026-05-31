"""Centralized version info for Citadel PBO Tools.

Update this file to bump the version across the entire project — the GUI
About windows, the release packager, and the publish workflow all read from
here.
"""

from __future__ import annotations

APP_NAME = "Citadel PBO Tools"
BUILDER_NAME = "Citadel PBO Builder"
INSPECTOR_NAME = "Citadel PBO Inspector"

VERSION = "1.0.0"
RELEASE_STAGE = "Beta"

COMPANY = "Citadel"
COPYRIGHT = "Copyright (c) Citadel. All rights reserved."

VERSION_STRING = f"{VERSION} {RELEASE_STAGE}" if RELEASE_STAGE else VERSION


def builder_title() -> str:
    return f"{BUILDER_NAME}  v{VERSION_STRING}"


def inspector_title() -> str:
    return f"{INSPECTOR_NAME}  v{VERSION_STRING}"
