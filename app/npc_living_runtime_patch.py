"""Living NPC runtime patch v1.

Adds a short NPC rule lock and session-level memory for invented NPCs.
This does not create random NPCs by itself. It only gives the model rules and
allows important invented NPCs to persist in state/session_npcs.json.
"""
from __future__ import annotations

import json
from typing import Any

import app.context_transport_runtime_patch as rt
from app.context_transport_runtime_patch import app
from app import compact as base
import app.compact_context_patch as ccp

NPC_RULES_FILE = "gpt/locks/npc_living_scene_rules.md"
SESSION_NPCS_FILE = "state/session_npcs.json"

_ORIGINAL_RECOMMENDED = getattr(rt, "lean_recommended_files_for_context", base.recommended_files_for_context)
_ORIGINAL_BUILD_DIGEST = rt.build_scene_context_digest
_ORIGINAL_READ_REQUIRED_FILE = getattr(rt, "read_required_file_for_bundle", None)

DEFAULT_SESSION_NPCS = {
    "schema": "session_npcs_v1",
    "purpose": "Session memory for invented NPCs who are not yet full character files.",
    "policy": {
        "background_npcs": "Do not save disposable background NPCs unless they become recurring or meaningful.",
        "important_npcs": "Save invented NPCs with name, role, goal, conflict, witness value, rumor value, relationship effect, or future hook.",
        "promotion_rule": "If an NPC becomes major enough for long-term canon, promote them later into characters/<id>/ files. Until then keep them here.",
    },
    "important_npcs": {},
    "open_npc_threads": [],
    "recent_background_notes": [],
}


def _ensure_session_npcs(session_id: str) -> dict[str, Any]:
    state = base.read_json(SESSION_NPCS_FILE, session_id, default=None)
    if isinstance(state, dict):
        return state
    base.write_json(SESSION_NPCS_FILE, DEFAULT_SESSION_NPCS, session_id)
    return dict(DEFAULT_SESSION_NPCS)


def _compact_session_npcs(state: dict[str, Any]) -> dict[str, Any]:
    important = state.get("important_npcs") if isinstance(state, dict) else {}
    threads = state.get("open_npc_threads") if isinstance(state, dict) else []
    background = state.get("recent_background_notes") if isinstance(state, dict) else []

    if not isinstance(important, dict):
        important = {}
    if not isinstance(threads, list):
        threads = []
    if not isinstance(background, list):
        background = []

    return {
        "schema": state.get("schema", "session_npcs_v1"),
        "important_npcs": important,
        "open_npc_threads": threads[-12:],
        "recent_background_notes": background[-8:],
        "rule": "Use saved important_npcs as session-only recurring NPC memory. Do not save disposable background reactions.",
    }


def read_required_file_for_bundle_with_npcs(path: str, session_id: str):
    safe_path = str(path or "").strip()
    if safe_path == SESSION_NPCS_FILE:
        state = _ensure_session_npcs(session_id)
        return json.dumps(state, ensure_ascii=False, indent=2), "session"
    if callable(_ORIGINAL_READ_REQUIRED_FILE):
        return _ORIGINAL_READ_REQUIRED_FILE(path, session_id)
    return None, None


def recommended_files_with_npcs(current=None, future=None):
    try:
        files = list(_ORIGINAL_RECOMMENDED(current, future) or [])
    except TypeError:
        files = list(base.recommended_files_for_context(current or {}, future or {}) or [])

    for path in [NPC_RULES_FILE, SESSION_NPCS_FILE]:
        if path not in files:
            files.append(path)

    # SESSION_NPCS_FILE may be created inside a session at read time.
    return [p for p in files if p == rt.RUNTIME_DIGEST_FILE or p == SESSION_NPCS_FILE or base.repo_file_exists(p)]


def build_scene_context_digest_with_npcs(session_id: str) -> str:
    text = _ORIGINAL_BUILD_DIGEST(session_id)
    session_npcs = _compact_session_npcs(_ensure_session_npcs(session_id))
    return text + "\n\n## Session NPC memory\n```json\n" + json.dumps(session_npcs, ensure_ascii=False, indent=2) + "\n```\n"


# Let apply-turn-result write session NPC memory.
state_map = list(getattr(base, "STATE_SECTION_MAP", []) or [])
entry = (
    SESSION_NPCS_FILE,
    ["session_npcs_changes", "session_npcs", "npc_changes", "important_npcs_changes"],
)
if not any(item and item[0] == SESSION_NPCS_FILE for item in state_map):
    state_map.append(entry)
base.STATE_SECTION_MAP = state_map

# Add the short rule lock to minimal locks without duplicating it.
if NPC_RULES_FILE not in rt.MINIMAL_LOCK_FILES:
    rt.MINIMAL_LOCK_FILES.append(NPC_RULES_FILE)

# Patch selectors / required-file reader.
rt.read_required_file_for_bundle = read_required_file_for_bundle_with_npcs
rt.lean_recommended_files_for_context = recommended_files_with_npcs
rt.build_scene_context_digest = build_scene_context_digest_with_npcs

base.recommended_files_for_context = recommended_files_with_npcs

ccp.recommended_files_for_context = recommended_files_with_npcs
ccp._read_required_file_for_bundle = read_required_file_for_bundle_with_npcs

app.version = "0.3.50-living-npc-memory-v1"
