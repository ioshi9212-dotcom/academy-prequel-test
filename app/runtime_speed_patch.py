"""
Runtime speed patch v17.

Goals:
- replace many old lock files with one compact runtime_scene_rules_digest.md;
- reduce full character loading to characters truly present in the scene;
- treat scheduled scene appearances as active characters for required files;
- keep relationship slice limited to active/nearby scene focus;
- keep delayed/mentioned characters as context inside digest, not full YAML files;
- include last 15 gameplay scene texts only when exact 15-turn audit is due;
- shrink runtime/scene_context_digest.md by using compact calendar/lore slices.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import app.context_transport_runtime_patch as rt
from app.context_transport_runtime_patch import app
from app import compact as base
import app.compact_context_patch as ccp

app.version = "0.3.37-runtime-speed-relationship-focus-v17"

RUNTIME_SCENE_RULES_DIGEST = "gpt/locks/runtime_scene_rules_digest.md"
RUNTIME_DIGEST_FILE = "runtime/scene_context_digest.md"

# Old locks remain in repo but are no longer pulled as individual required files.
rt.MINIMAL_LOCK_FILES = [RUNTIME_SCENE_RULES_DIGEST]


def _unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = rt.canonical_id(value)
        if item and item not in result:
            result.append(item)
    return result


ACTIVE_CHARACTER_FIELDS = [
    "active_characters",
    "nearby_characters",
    "speaking_character_ids",
    "observing_character_ids",
    "addressed_character_ids",
    "looked_at_character_ids",
    # Calendar/current-beat appearances are scene participants for required files.
    # This prevents missing character cards for scheduled arrivals.
    "scheduled_character_ids",
]

RELATIONSHIP_FOCUS_CHARACTER_FIELDS = [
    "active_characters",
    "nearby_characters",
    "speaking_character_ids",
    "observing_character_ids",
    "addressed_character_ids",
    "looked_at_character_ids",
]

BACKGROUND_CHARACTER_FIELDS = [
    "mentioned_character_ids",
    "delayed_character_ids",
]


PAST_TRIGGER_WORDS = [
    "прошл", "детств", "школ", "кай", "пожар", "травм", "перерожд",
    "памят", "старая тройка", "отец", "семь", "эксперимент", "самуэль",
]


def _scene_character_ids_from_fields(
    current: dict[str, Any],
    future: dict[str, Any],
    fields: list[str],
) -> list[str]:
    values: list[Any] = ["akira"]

    for field in fields:
        current_values = current.get(field, []) or []
        if isinstance(current_values, list):
            values.extend(current_values)

    for thread in current.get("open_threads", []) or []:
        if isinstance(thread, dict) and thread.get("status") in {"due", "active", "triggered"}:
            values.extend(thread.get("participants", []) or [])

    for lock in (future.get("locks") or {}).values():
        if not isinstance(lock, dict):
            continue
        if lock.get("status") not in {"due", "active", "triggered"}:
            continue
        values.extend(lock.get("participants", []) or [])

    return _unique(values)


def active_scene_character_ids_fast(current: dict[str, Any] | None = None, future: dict[str, Any] | None = None) -> list[str]:
    current = current or {}
    future = future or {}
    return _scene_character_ids_from_fields(current, future, ACTIVE_CHARACTER_FIELDS)


def relationship_focus_character_ids_fast(current: dict[str, Any] | None = None, future: dict[str, Any] | None = None) -> list[str]:
    current = current or {}
    future = future or {}
    return _scene_character_ids_from_fields(current, future, RELATIONSHIP_FOCUS_CHARACTER_FIELDS)


def background_character_ids(current: dict[str, Any] | None = None) -> dict[str, list[str]]:
    current = current or {}
    result: dict[str, list[str]] = {}
    for field in BACKGROUND_CHARACTER_FIELDS:
        values = current.get(field, []) or []
        if isinstance(values, list):
            result[field] = _unique(values)
    return result


def should_load_past_for_character(cid: str, current: dict[str, Any]) -> bool:
    text_parts = [
        str(current.get("last_player_input") or ""),
        str(current.get("current_scene_goal") or ""),
        str(current.get("current_location_text") or ""),
    ]
    text = "\n".join(text_parts).lower()
    return any(word in text for word in PAST_TRIGGER_WORDS)


def recommended_files_for_context_fast(current: dict[str, Any] | None = None, future: dict[str, Any] | None = None) -> list[str]:
    current = current or {}
    future = future or {}

    chars = active_scene_character_ids_fast(current, future)
    files: list[str] = [RUNTIME_DIGEST_FILE]

    if base.repo_file_exists(RUNTIME_SCENE_RULES_DIGEST):
        files.append(RUNTIME_SCENE_RULES_DIGEST)

    if base.repo_file_exists("characters/character_id_index.md"):
        files.append("characters/character_id_index.md")

    for cid in chars:
        files.extend(rt.character_files_for_context(cid, include_past=False))
        if should_load_past_for_character(cid, current):
            folder = rt.known_character_folder(cid)
            if folder:
                past = f"characters/{folder}/past.yaml"
                if base.repo_file_exists(past):
                    files.append(past)

    return [path for path in _unique(files) if path == RUNTIME_DIGEST_FILE or base.repo_file_exists(path)]


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


def _cut(value: Any, limit: int = 5000) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        except Exception:
            text = str(value)
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...<truncated>"


def _json_block(title: str, value: Any, max_chars: int = 4500) -> str:
    return f"\n## {title}\n```json\n{_cut(value, max_chars)}\n```\n"


def compact_lore_slice(session_id: str, current: dict[str, Any], chars: list[str], story_lines: Any) -> dict[str, Any]:
    if hasattr(rt, "lore_files_for_context"):
        try:
            files = rt.lore_files_for_context(current, chars, story_lines)
        except Exception:
            files = []
    else:
        files = [
            "canon_lore/index.yaml",
            "canon_lore/core/world_background.yaml",
            "canon_lore/academy/academy_background.yaml",
            "canon_lore/hidden/hidden_lore_policy.yaml",
        ]

    compact_files = []
    for path in files[:8]:
        compact_files.append({
            "path": path,
            "content_preview": _cut(_read_text_optional(path, session_id=session_id), 1200),
        })

    return {
        "mode": "compact_lore_slice",
        "loaded_lore_files": files,
        "files_preview": compact_files,
        "rule": "Use previews as background. Full lore files should load only by tag/full-context/debug.",
    }


def compact_calendar_slice(session_id: str, current: dict[str, Any]) -> dict[str, Any]:
    runtime = base.read_json("state/calendar_runtime.json", session_id, default={}) or {}
    current_date = current.get("current_date") or runtime.get("current_date")
    day_file = runtime.get("current_day_file") or (f"calendar/days/{current_date}.yaml" if current_date else "")
    return {
        "mode": "compact_calendar_slice",
        "calendar_runtime": runtime,
        "current_day_file": day_file,
        "current_day_preview": _cut(_read_text_optional(day_file, session_id=session_id), 2500),
        "rule": "Use current day hooks and current_beat_id. Do not load calendar_index each normal turn unless date changes or debug/full-context is requested.",
    }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _turn_counter_from_story(story_lines: Any) -> dict[str, Any]:
    if not isinstance(story_lines, dict):
        return {}
    counter = story_lines.get("turn_counter", {})
    return counter if isinstance(counter, dict) else {}


def audit_due_status(story_lines: Any) -> dict[str, Any]:
    counter = _turn_counter_from_story(story_lines)
    game_turn_number = _safe_int(
        counter.get("game_turn_number", counter.get("game_turn", counter.get("turn_number", counter.get("scene_count", 0)))),
        0,
    )
    last_audit_turn = _safe_int(
        counter.get("last_continuity_audit_turn", counter.get("last_compaction_turn", 0)),
        0,
    )
    next_due = ((last_audit_turn // 15) + 1) * 15 if last_audit_turn >= 0 else 15
    exact_due = game_turn_number > 0 and game_turn_number % 15 == 0 and last_audit_turn < game_turn_number
    missed_due = game_turn_number >= next_due and last_audit_turn < next_due
    return {
        "game_turn_number": game_turn_number,
        "last_continuity_audit_turn": last_audit_turn,
        "next_continuity_audit_turn": next_due,
        "audit_due": bool(exact_due or missed_due),
        "exact_15_turn_milestone": bool(exact_due),
        "missed_milestone_due": bool(missed_due and not exact_due),
        "rule": "If audit_due=true, audit the last 15 gameplay scenes against saved state before normal continuation.",
    }


def recent_scene_history_slice(session_id: str, audit_due: bool) -> dict[str, Any]:
    # Keep tiny during normal turns. Include actual last 15 scene texts only at 15/30/45... audit points.
    history = base.read_json("state/scene_history.json", session_id, default=None)
    if history is None:
        history = base.read_json("scene_history.json", session_id, default=[]) or []
    if not isinstance(history, list):
        history = []
    recent = history[-15:]
    if not audit_due:
        return {
            "mode": "not_due",
            "available_recent_scene_count": len(recent),
            "note": "Last 15 scene texts are withheld until exact 15-turn audit is due.",
        }
    compact_recent = []
    for item in recent:
        if not isinstance(item, dict):
            continue
        compact_recent.append({
            "turn_number": item.get("turn_number"),
            "player_input": _cut(item.get("player_input", ""), 800),
            "scene_text": _cut(item.get("scene_text", item.get("visible_scene_text", "")), 2400),
            "notes": item.get("notes", []),
        })
    return {
        "mode": "audit_due_include_last_15_scenes",
        "recent_scene_count": len(compact_recent),
        "audit_instruction": [
            "Extract played facts from these scene texts, not only from state.",
            "Compare with story_lines, knowledge_state, relationships, calendar_runtime and current_state.",
            "If played facts are missing from state, write them through apply-turn-result.",
            "Only after that compact repeated/minor events.",
        ],
        "recent_scenes": compact_recent,
    }


def build_scene_context_digest_fast(session_id: str) -> str:
    current = base.read_json("state/current_state.json", session_id, default={}) or {}
    future = base.read_json("state/future_locks_progress.json", session_id, default={}) or {}
    chars = active_scene_character_ids_fast(current, future)
    relationship_chars = relationship_focus_character_ids_fast(current, future)
    background_chars = background_character_ids(current)

    relationships = rt.compact_relationships_scene_pairs_only(
        base.read_json("state/relationships.json", session_id, default={}) or {},
        relationship_chars,
    )
    story_lines_full = base.read_json("state/story_lines.json", session_id, default={}) or {}
    story_lines = rt.compact_story_lines_scene_only(
        story_lines_full,
        chars,
        max_events=12,
    )
    knowledge = rt.compact_knowledge_scene_only(
        base.read_json("state/knowledge_state.json", session_id, default={}) or {},
        chars,
    )
    inventory = base.compact_if_large(
        base.read_json("state/inventory_state.json", session_id, default={}) or {},
        1800,
    )

    audit_status = audit_due_status(story_lines_full)
    recent_history = recent_scene_history_slice(session_id, bool(audit_status.get("audit_due")))

    calendar = compact_calendar_slice(session_id, current)
    lore = compact_lore_slice(session_id, current, chars, story_lines)

    current_scene = {
        "current_date": current.get("current_date"),
        "current_time": current.get("current_time"),
        "current_location_id": current.get("current_location_id"),
        "current_location_text": current.get("current_location_text"),
        "current_scene_goal": current.get("current_scene_goal"),
        "last_player_input": current.get("last_player_input"),
        "akira_state": current.get("akira_state"),
        "current_outfit": current.get("current_outfit"),
        "uniform_worn": current.get("uniform_worn"),
        "visible_inventory": current.get("visible_inventory", []),
        "nearby_items": current.get("nearby_items", []),
        "active_character_ids_loaded_full": chars,
        "relationship_focus_character_ids": relationship_chars,
        "background_character_ids_not_loaded_full": background_chars,
    }

    text = "# Runtime scene context digest — compact speed mode\n"
    text += "This digest is intentionally compact. Full immutable rules are in gpt/locks/runtime_scene_rules_digest.md.\n"
    text += _json_block("Current scene", current_scene, 5200)
    text += _json_block("15-turn audit status", audit_status, 2200)
    text += _json_block("Recent scene history for audit", recent_history, 15000 if audit_status.get("audit_due") else 1200)
    text += _json_block("Relationship slice", relationships, 4200)
    text += _json_block("Story lines slice", story_lines, 5200)
    text += _json_block("Knowledge slice", knowledge, 3600)
    text += _json_block("Inventory slice", inventory, 2000)
    text += _json_block("Calendar slice", calendar, 4200)
    text += _json_block("Lore slice", lore, 5200)
    text += "\n## State update reminder\nIf scene changes relationships/story/knowledge/current_state/calendar_runtime/inventory/reputation/rumors/future_locks, write explicit apply-turn-result payload. At 15/30/45/etc. compare last 15 scene texts with saved state before compacting.\n"
    return text


# Patch all selectors used by turn-contract and required-files endpoints.
rt.scene_character_ids = active_scene_character_ids_fast
rt.lean_recommended_files_for_context = recommended_files_for_context_fast
rt.build_scene_context_digest = build_scene_context_digest_fast

base.active_scene_characters = active_scene_character_ids_fast
base.recommended_files_for_context = recommended_files_for_context_fast

ccp.active_scene_characters = active_scene_character_ids_fast
ccp.recommended_files_for_context = recommended_files_for_context_fast
ccp._read_required_file_for_bundle = rt.read_required_file_for_bundle
ccp._required_file_parts = rt.required_file_parts_safe
ccp._chunk_loaded_parts = rt.chunk_loaded_parts_safe
ccp._required_files_chunk_response = rt.required_files_chunk_response_safe

rt.app.version = app.version
