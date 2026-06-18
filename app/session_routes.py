"""
Compatibility shim.

Legacy imports used to look for app.session_routes. The active runtime is now
loaded through scene_packet_runtime_patch, which imports the existing Academy
runtime and adds the Variant A scene-packet endpoint.

This file intentionally does not register old legacy endpoints.
"""

from __future__ import annotations

from typing import Any

from app.scene_packet_runtime_patch import app, build_scene_packet
from app import compact as base


def active_scene_characters(current: dict[str, Any], future: dict[str, Any] | None = None) -> list[str]:
    return base.active_scene_characters(current, future)


def recommended_files_for_context(current: dict[str, Any] | None = None, future: dict[str, Any] | None = None) -> list[str]:
    return base.recommended_files_for_context(current, future)


def scene_packet_payload(session_id: str, max_chars: int = 42000) -> dict[str, Any]:
    """Small helper for legacy tests/imports that need the new Variant A packet."""
    packet = build_scene_packet(session_id, max_chars=max_chars)
    return packet.model_dump()
