"""
Compatibility shim.

Old selective_context_patch used old canon/* and state/academy_schedule.json.
It is intentionally neutralized. Active selective context is provided by runtime patches.
"""

from __future__ import annotations

from typing import Any
from app import compact as base

app = base.app
RUNTIME_DIGEST_FILE = "runtime/scene_context_digest.md"


def active_scene_characters(current: dict[str, Any], future: dict[str, Any] | None = None) -> list[str]:
    return base.active_scene_characters(current, future)


def recommended_files_for_context(current: dict[str, Any] | None = None, future: dict[str, Any] | None = None) -> list[str]:
    return base.recommended_files_for_context(current, future)


def compact_relationships(state: Any, focus_ids: list[str]) -> Any:
    return base.compact_relationships(state, focus_ids)


def compact_story_lines(state: Any, focus_ids: list[str]) -> Any:
    return base.compact_story_lines(state, focus_ids)


def compact_knowledge(state: Any, focus_ids: list[str]) -> Any:
    return base.compact_knowledge(state, focus_ids)


def patch_after_routes() -> None:
    return None
