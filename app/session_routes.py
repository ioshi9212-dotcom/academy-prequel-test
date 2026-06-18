"""
Compatibility shim.

Old session_routes registered legacy routes and old required files.
The active routes are registered by compact_context_patch and runtime patches.
This file remains import-safe and does not register legacy endpoints.
"""

from __future__ import annotations

from typing import Any
from app import compact as base

app = base.app


def active_scene_characters(current: dict[str, Any], future: dict[str, Any] | None = None) -> list[str]:
    return base.active_scene_characters(current, future)


def recommended_files_for_context(current: dict[str, Any] | None = None, future: dict[str, Any] | None = None) -> list[str]:
    return base.recommended_files_for_context(current, future)
