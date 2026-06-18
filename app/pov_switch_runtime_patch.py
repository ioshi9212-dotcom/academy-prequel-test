"""POV switch runtime patch v2.

Activated only by explicit `POV:` / `пов:` in latest input.
Default Akira gameplay is not POV mode. `пов: Акира` is ignored as default.
Adds POV rules file + target character files only for non-Akira POV targets.
Adds POV metadata to runtime digest only when non-Akira POV is active.
"""
from __future__ import annotations

import re
from typing import Any

import app.context_transport_runtime_patch as rt
from app.context_transport_runtime_patch import app
from app import compact as base
import app.compact_context_patch as ccp

POV_SWITCH_MODE_FILE = "gpt/pov_switch_mode.md"

POV_ALIASES = {
    "акира": "akira", "akira": "akira",
    "ливия": "livia", "лив": "livia", "livia": "livia",
    "райден": "raiden", "рейден": "raiden", "стэрлинг": "raiden", "стерлинг": "raiden", "raiden": "raiden",
    "хару": "haru", "haru": "haru",
    "кир": "kir", "kir": "kir",
    "киара": "kiara", "kiara": "kiara",
    "норт": "kael_north", "норта": "kael_north", "каэл": "kael_north", "каел": "kael_north", "north": "kael_north", "kael": "kael_north",
}

_ORIGINAL_SCENE_CHARACTER_IDS = rt.scene_character_ids
_ORIGINAL_RECOMMENDED = getattr(rt, "lean_recommended_files_for_context", base.recommended_files_for_context)
_ORIGINAL_BUILD_DIGEST = rt.build_scene_context_digest


def _input_text(current: dict[str, Any] | None = None) -> str:
    current = current or {}
    return "\n".join([str(current.get("last_player_input") or ""), str(current.get("current_scene_goal") or "")]).strip()


def pov_mode_info(current: dict[str, Any] | None = None) -> dict[str, Any]:
    text = _input_text(current)
    low = text.lower().replace("ё", "е")
    if not re.search(r"\b(pov|пов)\s*[:：]", low):
        return {"active": False}

    m = re.search(r"(?:pov|пов)\s*[:：]\s*([А-Яа-яA-Za-z_\-]+)", text, re.IGNORECASE)
    raw = m.group(1).strip() if m else ""
    key = raw.lower().replace("ё", "е")
    target = POV_ALIASES.get(key, rt.canonical_id(key))

    # Akira is the default gameplay POV. Do not load POV rules for her.
    if target == "akira":
        return {
            "active": False,
            "ignored": True,
            "target_raw": raw,
            "target_character_id": "akira",
            "reason": "akira_is_default_pov",
        }

    if not rt.is_known_character_id(target):
        return {"active": True, "target_raw": raw, "target_character_id": None, "error": "unknown_pov_target"}

    return {
        "active": True,
        "target_raw": raw,
        "target_character_id": target,
        "mode": "explicit_non_akira_pov_switch",
        "duration_rule": "one scene unless next command explicitly keeps POV",
        "speech_rule": "outside parentheses is POV character exact speech",
        "action_rule": "inside parentheses is POV character action/intention",
        "thought_rule": "bottom thoughts and suggested lines belong to POV character",
        "knowledge_rule": "Akira does not gain knowledge without in-scene source",
        "state_rule": "relationships/story/knowledge/reputation/rumors/calendar update normally",
    }


def scene_character_ids_with_pov(current=None, future=None):
    chars = list(_ORIGINAL_SCENE_CHARACTER_IDS(current, future) or [])
    pov = pov_mode_info(current)
    target = pov.get("target_character_id")
    if pov.get("active") and target and target not in chars:
        chars.append(target)
    return chars


def recommended_files_with_pov(current=None, future=None):
    try:
        files = list(_ORIGINAL_RECOMMENDED(current, future) or [])
    except TypeError:
        files = list(base.recommended_files_for_context(current or {}, future or {}) or [])

    pov = pov_mode_info(current or {})
    target = pov.get("target_character_id")
    if pov.get("active"):
        if base.repo_file_exists(POV_SWITCH_MODE_FILE) and POV_SWITCH_MODE_FILE not in files:
            files.append(POV_SWITCH_MODE_FILE)
        if target:
            for path in rt.character_files_for_context(target, include_past=False):
                if path not in files:
                    files.append(path)
    return [p for p in files if p == rt.RUNTIME_DIGEST_FILE or base.repo_file_exists(p)]


def build_scene_context_digest_with_pov(session_id: str) -> str:
    text = _ORIGINAL_BUILD_DIGEST(session_id)
    current = base.read_json("state/current_state.json", session_id, default={}) or {}
    pov = pov_mode_info(current)
    if not pov.get("active"):
        return text
    target = pov.get("target_character_id") or ""
    raw = pov.get("target_raw") or target
    return text + f"""

## POV switch mode — active

Explicit non-Akira POV switch requested.

- POV target: {raw} / {target}
- Text outside parentheses belongs to POV character.
- Text inside parentheses is POV character action/body state/intention.
- Header must include: 🎥 POV: {raw} · фокус сцены не Акира
- Bottom thoughts and suggested lines belong to POV character.
- Akira does not gain knowledge unless she actually sees/hears/is told.
- Relationships/knowledge/story/reputation/rumors/calendar update normally from the POV scene.
"""


rt.pov_mode_info = pov_mode_info
rt.scene_character_ids = scene_character_ids_with_pov
rt.lean_recommended_files_for_context = recommended_files_with_pov
rt.build_scene_context_digest = build_scene_context_digest_with_pov

base.active_scene_characters = scene_character_ids_with_pov
base.recommended_files_for_context = recommended_files_with_pov

ccp.active_scene_characters = scene_character_ids_with_pov
ccp.recommended_files_for_context = recommended_files_with_pov

app.version = "0.3.48-pov-switch-non-akira-only"
