"""
Calendar context runtime patch v13.

This patch keeps the existing runtime pipeline but replaces the old
state/academy_schedule.json calendar source with:

- state/calendar_runtime.json
- calendar/calendar_index.yaml
- calendar/days/{current_date}.yaml

The visible scene format reminder now matches the current old Academy header.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import app.context_transport_runtime_patch as rt
from app.context_transport_runtime_patch import app
from app import compact as base
import app.compact_context_patch as ccp

app.version = "0.3.43-calendar-format-clean-v13"

CALENDAR_INDEX_FILE = "calendar/calendar_index.yaml"
CALENDAR_RUNTIME_FILE = "state/calendar_runtime.json"


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


def _cut_text(text: str, limit: int = 9000) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n...<truncated>"


def build_calendar_slice_v2(current: dict[str, Any], session_id: str) -> dict[str, Any]:
    runtime = base.read_json(CALENDAR_RUNTIME_FILE, session_id, default={}) or {}
    current_date = str(current.get("current_date") or runtime.get("current_date") or "")
    current_time = str(current.get("current_time") or "")
    day_file = str(runtime.get("current_day_file") or current.get("current_day_file") or (f"calendar/days/{current_date}.yaml" if current_date else ""))
    index_text = _read_text_optional(CALENDAR_INDEX_FILE, session_id=session_id)
    day_text = _read_text_optional(day_file, session_id=session_id) if day_file else ""
    return {
        "calendar_mode": "calendar_module_v1",
        "current_date": current_date,
        "current_time": current_time,
        "calendar_source": CALENDAR_INDEX_FILE,
        "calendar_runtime_file": CALENDAR_RUNTIME_FILE,
        "current_day_file": day_file,
        "current_beat_id": runtime.get("current_beat_id") or current.get("current_beat_id"),
        "completed_beat_ids": runtime.get("completed_beat_ids", []),
        "skipped_beat_ids": runtime.get("skipped_beat_ids", []),
        "introduced_character_ids": runtime.get("introduced_character_ids", []),
        "calendar_check_rule": [
            "Use current_date from state/current_state.json first.",
            "Read calendar/calendar_index.yaml, then the current day file.",
            "Calendar entries are important hooks, not full scene prose.",
            "If a character is listed in first_introduction_ids or required beat character_ids, introduce them when that beat is reached.",
            "If a character is not listed in the current day file, that does not forbid them from appearing.",
            "After first introduction, a character may appear on later days if it is logical and interesting.",
            "Before first introduction, do not actively introduce a character without player/state/calendar override.",
            "All characters must act strictly according to loaded character files.",
            "Do not turn the calendar into a dry academy guide.",
            "Do not overfill a day; if saturated, guide toward evening/sleep/next meaningful beat.",
        ],
        "calendar_index_yaml": _cut_text(index_text, 7000),
        "current_day_yaml": _cut_text(day_text, 9000),
    }


def build_scene_context_digest(session_id: str) -> str:
    current = base.read_json("state/current_state.json", session_id, default={}) or {}
    future = base.read_json("state/future_locks_progress.json", session_id, default={}) or {}
    chars = rt.scene_character_ids(current, future)
    relationships = rt.compact_relationships_scene_pairs_only(base.read_json("state/relationships.json", session_id, default={}) or {}, chars)
    story_lines = rt.compact_story_lines_scene_only(base.read_json("state/story_lines.json", session_id, default={}) or {}, chars)
    knowledge = rt.compact_knowledge_scene_only(base.read_json("state/knowledge_state.json", session_id, default={}) or {}, chars)
    inventory = base.compact_if_large(base.read_json("state/inventory_state.json", session_id, default={}) or {}, 2200)
    calendar_slice = build_calendar_slice_v2(current, session_id)
    rule_digest = {
        "output": [
            "Gameplay only: no API/status/debug summary in final answer.",
            "Scene must start with the current old Academy visual-novel header, not the obsolete loose 🗓️ card header.",
            "Header: 🏛️ Академия Астрейн · date, then 🕒 time · 📍 location, 🌦️ weather, ⚙️ active scene state, then ✦/🧥/◈ lines and separator.",
            "Dialogue format: **Name/descriptor** — speech. (*short italic remark*)",
            "Descriptions are separate italic paragraphs.",
            "Akira thoughts only in bottom block, not inside the scene body.",
            "Bottom blocks use ✦ headings.",
            "No empty scene: add hook/reaction/conflict/consequence or time skip.",
            "Do not answer with technical commentary after a gameplay scene.",
        ],
        "calendar": [
            "Calendar module is source of date hooks.",
            "Use calendar/day YAML as hooks, not as ready-made prose.",
            "Character absence from day file is not a ban after first introduction.",
            "Character presence in a required beat makes the introduction/appearance required when that beat is reached.",
            "If the day is saturated, guide toward ending the day rather than adding filler.",
        ],
        "state_write": [
            "Backend does not infer state from prose.",
            "If relationships/story/knowledge/current_state/calendar_runtime change, send explicit state payload to apply-turn-result.",
            "Roster lists are replacement fields, not append-only fields.",
        ],
    }
    text = "# Runtime scene context digest\n"
    text += "This digest replaces heavy global prompt/canon/state files for normal gameplay. Use exact character files also loaded in required_files.\n"
    text += rt.MEDIUM_STYLE_FORMAT_DIGEST + "\n"
    text += rt.MEDIUM_ENGINE_DIGEST + "\n"
    text += rt.MEDIUM_SOURCE_USAGE_DIGEST + "\n"
    text += rt.MEDIUM_RELATIONSHIP_DIGEST + "\n"
    text += rt._json_block("Rule digest", rule_digest, 4200)
    text += rt._json_block("Scene character ids", chars, 1200)
    text += rt._json_block("Current state", current, 4600)
    text += rt._json_block("Relationship slice", relationships, 5600)
    text += rt._json_block("Story lines slice", story_lines, 7600)
    text += rt._json_block("Knowledge slice", knowledge, 5200)
    text += rt._json_block("Inventory slice", inventory, 2200)
    text += rt._json_block("Calendar slice", calendar_slice, 12000)
    text += "\n## State update reminder\nIf scene changes roster, use current_state_changes with roster fields as full replacement lists. If calendar progress changes, update state/calendar_runtime.json explicitly.\n"
    return text


rt.build_calendar_slice_v2 = build_calendar_slice_v2
rt.build_scene_context_digest = build_scene_context_digest
rt.app.version = app.version
ccp._read_required_file_for_bundle = rt.read_required_file_for_bundle
