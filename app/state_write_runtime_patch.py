"""
Runtime patch: reliable relationship/state write contract.

What this adds:
- relationship pair alias support (livia_cross <-> livia, raiden_sterling <-> raiden, etc.);
- required-file inclusion for gpt/locks/state_update_payload_contract.md;
- stricter apply-turn-result route that stores state/last_apply_result.json;
- compact relationship context that shows legacy pair ids when short ids are active.

This module imports the current compact_context_patch app, then monkey-patches runtime helpers.
"""

from __future__ import annotations

import json
from typing import Any

import app.compact_context_patch as ccp
from app.compact_context_patch import app
from app import compact as base

STATE_UPDATE_PAYLOAD_CONTRACT_FILE = "gpt/locks/state_update_payload_contract.md"
LAST_APPLY_RESULT_FILE = "state/last_apply_result.json"
APPLY_TURN_RESULT_PATH = ccp.APPLY_TURN_RESULT_PATH

ID_ALIASES: dict[str, str] = {
    "akira": "akira", "char_akira": "akira",
    "livia": "livia", "livia_cross": "livia", "char_livia": "livia",
    "kir": "kir", "kir_knox": "kir", "char_kir": "kir",
    "haru": "haru", "haru_foster": "haru", "char_haru": "haru",
    "raiden": "raiden", "raiden_sterling": "raiden", "char_raiden": "raiden",
    "kiara": "kiara", "kiara_volt": "kiara", "char_kiara": "kiara",
    "kael": "kael_north", "kael_north": "kael_north", "char_kael_north": "kael_north",
    "north": "kael_north", "kael_nort": "kael_north",
}

_ORIGINAL_RECOMMENDED_FILES_FOR_CONTEXT = ccp.recommended_files_for_context
_ORIGINAL_ACTIVE_SCENE_CHARACTERS = ccp.active_scene_characters
_ORIGINAL_APPLY_JSON_SECTION = base.apply_json_section


def canonical_id(value: Any) -> str:
    item = str(value or "").strip()
    return ID_ALIASES.get(item, item)


def pair_parts(pair_id: str) -> list[str]:
    return [part for part in str(pair_id).split("__") if part]


def same_pair(a: str, b: str) -> bool:
    a_parts = [canonical_id(p) for p in pair_parts(a)]
    b_parts = [canonical_id(p) for p in pair_parts(b)]
    if len(a_parts) != 2 or len(b_parts) != 2:
        return False
    return set(a_parts) == set(b_parts)


def resolve_relationship_pair_key(pairs: dict[str, Any], requested_pair: str) -> str:
    requested_pair = str(requested_pair).strip()
    if requested_pair in pairs:
        return requested_pair

    # Reuse old/legacy pair id if it already exists, so we do not split memory
    # between akira__raiden and akira__raiden_sterling.
    for existing_pair in pairs.keys():
        if same_pair(existing_pair, requested_pair):
            return str(existing_pair)

    parts = pair_parts(requested_pair)
    if len(parts) == 2:
        return f"{canonical_id(parts[0])}__{canonical_id(parts[1])}"
    return requested_pair


def pair_in_focus_with_aliases(pair_id: str, focus_ids: set[str]) -> bool:
    focus = set(focus_ids or {"akira"})
    focus |= {canonical_id(item) for item in focus}
    parts = pair_parts(str(pair_id))
    return any(part in focus or canonical_id(part) in focus for part in parts)


def compact_relationships_with_aliases(state: Any, focus_ids: list[str]) -> Any:
    if not isinstance(state, dict):
        return state
    focus = set(focus_ids or ["akira"])
    focus |= {canonical_id(item) for item in focus}
    pairs = state.get("pairs")
    if isinstance(pairs, dict):
        filtered = {
            pair: data
            for pair, data in pairs.items()
            if pair_in_focus_with_aliases(str(pair), focus)
        }
        return {
            "pairs": filtered,
            "_context_filter": {
                "mode": "active_nearby_pairs_only_with_aliases",
                "focus_character_ids": sorted(focus),
                "visible_pairs": len(filtered),
                "total_pairs": len(pairs),
                "alias_note": "livia_cross/livia, raiden_sterling/raiden, haru_foster/haru are treated as the same focus ids.",
                "note": "Use /api/v1/sessions/{session_id}/json/state/relationships.json for full relationship memory when needed.",
            },
        }
    filtered = {
        key: value
        for key, value in state.items()
        if "__" in str(key) and pair_in_focus_with_aliases(str(key), focus)
    }
    if filtered:
        return {
            **filtered,
            "_context_filter": {
                "mode": "active_nearby_pairs_only_with_aliases",
                "focus_character_ids": sorted(focus),
                "visible_pairs": len(filtered),
                "total_keys": len(state),
            },
        }
    return state


def normalize_change_items(section: Any) -> list[dict[str, Any]]:
    return base.normalize_change_items(section)


def merge_unique_list(rel: dict[str, Any], field: str, value: Any) -> bool:
    return base.merge_unique_list(rel, field, value)


def apply_relationship_changes_with_aliases(session_id: str, payload: dict, dry_run: bool) -> bool:
    section = base.find_section(payload, [
        "relationship_changes",
        "relationships_changes",
        "relationship_deltas",
        "relationships",
    ])
    items = normalize_change_items(section)
    if not items:
        return False

    state = base.read_json("state/relationships.json", session_id, default={}) or {}
    pairs = state.setdefault("pairs", {})
    changed = False

    for item in items:
        pair = item.get("pair") or item.get("pair_id") or item.get("id")
        if not pair or "__" not in str(pair):
            continue

        pair_key = resolve_relationship_pair_key(pairs, str(pair))
        rel = pairs.setdefault(pair_key, base.default_relationship())

        for metric in base.REL_METRICS:
            delta_key = f"{metric}_delta"
            if delta_key in item:
                rel[metric] = max(0, min(100, int(rel.get(metric, 0)) + int(item.get(delta_key) or 0)))
                changed = True
            elif metric in item and isinstance(item.get(metric), int):
                rel[metric] = max(0, min(100, int(item[metric])))
                changed = True

        if isinstance(item.get("status"), str):
            rel["status"] = item["status"]
            changed = True

        notes = item.get("notes") or item.get("add_notes") or item.get("note")
        if merge_unique_list(rel, "notes", notes):
            changed = True

        for field in ["memory", "open_threads", "behavior_next", "triggers"]:
            value = item.get(field) or item.get(f"add_{field}")
            if merge_unique_list(rel, field, value):
                changed = True

        if item.get("last_interaction") is not None:
            rel["last_interaction"] = item.get("last_interaction")
            changed = True

    if changed and not dry_run:
        base.write_json("state/relationships.json", state, session_id)
    return changed


def recommended_files_for_context_with_state_contract(current: dict[str, Any] | None = None, future: dict[str, Any] | None = None) -> list[str]:
    files = list(_ORIGINAL_RECOMMENDED_FILES_FOR_CONTEXT(current, future))
    if base.repo_file_exists(STATE_UPDATE_PAYLOAD_CONTRACT_FILE) and STATE_UPDATE_PAYLOAD_CONTRACT_FILE not in files:
        files.append(STATE_UPDATE_PAYLOAD_CONTRACT_FILE)
    return files


def active_scene_characters_with_aliases(current: dict[str, Any], future: dict[str, Any] | None = None) -> list[str]:
    chars = _ORIGINAL_ACTIVE_SCENE_CHARACTERS(current, future)
    result: list[str] = []
    for char_id in chars:
        item = str(char_id).strip()
        canon = canonical_id(item)
        if item and item not in result:
            result.append(item)
        if canon and canon not in result:
            result.append(canon)
    return result


def state_payload_section_summary(payload: dict[str, Any]) -> dict[str, bool]:
    return {
        "relationship_changes": bool(base.find_section(payload, ["relationship_changes", "relationships_changes", "relationship_deltas", "relationships"])),
        "story_lines_changes": bool(base.find_section(payload, ["story_lines_changes", "story_line_changes", "story_lines", "story_lines_state"])),
        "knowledge_changes": bool(base.find_section(payload, ["knowledge_changes", "knowledge_state_changes", "knowledge_state"])),
        "current_state_changes": bool(base.find_section(payload, ["current_state_changes", "current_state", "state_changes"])),
        "reputation_changes": bool(base.find_section(payload, ["reputation_changes", "reputation_state_changes", "reputation_state"])),
        "rumors_changes": bool(base.find_section(payload, ["rumor_changes", "rumors_changes", "rumors_state_changes", "rumors_state"])),
        "future_locks_changes": bool(base.find_section(payload, ["future_locks_changes", "future_locks_progress_changes", "future_locks_progress"])),
    }


# Patch global helpers used by base.context_payload and compact_context_patch routes.
base.pair_in_focus = pair_in_focus_with_aliases
base.compact_relationships = compact_relationships_with_aliases
base.apply_relationship_changes = apply_relationship_changes_with_aliases
base.active_scene_characters = active_scene_characters_with_aliases
base.recommended_files_for_context = recommended_files_for_context_with_state_contract
ccp.active_scene_characters = active_scene_characters_with_aliases
ccp.recommended_files_for_context = recommended_files_for_context_with_state_contract

# Remove compact_context_patch apply route and replace it with a route that stores last_apply_result.
for route in list(app.router.routes):
    if getattr(route, "path", None) == APPLY_TURN_RESULT_PATH and "POST" in (getattr(route, "methods", set()) or set()):
        app.router.routes.remove(route)


@app.post(APPLY_TURN_RESULT_PATH, response_model=ccp.ApplyTurnResultWithVisibleSceneResponse, operation_id="applyTurnResult")
def apply_turn_result_with_state_guard(
    session_id: str,
    request: ccp.ApplyTurnResultWithVisibleSceneRequest = ccp.ApplyTurnResultWithVisibleSceneRequest(),
) -> ccp.ApplyTurnResultWithVisibleSceneResponse:
    sid = base.safe_session_id(session_id)
    base.ensure_session(sid)

    source, payload = base.read_turn_payload(sid, request)
    changed_files: list[str] = []

    if base.apply_relationship_changes(sid, payload, request.dry_run):
        changed_files.append("state/relationships.json")

    for path, names in base.STATE_SECTION_MAP:
        if base.apply_json_section(sid, payload, path, names, request.dry_run):
            changed_files.append(path)

    section_summary = state_payload_section_summary(payload)
    status = "applied" if changed_files else "no_changes_detected"

    last_apply_result = {
        "status": status,
        "session_id": sid,
        "source": source,
        "dry_run": request.dry_run,
        "changed_files": changed_files,
        "payload_sections_present": section_summary,
        "state_write_warning": None if changed_files else "No state sections changed. If the scene had relationship/story/knowledge movement, the GPT payload was incomplete.",
    }
    if not request.dry_run:
        base.write_json(LAST_APPLY_RESULT_FILE, last_apply_result, sid)
        if LAST_APPLY_RESULT_FILE not in changed_files:
            changed_files.append(LAST_APPLY_RESULT_FILE)

    scene_text = request.visible_scene_text
    return ccp.ApplyTurnResultWithVisibleSceneResponse(
        status="applied" if changed_files else status,
        session_id=sid,
        source=source,
        dry_run=request.dry_run,
        changed_files=changed_files,
        visible_scene_text=scene_text,
        final_scene_text=scene_text,
        render_packet_received=isinstance(request.render_packet, dict),
    )
