"""
Compact prompt preview builder for academy-prequel turn-contract.

This is not a user-visible scene.
It is an internal rendering brief that tells the GPT what to do after API/state/files
are loaded: output the scene, not the API/state/status.
"""

from __future__ import annotations

import json
from typing import Any

MAX_PROMPT_PREVIEW_CHARS = 8000


def _cut(text: Any, limit: int = 700) -> str:
    if text is None:
        return ""
    value = str(text).strip()
    return value if len(value) <= limit else value[:limit].rstrip() + "..."


def _dump(value: Any, limit: int = 2200) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        text = str(value)
    return _cut(text, limit)


def _compact_current_state(current: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": current.get("current_date"),
        "time": current.get("current_time"),
        "location_id": current.get("current_location_id"),
        "location_text": current.get("current_location_text"),
        "scene_goal": current.get("current_scene_goal"),
        "akira_behavior_profile": current.get("akira_behavior_profile"),
        "akira_state": current.get("akira_state"),
        "current_outfit": current.get("current_outfit"),
        "uniform_worn": current.get("uniform_worn"),
        "visible_inventory": current.get("visible_inventory", []),
        "nearby_items": current.get("nearby_items", []),
        "active_characters": current.get("active_characters", []),
        "nearby_characters": current.get("nearby_characters", []),
        "scheduled_character_ids": current.get("scheduled_character_ids", []),
        "mentioned_character_ids": current.get("mentioned_character_ids", []),
        "delayed_character_ids": current.get("delayed_character_ids", []),
        "last_player_input": current.get("last_player_input"),
    }


def _compact_relationships(relationships: dict[str, Any], focus_ids: list[str]) -> dict[str, Any]:
    if not isinstance(relationships, dict):
        return {}
    pairs = relationships.get("pairs")
    if not isinstance(pairs, dict):
        return {}
    focus = set(focus_ids or [])
    result: dict[str, Any] = {}
    for pair_id, data in pairs.items():
        if not isinstance(pair_id, str) or "__" not in pair_id:
            continue
        left, right = pair_id.split("__", 1)
        # Prompt preview must stay scene-local: include only pairs where BOTH
        # characters are in the current active/nearby focus.
        if left not in focus or right not in focus:
            continue
        if isinstance(data, dict):
            result[pair_id] = {
                "status": data.get("status"),
                "affection": data.get("affection"),
                "trust": data.get("trust"),
                "tension": data.get("tension"),
                "jealousy": data.get("jealousy"),
                "respect": data.get("respect"),
                "curiosity": data.get("curiosity"),
                "resentment": data.get("resentment"),
                "notes": (data.get("notes") or [])[-3:] if isinstance(data.get("notes"), list) else data.get("notes"),
                "open_threads": (data.get("open_threads") or [])[-3:] if isinstance(data.get("open_threads"), list) else data.get("open_threads"),
                "behavior_next": (data.get("behavior_next") or [])[-3:] if isinstance(data.get("behavior_next"), list) else data.get("behavior_next"),
            }
    return result


def build_prompt_preview(
    *,
    session_id: str,
    current_state: dict[str, Any],
    turn_contract: dict[str, Any],
    required_files: list[str],
    knowledge_table: dict[str, Any] | None = None,
    relationships: dict[str, Any] | None = None,
    story_lines: dict[str, Any] | None = None,
    future_locks: dict[str, Any] | None = None,
) -> str:
    active_ids = list(turn_contract.get("active_character_ids", []) or [])
    nearby_ids = list(turn_contract.get("nearby_character_ids", []) or [])
    focus_ids: list[str] = []
    for item in ["akira"] + active_ids + nearby_ids:
        if item and item not in focus_ids:
            focus_ids.append(item)

    brief = f"""
PLAY MODE RENDER BRIEF
session_id: {session_id}

TASK:
- Use this contract and required_files internally.
- Immediately after getSessionTurnContract and before any gameplay scene, load required files through the CHUNKED protocol:
  1) call getRequiredFilesManifest for this same session_id;
  2) call getRequiredFilesChunk from chunk_index=0;
  3) continue with next_chunk_index until has_more=false;
  4) treat all returned chunk loaded_files/parts as the actual loaded required file contents.
- Do NOT replace chunked loading with getProjectFile or only main.yaml files.
- Do NOT render from only main.yaml files if required_files also contains character.yaml, past.yaml, locks, calendar, canon_lore or state files.
- Output the gameplay scene only after required file chunks are loaded.
- Do NOT show API status, session status, current_state summary, file list, contract summary, setup explanation or prompt_preview.
- Do NOT ask permission to continue/render/start.

SOURCE SYSTEM:
- Character behavior comes from characters/{{id}}/character.yaml, past.yaml and main.yaml if present.
- Calendar comes from calendar/calendar_index.yaml, calendar/days/{{current_date}}.yaml and state/calendar_runtime.json.
- Lore comes from canon_lore/ and lore slice.
- Hidden lore is author/engine knowledge, not automatic NPC knowledge.
- Old canon/ and old characters/main/*.md are fallback/archive only unless explicitly loaded in required_files.

PLAYER INPUT ANCHOR PROTOCOL:
- Everything the user writes outside parentheses is Akira's exact spoken line. Insert it as Akira's line; do not paraphrase, shorten, improve, or give it to another character.
- If the current player input contains no spoken text outside parentheses, do NOT create any new Akira dialogue lines in the scene body.
- Possible Akira lines that were not explicitly written by the player belong only in the bottom block "Что Акира могла бы сказать".
- Everything inside parentheses is Akira's action, gesture, body state, intention, movement or inner pause. It is not speech and not an instruction for NPCs to obey automatically.
- If an NPC asks Akira a direct question, throws a social jab, challenges her, names her, blocks her, or changes the power balance, stop and give the player the choice instead of auto-answering.

RHYTHM CONTROL:
- Good rhythm: Akira anchor -> 1-4 meaningful NPC/world reactions -> next Akira anchor or choice point.
- If 6 or more NPC lines pass without a new Akira anchor or a player choice, stop earlier.
- If Akira is leaving and an NPC throws a hook at her back, stop on that hook unless the player explicitly wrote that she ignores it.
- If a day is overloaded, softly guide toward evening/sleep/next meaningful beat instead of adding filler.

CHARACTER FIDELITY:
- Characters must act strictly according to loaded character files, current relationship state, knowledge_state, current mood, goals, limits and scene pressure.
- Do not smooth characters into generic friendly NPCs.
- If a planned line or reaction contradicts a loaded character file, relationship state or knowledge source, rewrite it before sending.

CURRENT STATE:
{_dump(_compact_current_state(current_state), 1800)}

FOCUS CHARACTERS:
active_character_ids: {active_ids}
nearby_character_ids: {nearby_ids}
focus_ids_for_relationships: {focus_ids}

REQUIRED FILES TO LOAD BEFORE SCENE:
{_dump(required_files, 1800)}

REQUIRED FILE LOADING PROTOCOL:
- The list above is not enough by itself. It is only a manifest.
- Call getRequiredFilesManifest(session_id), then getRequiredFilesChunk(session_id, chunk_index=0), then next chunks until has_more=false.
- Use all returned chunks as the loaded required file contents before writing gameplay prose.
- If chunks were not loaded, do not invent missing character relationships, calendar beats, lore, or state.

KNOWLEDGE TABLE:
{_dump(knowledge_table or turn_contract.get('knowledge_table', {}), 1400)}

RELATIONSHIP CONTEXT:
{_dump(_compact_relationships(relationships or {}, focus_ids), 1200)}

STORY / FUTURE CONTEXT:
story_lines_contract: {_dump(turn_contract.get('story_lines_contract', {}), 900)}
canon_locks: {_dump(turn_contract.get('canon_locks', []), 700)}

OUTPUT GATE:
A gameplay answer must include:
1. Scene header: short date, time, location, Akira state, visible items / atmosphere.
2. Full scene body, not recap/status/summary.
3. Akira player-input anchors inserted exactly as Akira's speech.
4. NPC/world reaction that does not steal Akira's agency.
5. Character fidelity: every NPC line/reaction must fit loaded character files, relationships, calendar, lore and knowledge sources.
6. At least one scene movement: plot, relationship, knowledge, conflict, reputation, body/energy state, rumor, schedule, open_thread or future hook.
7. Stop at a point where the player can answer if a direct hook to Akira appears.
8. Bottom block: Что можно сделать / Что Акира могла бы сказать / Мысли Акиры.

FORBIDDEN FINAL OUTPUT IN PLAY MODE:
- API/debug/contract commentary.
- Scene-complete status summary replacing the scene.
- Rendering a scene after reading only 1-3 main.yaml files while required_files contains more files.
- Letting Livia/Kir answer a direct challenge addressed to Akira.
"""
    return brief[:MAX_PROMPT_PREVIEW_CHARS]
