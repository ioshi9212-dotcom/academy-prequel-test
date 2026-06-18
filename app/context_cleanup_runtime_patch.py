"""
Context cleanup runtime patch v14.

Compatibility layer:
- seeds new calendar/ and canon_lore/ roots;
- allows apply-turn-result to save state/calendar_runtime.json;
- replaces old compact /context academy_schedule snapshot with active calendar snapshot;
- prevents old hidden bond path from being preferred over canon_lore hidden bond;
- patches state_write_runtime_patch summary to recognize calendar runtime changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import app.context_transport_runtime_patch as rt
from app.context_transport_runtime_patch import app
from app import compact as base

app.version = "0.3.31-context-cleanup-v14"

CONTEXT_CLEANUP_LOCK = "gpt/locks/context_cleanup_lock.md"
CALENDAR_RUNTIME_FILE = "state/calendar_runtime.json"


def _add_unique_list_attr(module: Any, attr: str, values: list[str]) -> None:
    current = list(getattr(module, attr, []) or [])
    for value in values:
        if value not in current:
            current.append(value)
    setattr(module, attr, current)


# Make new roots participate in DATA seeding. This must run before startup seed().
_add_unique_list_attr(base, "SYNC_FROM_REPO", ["calendar", "canon_lore"])
_add_unique_list_attr(base, "STATE_SEED", ["state"])

# Let apply-turn-result update calendar progress.
calendar_state_entry = (
    CALENDAR_RUNTIME_FILE,
    ["calendar_runtime_changes", "calendar_runtime", "calendar_state_changes", "calendar_state"],
)
state_map = list(getattr(base, "STATE_SECTION_MAP", []) or [])
if not any(item and item[0] == CALENDAR_RUNTIME_FILE for item in state_map):
    state_map.append(calendar_state_entry)
base.STATE_SECTION_MAP = state_map

for lock_path in [CONTEXT_CLEANUP_LOCK, "gpt/locks/calendar_usage_lock.md", "gpt/locks/lore_usage_lock.md"]:
    if lock_path not in rt.MINIMAL_LOCK_FILES:
        rt.MINIMAL_LOCK_FILES.append(lock_path)


def _read_text_optional(path: str, session_id: str | None = None) -> str:
    safe_path = str(path or "").strip()
    if not safe_path:
        return ""
    try:
        return base.read_text(safe_path, session_id=session_id)
    except Exception:
        pass
    for root in [getattr(base, "DATA", None), getattr(base, "ROOT", None)]:
        if not root:
            continue
        try:
            file_path = Path(root) / base.safe(safe_path)
            if file_path.exists() and file_path.is_file():
                return file_path.read_text(encoding="utf-8")
        except Exception:
            continue
    return ""


def _compact_text(text: str, limit: int = 3500) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n...<truncated>"


_ORIGINAL_CHARACTER_LOCK_FILES = getattr(base, "character_lock_files", None)


def character_lock_files_clean(scene_chars: list[str]) -> list[str]:
    files: list[str] = []
    if callable(_ORIGINAL_CHARACTER_LOCK_FILES):
        files.extend(_ORIGINAL_CHARACTER_LOCK_FILES(scene_chars))
    files = [path for path in files if path != "canon/hidden_raiden_akira_bond.md"]
    normalized = {rt.canonical_id(cid) for cid in scene_chars}
    if {"akira", "raiden"} <= normalized:
        files.append("canon_lore/hidden/raiden_akira_bond.yaml")
    result: list[str] = []
    for path in files:
        if path and path not in result and base.repo_file_exists(path):
            result.append(path)
    return result


base.character_lock_files = character_lock_files_clean

_ORIGINAL_CONTEXT_PAYLOAD = getattr(base, "context_payload", None)


def context_payload_clean(session_id: str | None = None):
    if callable(_ORIGINAL_CONTEXT_PAYLOAD):
        payload = _ORIGINAL_CONTEXT_PAYLOAD(session_id)
    else:
        payload = None

    current = base.read_json("state/current_state.json", session_id, default={}) or {}
    calendar_runtime = base.read_json(CALENDAR_RUNTIME_FILE, session_id, default={}) or {}
    current_date = current.get("current_date") or calendar_runtime.get("current_date")
    current_day_file = calendar_runtime.get("current_day_file") or (f"calendar/days/{current_date}.yaml" if current_date else "")

    active_calendar_snapshot = {
        "mode": "calendar_module_v1",
        "calendar_runtime": calendar_runtime,
        "calendar_index_file": "calendar/calendar_index.yaml",
        "current_day_file": current_day_file,
        "current_day_yaml": _compact_text(_read_text_optional(current_day_file, session_id=session_id), 3500),
        "note": "This field replaces old state/academy_schedule.json in compact /context. Use calendar runtime + day file as active schedule source.",
    }

    if payload is not None and hasattr(payload, "model_copy"):
        return payload.model_copy(update={"academy_schedule": active_calendar_snapshot})
    if payload is not None and hasattr(payload, "copy"):
        try:
            return payload.copy(update={"academy_schedule": active_calendar_snapshot})
        except Exception:
            pass
    if isinstance(payload, dict):
        payload["academy_schedule"] = active_calendar_snapshot
        return payload
    return payload


base.context_payload = context_payload_clean

try:
    import app.state_write_runtime_patch as swp  # type: ignore

    _ORIGINAL_STATE_PAYLOAD_SECTION_SUMMARY = swp.state_payload_section_summary

    def state_payload_section_summary_with_calendar(payload: dict[str, Any]) -> dict[str, bool]:
        summary = _ORIGINAL_STATE_PAYLOAD_SECTION_SUMMARY(payload)
        summary["calendar_runtime_changes"] = bool(
            base.find_section(payload, ["calendar_runtime_changes", "calendar_runtime", "calendar_state_changes", "calendar_state"])
        )
        return summary

    swp.state_payload_section_summary = state_payload_section_summary_with_calendar
except Exception:
    pass
