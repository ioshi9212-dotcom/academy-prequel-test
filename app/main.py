
from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.core.storage import (
    append_jsonl,
    debug_info,
    ensure_runtime_root,
    ensure_session,
    read_json,
    read_project_or_runtime_file,
    read_state,
    safe_repo_path,
    session_root,
    session_state_root,
    utc_now,
    write_json_atomic,
    write_state,
)

PROJECT_SLUG = os.getenv("PROJECT_SLUG", "academy-1198-v3")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
COMPACT_EVERY_TURNS = int(os.getenv("COMPACT_EVERY_TURNS", "15"))
MAX_FILE_CHARS = int(os.getenv("MAX_FILE_CHARS", "18000"))
MAX_SCENE_SLICE_CHARS = int(os.getenv("MAX_SCENE_SLICE_CHARS", "2200"))
RUNTIME_SUMMARY_CHARS = int(os.getenv("RUNTIME_SUMMARY_CHARS", "950"))

app = FastAPI(title=f"{PROJECT_SLUG} GPT Actions API", version="3.4.8")

RESERVED_SESSION_IDS = {"default", "new", "none", "null", "undefined", "session"}


def is_reserved_session_id(session_id: str | None) -> bool:
    if not isinstance(session_id, str):
        return False
    return session_id.strip().lower() in RESERVED_SESSION_IDS


def normalize_session_id_for_create(session_id: str | None) -> str | None:
    """CreateSession must generate a fresh random id when GPT sends unsafe placeholders."""
    if session_id is None:
        return None
    cleaned = session_id.strip()
    if not cleaned or is_reserved_session_id(cleaned):
        return None
    return cleaned


def reject_reserved_session_id(session_id: str) -> None:
    if is_reserved_session_id(session_id):
        raise HTTPException(
            status_code=400,
            detail=(
                "Reserved session_id is not allowed for gameplay. "
                "Call createSession without session_id and use the returned random session_id."
            ),
        )



class CreateSessionRequest(BaseModel):
    session_id: str | None = None
    reset: bool = True


class TurnContractRequest(BaseModel):
    user_input: str = ""
    mode: Literal["play", "technical", "audit", "transfer"] = "play"
    include_file_contents: bool = False


class ApplyTurnResultRequest(BaseModel):
    scene_id: str = "scene"
    scene_text: str = ""
    technical: bool = False
    current_state_changes: dict[str, Any] = Field(default_factory=dict)
    knowledge_changes: dict[str, Any] = Field(default_factory=dict)
    relationship_changes: dict[str, Any] = Field(default_factory=dict)
    open_thread_changes: dict[str, Any] = Field(default_factory=dict)
    shared_incident_changes: dict[str, Any] = Field(default_factory=dict)
    inventory_changes: dict[str, Any] = Field(default_factory=dict)
    character_memory_changes: dict[str, Any] = Field(default_factory=dict)

    event_seed_changes: dict[str, Any] = Field(default_factory=dict)
    event_queue_changes: dict[str, Any] = Field(default_factory=dict)
    director_note_changes: dict[str, Any] = Field(default_factory=dict)
    gossip_changes: dict[str, Any] = Field(default_factory=dict)
    rating_changes: dict[str, Any] = Field(default_factory=dict)
    energy_incident_changes: dict[str, Any] = Field(default_factory=dict)


class ApplyTurnResultSimpleRequest(BaseModel):
    text: str | None = None  # Tolerates GPT Actions sending the whole payload as a JSON string.
    scene_id: str = "scene"
    scene_text: str = ""
    technical: bool = False
    current_state_changes_json: str = "{}"
    knowledge_changes_json: str = "{}"
    relationship_changes_json: str = "{}"
    open_thread_changes_json: str = "{}"
    shared_incident_changes_json: str = "{}"
    inventory_changes_json: str = "{}"
    character_memory_changes_json: str = "{}"

    event_seed_changes_json: str = "{}"
    event_queue_changes_json: str = "{}"
    director_note_changes_json: str = "{}"
    gossip_changes_json: str = "{}"
    rating_changes_json: str = "{}"
    energy_incident_changes_json: str = "{}"


class CompactRequest(BaseModel):
    reason: str = "scheduled_compaction"
    compact_last_turns: int = 15
    recent_turns_md: str | None = None
    state_updates: dict[str, Any] = Field(default_factory=dict)


CORE_REQUIRED_FILES = [
    "MANCHESS_RULES.md",
    "engine/turn_contract.md",
    "engine/loading_policy.md",
    "engine/source_priority.md",
    "engine/current_frame_policy.md",
    "engine/novel_director_core.md",
    "engine/output_format.md",
    "engine/scene_generation_rules.md",
    "engine/event_engine_rules.md",
    "engine/pov_rules.md",
    "engine/memory_update_rules.md",
    "engine/runtime_character_slice_rules.md",
    "engine/scene_assembly_gate.md",
    "engine/scene_quality_gate.md",
    "engine/scene_progress_rules.md",
    "engine/prose_style_rules.md",
    "engine/energy_atmosphere_rules.md",
    "story/pacing/no_filler_rules.md",
    "state/current_state.json",
    "state/recent_turns.md",
    "characters/characters_index.yaml",
    "runtime/characters/characters_runtime_index.yaml",
    "world/locations/locations_index.yaml",
    "world/academy/academy_index.yaml",
    "world/energy/energy_index.yaml",
    "runtime/academy/energy_atmosphere.yaml",
    "knowledge/knowledge_rules.md",
]

TECHNICAL_EXTRA_FILES = [
    "engine/session_policy.md",
    "engine/npc_knowledge_rules.md",
    "engine/anti_hallucination_rules.md",
    "validation/checklist_before_scene.md",
    "validation/calendar_skip_check.md",
    "validation/npc_knowledge_check.md",
    "validation/pov_violation_check.md",
    "relationships/relationships_index.yaml",
    "relationships/pair_schema.yaml",
]

AUDIT_EXTRA_FILES = [
    "validation/checklist_after_scene.md",
    "relationships/shared_incidents/incidents_index.yaml",
    "relationships/shared_incidents/incident_template.yaml",
]

STATE_ITEM_CONTAINER_KEYS: dict[str, str] = {
    "relationships.json": "relationships",
    "knowledge_state.json": "character_knowledge",
    "open_threads.json": "threads",
    "shared_incidents.json": "incidents",
    "event_seeds.json": "items",
    "event_queue.json": "items",
    "gossip_state.json": "items",
    "energy_incidents.json": "items",
}

STATE_METADATA_KEYS = {
    "schema",
    "session_id",
    "updated_at",
    "created_at",
    "description",
    "version",
}

KNOWLEDGE_TOP_LEVEL_KEYS = {
    "public_knowledge",
    "hidden_truths",
    "character_knowledge",
    "evidence_log",
    "speaker_labels",
}

CHARACTER_FOLDERS: dict[str, str] = {
    "char_akira": "akira",
    "char_livia": "livia",
    "char_kir": "kir",
    "char_kiara": "kiara",
    "char_haru": "haru",
    "char_raiden": "raiden",
    "char_samuel": "samuel",
}

LOCATION_REQUIRED_FILES: dict[str, list[str]] = {
    "loc_academy_main": [
        "world/locations/academy_main/location_card.yaml",
        "world/locations/academy_main/visual_description.md",
    ],
}

MONTHS_RU = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}

WEEKDAY_SHORT = {
    "понедельник": "пн",
    "вторник": "вт",
    "ср": "ср",
    "среда": "ср",
    "четверг": "чт",
    "пятница": "пт",
    "суббота": "сб",
    "воскресенье": "вс",
}

TIME_OF_DAY_RU = {
    "morning": "Утро",
    "day": "День",
    "afternoon": "День",
    "evening": "Вечер",
    "night": "Ночь",
}


def unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and value and value not in result:
            result.append(value)
    return result


def as_id_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return unique([item for item in value if isinstance(item, str)])


def trim_text(text: str, max_chars: int) -> str:
    if not isinstance(text, str):
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[truncated]"


def trim(text: str) -> dict[str, Any]:
    if len(text) <= MAX_FILE_CHARS:
        return {"content": text, "truncated": False, "chars": len(text)}
    return {"content": text[:MAX_FILE_CHARS], "truncated": True, "chars": len(text)}


def safe_read_text(path: str, session_id: str | None = None, max_chars: int = MAX_SCENE_SLICE_CHARS) -> str:
    try:
        return trim_text(read_project_or_runtime_file(path, session_id), max_chars)
    except Exception:
        return ""


def simple_yaml_value(text: str, key: str) -> str | None:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:\s*[\"']?(.*?)[\"']?\s*$", re.MULTILINE)
    match = pattern.search(text or "")
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def compact_text_list(values: Any, max_items: int = 5, max_chars_each: int = 180) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for item in values:
        if isinstance(item, str):
            result.append(trim_text(item, max_chars_each))
        elif isinstance(item, dict):
            text = item.get("summary") or item.get("text") or item.get("line") or item.get("fact") or json.dumps(item, ensure_ascii=False)
            result.append(trim_text(str(text), max_chars_each))
        if len(result) >= max_items:
            break
    return result


def compact_value(value: Any, max_depth: int = 2, max_items: int = 6, max_text: int = 350) -> Any:
    if max_depth <= 0:
        if isinstance(value, str):
            return trim_text(value, max_text)
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        return trim_text(json.dumps(value, ensure_ascii=False), max_text)

    if isinstance(value, str):
        return trim_text(value, max_text)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [compact_value(v, max_depth - 1, max_items, max_text) for v in value[:max_items]]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        preferred = [
            "id", "title", "type", "status", "priority", "date", "time", "location_id",
            "characters", "participants", "witnesses", "known_by", "summary", "text",
            "source", "certainty", "visible_facts", "spoken_lines", "relationship_effects",
            "levels", "trust", "tension", "respect", "curiosity", "jealousy", "resentment",
            "affection", "status", "private_status", "behavior_next", "triggers",
            "last_interaction", "open_threads", "shared_incidents", "wrong_beliefs",
            "beliefs", "seen_events", "heard_events", "source_file", "content",
            "event_goal", "scene_pressure", "use_as", "do_not", "requires_story_flag",
            "trigger_after",
        ]
        keys = [k for k in preferred if k in value] + [k for k in value.keys() if k not in preferred]
        for key in keys[:max_items]:
            result[key] = compact_value(value[key], max_depth - 1, max_items, max_text)
        return result
    return trim_text(str(value), max_text)


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def parse_json_text(value: str, field_name: str) -> dict[str, Any]:
    if value is None or not str(value).strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_json",
                "field": field_name,
                "message": str(exc),
            },
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_json_type",
                "field": field_name,
                "message": "JSON value must be an object/dict.",
            },
        )
    return parsed



def parse_json_string_payload(value: str, field_name: str) -> dict[str, Any]:
    """Parse a JSON object that GPT Actions may send as a single string field."""
    raw: Any = value
    for _ in range(3):
        if not isinstance(raw, str):
            break
        candidate = raw.strip()
        if not candidate:
            return {}
        try:
            raw = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_json_string_payload",
                    "field": field_name,
                    "message": str(exc),
                    "hint": "Send fields directly, or send text as a valid JSON object string.",
                },
            ) from exc
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_json_string_payload_type",
                "field": field_name,
                "message": "Payload string must decode to an object/dict.",
            },
        )
    return raw


def normalize_apply_turn_result_simple_request(req: ApplyTurnResultSimpleRequest) -> ApplyTurnResultSimpleRequest:
    """Accept both the normal schema and the common GPT mistake: {"text": "{...json...}"}."""
    data = req.model_dump()

    if data.get("text"):
        parsed = parse_json_string_payload(str(data["text"]), "text")
        # Never allow a body session_id to override the path session_id.
        parsed.pop("session_id", None)
        for key, value in parsed.items():
            if key in data:
                data[key] = value

    data["text"] = None

    json_fields = [
        "current_state_changes_json",
        "knowledge_changes_json",
        "relationship_changes_json",
        "open_thread_changes_json",
        "shared_incident_changes_json",
        "inventory_changes_json",
        "character_memory_changes_json",
        "event_seed_changes_json",
        "event_queue_changes_json",
        "director_note_changes_json",
        "gossip_changes_json",
        "rating_changes_json",
        "energy_incident_changes_json",
    ]

    for field in json_fields:
        value = data.get(field)
        if value is None or value == "":
            data[field] = "{}"
        elif isinstance(value, (dict, list)):
            # The simple endpoint stores JSON text fields, but GPT sometimes sends objects.
            data[field] = json.dumps(value if isinstance(value, dict) else {"items": value}, ensure_ascii=False)
        elif not isinstance(value, str):
            data[field] = json.dumps(value, ensure_ascii=False)

    if not isinstance(data.get("scene_text"), str):
        data["scene_text"] = json.dumps(data.get("scene_text"), ensure_ascii=False)
    if not isinstance(data.get("scene_id"), str):
        data["scene_id"] = str(data.get("scene_id") or "scene")

    return ApplyTurnResultSimpleRequest(**data)


def read_json_state(session_id: str, filename: str) -> dict[str, Any]:
    value = read_state(session_id, filename)
    return value if isinstance(value, dict) else {}


def state_container_items(state: dict[str, Any], container_key: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in state.items():
        if key in STATE_METADATA_KEYS or key == container_key:
            continue
        if key in KNOWLEDGE_TOP_LEVEL_KEYS:
            continue
        if isinstance(value, dict):
            result[key] = value
    container = state.get(container_key, {})
    if isinstance(container, dict):
        result.update({key: value for key, value in container.items() if isinstance(value, dict)})
    return result


def normalize_state_patch(filename: str, patch: dict[str, Any]) -> dict[str, Any]:
    container_key = STATE_ITEM_CONTAINER_KEYS.get(filename)
    if not container_key or not patch:
        return patch

    normalized: dict[str, Any] = {}
    container_patch: dict[str, Any] = {}

    for key, value in patch.items():
        if key == container_key and isinstance(value, dict):
            deep_merge(container_patch, value)
            continue
        if key in STATE_METADATA_KEYS:
            normalized[key] = value
            continue
        if filename == "knowledge_state.json" and key in KNOWLEDGE_TOP_LEVEL_KEYS:
            normalized[key] = value
            continue
        if isinstance(value, dict):
            container_patch[key] = value
        else:
            normalized[key] = value

    if container_patch:
        normalized.setdefault(container_key, {})
        deep_merge(normalized[container_key], container_patch)
    return normalized


def write_json_state(session_id: str, filename: str, patch: dict[str, Any]) -> None:
    current = read_json_state(session_id, filename)
    normalized_patch = normalize_state_patch(filename, patch)
    deep_merge(current, normalized_patch)
    current["updated_at"] = utc_now()
    write_state(session_id, filename, current)


def character_folder(character_id: str) -> str | None:
    return CHARACTER_FOLDERS.get(character_id)


def add_location_files(required_files: list[str], location_id: str | None) -> None:
    if not location_id:
        return
    required_files.extend(LOCATION_REQUIRED_FILES.get(location_id, []))


def should_load_goals(current_state: dict[str, Any], character_id: str) -> bool:
    ids = unique(
        as_id_list(current_state.get("goal_character_ids"))
        + as_id_list(current_state.get("initiator_character_ids"))
        + as_id_list(current_state.get("scene_driver_character_ids"))
    )
    return character_id in ids


def should_load_details(current_state: dict[str, Any], character_id: str) -> bool:
    detail_keys = [
        "detail_character_ids",
        "energy_character_ids",
        "habit_character_ids",
        "past_character_ids",
        "training_character_ids",
        "combat_character_ids",
        "close_interaction_character_ids",
    ]
    for key in detail_keys:
        if character_id in as_id_list(current_state.get(key)):
            return True

    scene_tags = as_id_list(current_state.get("scene_tags"))
    detail_tags = {"energy", "training", "combat", "sparring", "past", "memory", "medical", "injury"}
    return bool(set(scene_tags) & detail_tags)


def selected_character_ids(current_state: dict[str, Any]) -> dict[str, list[str]]:
    pov_id = current_state.get("pov_character_id")
    active = as_id_list(current_state.get("active_character_ids"))
    nearby = as_id_list(current_state.get("nearby_character_ids"))
    mentioned = as_id_list(current_state.get("mentioned_character_ids"))
    scheduled = as_id_list(current_state.get("scheduled_character_ids"))
    delayed = as_id_list(current_state.get("delayed_character_ids"))

    full = unique(([pov_id] if isinstance(pov_id, str) else []) + active + nearby)
    reference = unique(mentioned + scheduled + delayed)
    reference = [cid for cid in reference if cid not in full]

    return {
        "full": full,
        "reference": reference,
        "active": active,
        "nearby": nearby,
        "mentioned": mentioned,
        "scheduled": scheduled,
        "delayed": delayed,
    }



CHARACTER_HEADER_LABELS = {
    "char_akira": "Акира",
    "char_livia": "Ливия",
    "char_kir": "Кир",
    "char_kiara": "Киара",
    "char_haru": "Хару",
    "char_raiden": "Райден",
}


def character_header_label(character_id: str) -> str:
    return CHARACTER_HEADER_LABELS.get(character_id, character_id.replace("char_", ""))


def detect_akira_variant_from_text(user_input: str | None) -> str | None:
    text = (user_input or "").lower()
    if not text:
        return None
    if any(token in text for token in ["версия 2", "v2", "version 2", "акира 2", "ядовит", "poison"]):
        return "version_2_poisonous"
    if any(token in text for token in ["версия 1", "v1", "version 1", "холодн", "cold"]):
        return "version_1_cold"
    return None


def normalize_akira_variant(value: Any) -> str:
    raw = str(value or "").lower().strip()
    if raw in {"version_2_poisonous", "v2", "version_2", "chaotic_poisonous", "poisonous", "ядовитая", "ядовитый"}:
        return "version_2_poisonous"
    if raw in {"version_1_cold", "v1", "version_1", "cold_observing", "cold", "холодная"}:
        return "version_1_cold"
    return "version_1_cold"


def get_akira_runtime_variant(current_state: dict[str, Any]) -> str:
    status = {}
    if isinstance(current_state.get("character_status"), dict):
        status = current_state.get("character_status", {}).get("char_akira", {}) or {}
    for key in ("runtime_variant", "behavior_version", "behavior_mask", "active_mask"):
        if key in status:
            return normalize_akira_variant(status.get(key))
    story_flags = current_state.get("story_flags", {})
    if isinstance(story_flags, dict):
        for key in ("akira_runtime_variant", "akira_behavior_version", "akira_mask"):
            if key in story_flags:
                return normalize_akira_variant(story_flags.get(key))
    return "version_1_cold"


def apply_user_variant_selection(session_id: str, current_state: dict[str, Any], user_input: str | None) -> dict[str, Any]:
    detected = detect_akira_variant_from_text(user_input)
    if not detected:
        return current_state
    current_state.setdefault("character_status", {})
    current_state["character_status"].setdefault("char_akira", {})
    current_state["character_status"]["char_akira"]["runtime_variant"] = detected
    current_state["character_status"]["char_akira"]["behavior_version"] = detected
    current_state.setdefault("story_flags", {})
    current_state["story_flags"]["akira_runtime_variant"] = detected
    write_state(session_id, "current_state.json", current_state)
    return current_state



def state_has_akira_v2_marker(current_state: dict[str, Any]) -> bool:
    """Return True if any stored state field says Akira v2 is active."""
    status = {}
    if isinstance(current_state.get("character_status"), dict):
        status = current_state.get("character_status", {}).get("char_akira", {}) or {}
    story_flags = current_state.get("story_flags", {}) if isinstance(current_state.get("story_flags"), dict) else {}
    raw_values = [
        status.get("runtime_variant"),
        status.get("behavior_version"),
        status.get("behavior_mask"),
        status.get("active_mask"),
        status.get("selected_runtime_variant"),
        story_flags.get("akira_runtime_variant"),
        story_flags.get("akira_behavior_version"),
        story_flags.get("akira_mask"),
    ]
    return any(normalize_akira_variant(value) == "version_2_poisonous" for value in raw_values if value is not None)


def normalize_current_akira_variant_state(session_id: str, current_state: dict[str, Any]) -> dict[str, Any]:
    """Fix v1/v2 drift inside long-running sessions. Prefer v2 if any field already confirms v2."""
    if not isinstance(current_state, dict):
        return current_state

    selected = "version_2_poisonous" if state_has_akira_v2_marker(current_state) else get_akira_runtime_variant(current_state)

    current_state.setdefault("character_status", {})
    current_state["character_status"].setdefault("char_akira", {})
    status = current_state["character_status"]["char_akira"]

    changed = False
    for key in ("runtime_variant", "behavior_version", "active_mask"):
        if status.get(key) != selected:
            status[key] = selected
            changed = True

    current_state.setdefault("story_flags", {})
    if current_state["story_flags"].get("akira_runtime_variant") != selected:
        current_state["story_flags"]["akira_runtime_variant"] = selected
        changed = True

    if changed:
        write_state(session_id, "current_state.json", current_state)
    return current_state


def compact_string_map(value: Any, max_chars: int = 360) -> Any:
    if isinstance(value, str):
        return trim_text(value, max_chars)
    if isinstance(value, dict):
        return {str(k): compact_string_map(v, max_chars) for k, v in list(value.items())[:4]}
    return compact_value(value, max_depth=1, max_items=4, max_text=max_chars)


def compact_scene_contract_for_tool(contract: dict[str, Any]) -> dict[str, Any]:
    """Hard cap the Action response so long sessions do not hit ResponseTooLargeError."""
    if not isinstance(contract, dict):
        return {}

    def cv(value: Any, depth: int = 2, items: int = 4, text_len: int = 160) -> Any:
        return compact_value(value, max_depth=depth, max_items=items, max_text=text_len)

    result: dict[str, Any] = {
        "version": "scene_contract_v5_ultra_compact",
        "mode": contract.get("mode"),
        "compact_reason": "ResponseTooLarge protection; full files remain available through getProjectFileByQuery in technical mode.",
    }

    # current frame / header
    result["current_frame"] = cv(contract.get("current_frame", {}), depth=3, items=8, text_len=120)
    result["header_contract"] = {
        "template_lines": [
            "📅 {date_human}",
            "🕒 {time_human}",
            "📍 Место: {location_human}",
            "🌤 Погода: {weather_human}",
            "🫀 Состояние Акиры: {pov_state_human}",
            "🎒 При себе / рядом: {context_human}",
        ],
        "omit_empty_lines": True,
        "rules_short": "🫀 state only; 🎒 visible items/clothes/hair/nearby; no dry/wet unless relevant.",
    }

    # compact scene sources
    calendar = contract.get("calendar_slice", {}) if isinstance(contract.get("calendar_slice"), dict) else {}
    result["calendar_slice"] = {
        "calendar_id": calendar.get("calendar_id"),
        "current_day_id": calendar.get("current_day_id"),
        "current_date": calendar.get("current_date"),
        "current_day_block": trim_text(str(calendar.get("current_day_block", "")), 700),
    }

    arc = contract.get("arc_slice", {}) if isinstance(contract.get("arc_slice"), dict) else {}
    result["arc_slice"] = {
        "source_file": arc.get("source_file"),
        "content": trim_text(str(arc.get("content", "")), 450),
    }

    location = contract.get("location_slice", {}) if isinstance(contract.get("location_slice"), dict) else {}
    location_content = location.get("content", {})
    if not isinstance(location_content, dict):
        location_content = {}
    result["location_slice"] = {
        "location_id": location.get("location_id"),
        "source_files": location.get("source_files", [])[:2] if isinstance(location.get("source_files"), list) else [],
        "content": {k: trim_text(str(v), 360) for k, v in list(location_content.items())[:2]},
    }

    # character load plan
    load_plan = contract.get("character_load_plan", {}) if isinstance(contract.get("character_load_plan"), dict) else {}
    result["character_load_plan"] = {
        "full_character_ids": load_plan.get("full_character_ids", []),
        "reference_character_ids": (load_plan.get("reference_character_ids", []) or [])[:4],
        "full_rule": "Use compact runtime summaries only.",
    }

    # character slice
    char_slice = contract.get("character_slice", {})
    compact_chars: dict[str, Any] = {}
    if isinstance(char_slice, dict):
        for cid, data in list(char_slice.items())[:5]:
            if not isinstance(data, dict):
                continue
            compact_chars[cid] = {
                "character_id": data.get("character_id", cid),
                "folder": data.get("folder"),
                "runtime_file": data.get("runtime_file"),
                "selected_runtime_variant": data.get("selected_runtime_variant"),
                "runtime_summary": trim_text(str(data.get("runtime_summary", "")), 850),
                "card_hint": trim_text(str(data.get("card_hint", "")), 220),
                "variant_rule": data.get("variant_rule"),
            }
            if data.get("goals_hint"):
                compact_chars[cid]["goals_hint"] = trim_text(str(data.get("goals_hint")), 240)
    result["character_slice"] = compact_chars

    # state/knowledge/memory
    result["character_memory_slice"] = cv(contract.get("character_memory_slice", {}), depth=2, items=3, text_len=130)
    result["relationship_slice"] = cv(contract.get("relationship_slice", {}), depth=2, items=4, text_len=130)
    result["relationship_behavior_contract"] = {
        "rule": "relationship_slice + behavior_next shape NPC behavior",
        "levels": "trust/tension/respect/curiosity/jealousy/resentment",
    }
    result["knowledge_slice"] = cv(contract.get("knowledge_slice", {}), depth=2, items=4, text_len=130)
    result["knowledge_write_contract"] = {"rule": "Save only new seen/heard/said facts and wrong beliefs."}
    result["open_threads_slice"] = cv(contract.get("open_threads_slice", {}), depth=2, items=3, text_len=130)
    result["shared_incidents_slice"] = cv(contract.get("shared_incidents_slice", {}), depth=2, items=3, text_len=130)

    # event/energy
    result["event_engine_slice"] = cv(contract.get("event_engine_slice", {}), depth=2, items=3, text_len=130)

    energy = contract.get("energy_atmosphere_slice", {}) if isinstance(contract.get("energy_atmosphere_slice"), dict) else {}
    active_energy = energy.get("active_character_energy", {})
    if not isinstance(active_energy, dict):
        active_energy = {}
    result["energy_atmosphere_slice"] = {
        "academy_rule": energy.get("academy_rule", "Academy scenes must feel populated by energy carriers."),
        "atmosphere_compact": trim_text(str(energy.get("atmosphere_compact", "")), 620),
        "classes_compact": trim_text(str(energy.get("classes_compact", "")), 360),
        "active_character_energy": {
            cid: cv(data, depth=1, items=3, text_len=260)
            for cid, data in list(active_energy.items())[:3]
        },
        "energy_incidents": cv(energy.get("energy_incidents", {}), depth=2, items=2, text_len=110),
        "use_rules": [
            "Add 1 small physical energy detail in Academy scenes.",
            "No power showcase without trigger.",
            "Save meaningful slips as energy_incident.",
        ],
    }

    # hard gates as tiny contracts
    result["scene_assembly_gate"] = {
        "status": "hard_gate",
        "failure_line": "Не удалось собрать scene assembly packet через Action. Без него я не продолжаю игровую сцену.",
        "must_have": ["current_frame", "character_slice", "relationship_slice", "knowledge_slice", "energy_atmosphere_slice"],
    }
    result["response_format_contract"] = {
        "required": "emoji header + scene + actions + speech options + Akira thoughts",
        "forbidden": ["technical text", "empty header", "micro-choice endings", "decorative prose"],
    }
    result["scene_density_contract"] = {
        "target": "7-12 short units",
        "must": ["world/system motion", "Akira POV", "active NPC reaction", "pressure/change", "real choice"],
    }
    result["scene_quality_gate_contract"] = {
        "rule": "No stub. Complete scene only. NPC dialogue/action + pressure + consequence.",
    }
    result["scene_progress_contract"] = {
        "rule": "Do not stop on micro-actions; auto-advance to real choice/reply/risk.",
        "forbidden_micro_choices": ["press button", "wait instructions", "look panel", "take card", "continue observing"],
    }
    result["prose_style_contract"] = {
        "rule": "clear factual prose; no decorative literary contrast",
        "example": "Bad: 'контрастируя с серостью'; Good: 'заметны в холодном свете панели'.",
    }
    result["npc_autonomy_contract"] = {
        "rule": "NPCs/world do not obey player intent automatically; thoughts are not NPC knowledge.",
    }
    result["memory_write_contract"] = {
        "rule": "Save important events/quotes/knowledge/relationship/energy only; not full dialogue.",
    }

    result["selection_rules"] = [
        "Use runtime summaries.",
        "Use relationships/knowledge before NPC reactions.",
        "Use energy atmosphere.",
        "No micro-choice endings.",
        "Save only important changes.",
    ]
    return result



def runtime_character_file_for(character_id: str, current_state: dict[str, Any]) -> str | None:
    folder = character_folder(character_id)
    if not folder:
        return None
    if character_id == "char_akira":
        variant = get_akira_runtime_variant(current_state)
        if variant == "version_2_poisonous":
            return "runtime/characters/akira_v2.yaml"
        return "runtime/characters/akira_v1.yaml"
    return f"runtime/characters/{folder}.yaml"


def format_level_value(value: Any, label: str) -> str | None:
    if isinstance(value, (int, float)) and value > 0:
        return f"{label} {value}/10"
    if isinstance(value, str) and value.strip():
        return f"{label}: {value.strip()}"
    return None


def build_required_files(current_state: dict[str, Any], mode: str) -> list[str]:
    required_files = list(CORE_REQUIRED_FILES)

    arc_id = current_state.get("current_arc_id") or "arc_001_academy_start"
    if isinstance(arc_id, str) and arc_id:
        required_files.append(f"story/arcs/{arc_id}.yaml")

    location_id = current_state.get("current_location_id") or "loc_academy_main"
    add_location_files(required_files, location_id)

    selected = selected_character_ids(current_state)
    for cid in selected["full"]:
        runtime_file = runtime_character_file_for(cid, current_state)
        if runtime_file:
            required_files.append(runtime_file)

    for cid in selected["reference"][:4]:
        runtime_file = runtime_character_file_for(cid, current_state)
        if runtime_file:
            required_files.append(runtime_file)

    if mode in {"technical", "audit", "transfer"}:
        required_files.extend(TECHNICAL_EXTRA_FILES)

    if mode in {"audit", "transfer"}:
        required_files.extend(AUDIT_EXTRA_FILES)

    return unique(required_files)


def build_character_slice(session_id: str, current_state: dict[str, Any], character_ids: list[str]) -> dict[str, Any]:
    """Compact active-character source pack. Uses runtime summaries, not full behavior/voice files."""
    result: dict[str, Any] = {}
    for character_id in character_ids:
        folder = character_folder(character_id)
        if not folder:
            continue

        runtime_file = runtime_character_file_for(character_id, current_state) or f"runtime/characters/{folder}.yaml"
        runtime_summary = safe_read_text(runtime_file, session_id, max_chars=RUNTIME_SUMMARY_CHARS)
        card = safe_read_text(f"characters/{folder}/character_card.yaml", session_id, max_chars=300)

        data: dict[str, Any] = {
            "character_id": character_id,
            "folder": folder,
            "source": "runtime_summary",
            "runtime_file": runtime_file,
            "runtime_summary": runtime_summary,
            "card_hint": card,
            "use_rule": "Use runtime_summary as the primary behavior/voice source. Do not fetch full behavior.md or voice.md in normal play unless explicitly missing.",
        }

        if character_id == "char_akira":
            data["selected_runtime_variant"] = get_akira_runtime_variant(current_state)
            data["variant_rule"] = "Use ONLY the selected Akira runtime variant for face, smile, expression, tone and behavior. Do not mix version 1 and version 2."

        if not runtime_summary:
            # Safe fallback: small extracts only, never full files.
            data["source"] = "compact_fallback"
            data["behavior_hint"] = safe_read_text(f"characters/{folder}/behavior.md", session_id, max_chars=500)
            data["voice_hint"] = safe_read_text(f"characters/{folder}/voice.md", session_id, max_chars=350)

        if should_load_goals(current_state, character_id):
            data["goals_hint"] = safe_read_text(f"characters/{folder}/goals.yaml", session_id, max_chars=700)

        if should_load_details(current_state, character_id):
            data["detail_hint"] = {
                "energy": safe_read_text(f"characters/{folder}/energy.yaml", session_id, max_chars=700),
                "habits": safe_read_text(f"characters/{folder}/habits.md", session_id, max_chars=700),
                "past": safe_read_text(f"characters/{folder}/past.md", session_id, max_chars=900),
            }

        result[character_id] = data
    return result


def relationship_participants(key: str, value: Any) -> list[str]:
    if isinstance(value, dict):
        for field in ("characters", "participants", "character_ids"):
            ids = as_id_list(value.get(field))
            if ids:
                return ids
    return unique(re.findall(r"char_[A-Za-z0-9_]+", key))


def build_relationship_slice(session_id: str, scene_ids: list[str]) -> dict[str, Any]:
    relationships_state = read_json_state(session_id, "relationships.json")
    relationships = state_container_items(relationships_state, "relationships")
    result: dict[str, Any] = {}
    for key, value in relationships.items():
        participants = relationship_participants(key, value)
        if len([cid for cid in participants if cid in scene_ids]) >= 2:
            result[key] = compact_value(value, max_depth=3, max_items=8, max_text=260)
    return result


def build_knowledge_slice(session_id: str, scene_ids: list[str]) -> dict[str, Any]:
    knowledge = read_json_state(session_id, "knowledge_state.json")
    character_knowledge = knowledge.get("character_knowledge", {})
    if not isinstance(character_knowledge, dict):
        character_knowledge = {}

    result: dict[str, Any] = {
        cid: compact_value(character_knowledge.get(cid, {}), max_depth=3, max_items=8, max_text=260)
        for cid in scene_ids
        if isinstance(character_knowledge.get(cid, {}), dict)
    }

    speaker_labels = knowledge.get("speaker_labels", {})
    if isinstance(speaker_labels, dict):
        focused_labels = {cid: speaker_labels.get(cid) for cid in scene_ids if cid in speaker_labels}
        if focused_labels:
            result["speaker_labels"] = focused_labels

    evidence_log = knowledge.get("evidence_log", [])
    if isinstance(evidence_log, list):
        focused_evidence: list[Any] = []
        for item in evidence_log:
            if not isinstance(item, dict):
                continue
            chars = unique(
                as_id_list(item.get("characters"))
                + as_id_list(item.get("participants"))
                + as_id_list(item.get("known_by"))
                + as_id_list(item.get("witnesses"))
            )
            if chars and any(cid in scene_ids for cid in chars):
                focused_evidence.append(compact_value(item, max_depth=2, max_items=6, max_text=220))
            if len(focused_evidence) >= 4:
                break
        if focused_evidence:
            result["focused_evidence_log"] = focused_evidence
    return result


def build_character_memory_slice(session_id: str, scene_ids: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    root = session_state_root(session_id) / "character_memory"
    for character_id in scene_ids:
        path = root / f"{character_id}.json"
        current = read_json(path, {})
        if isinstance(current, dict) and current:
            result[character_id] = {
                "character_id": current.get("character_id", character_id),
                "seen_events": compact_text_list(current.get("seen_events"), max_items=4),
                "heard_events": compact_text_list(current.get("heard_events"), max_items=4),
                "beliefs": compact_value(current.get("beliefs", []), max_depth=2, max_items=5, max_text=220),
                "wrong_beliefs": compact_value(current.get("wrong_beliefs", []), max_depth=2, max_items=4, max_text=220),
                "relationships_from_this_character": compact_value(
                    current.get("relationships_from_this_character", {}),
                    max_depth=3,
                    max_items=5,
                    max_text=220,
                ),
                "scene_behavior_overrides": compact_value(
                    current.get("scene_behavior_overrides", []),
                    max_depth=2,
                    max_items=3,
                    max_text=220,
                ),
                "last_updated_scene_id": current.get("last_updated_scene_id"),
            }
    return result


def build_open_threads_slice(session_id: str, scene_ids: list[str]) -> dict[str, Any]:
    open_threads_state = read_json_state(session_id, "open_threads.json")
    open_threads = state_container_items(open_threads_state, "threads")
    result: dict[str, Any] = {}
    for key, value in open_threads.items():
        if not isinstance(value, dict):
            continue
        status = value.get("status", "open")
        participants = as_id_list(value.get("participants")) or as_id_list(value.get("character_ids"))
        if status in {"closed", "resolved", "archived"}:
            continue
        if participants and any(cid in scene_ids for cid in participants):
            result[key] = compact_value(value, max_depth=2, max_items=6, max_text=220)
        elif not participants and len(result) < 3:
            result[key] = compact_value(value, max_depth=2, max_items=6, max_text=220)
        if len(result) >= 6:
            break
    return result


def build_shared_incidents_slice(session_id: str, scene_ids: list[str]) -> dict[str, Any]:
    incidents_state = read_json_state(session_id, "shared_incidents.json")
    incidents = state_container_items(incidents_state, "incidents")
    result: dict[str, Any] = {}
    for key, value in incidents.items():
        if not isinstance(value, dict):
            continue
        participants = unique(
            as_id_list(value.get("participants"))
            + as_id_list(value.get("witnesses"))
            + as_id_list(value.get("known_by"))
        )
        status = value.get("status", "active_reference")
        if participants and any(cid in scene_ids for cid in participants) and status != "archived":
            result[key] = compact_value(value, max_depth=2, max_items=6, max_text=220)
        if len(result) >= 5:
            break
    return result


def item_related_to_scene(value: Any, scene_ids: list[str], location_id: str | None, date_value: str | None) -> bool:
    if not isinstance(value, dict):
        return False

    chars = unique(
        as_id_list(value.get("characters"))
        + as_id_list(value.get("participants"))
        + as_id_list(value.get("about"))
        + as_id_list(value.get("witnesses"))
        + as_id_list(value.get("required_characters"))
        + as_id_list(value.get("characters_required"))
        + as_id_list(value.get("characters_optional"))
    )
    if chars and any(cid in scene_ids for cid in chars):
        return True

    locs = unique(as_id_list(value.get("location_ids")) + as_id_list(value.get("location_tags")))
    loc_single = value.get("location_id")
    if isinstance(loc_single, str):
        locs.append(loc_single)
    if location_id and location_id in locs:
        return True

    for date_key in ("date", "current_date", "starts_at", "created_at"):
        raw = value.get(date_key)
        if isinstance(raw, str) and date_value and raw.startswith(date_value):
            return True
        if isinstance(raw, dict):
            raw_date = raw.get("date")
            if isinstance(raw_date, str) and raw_date == date_value:
                return True
    return False


def item_unlocked_by_flags(value: Any, current_state: dict[str, Any]) -> bool:
    if not isinstance(value, dict):
        return False
    story_flags = current_state.get("story_flags", {})
    if not isinstance(story_flags, dict):
        story_flags = {}
    required_flag = value.get("requires_story_flag")
    if isinstance(required_flag, str) and required_flag and not story_flags.get(required_flag):
        return False
    return True


def slice_state_items(
    state: dict[str, Any],
    current_state: dict[str, Any],
    scene_ids: list[str],
    location_id: str | None,
    date_value: str | None,
    *,
    statuses: set[str] | None = None,
    max_items: int = 5,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in state.items():
        if not isinstance(value, dict):
            continue
        if statuses is not None:
            status = str(value.get("status", "active"))
            if status not in statuses:
                continue
        if not item_unlocked_by_flags(value, current_state):
            continue
        related = item_related_to_scene(value, scene_ids, location_id, date_value)
        priority = value.get("priority", 0)
        is_priority = isinstance(priority, (int, float)) and priority >= 4
        if related or (len(result) < 2 and is_priority):
            result[key] = compact_value(value, max_depth=2, max_items=6, max_text=220)
        if len(result) >= max_items:
            break
    return result


def build_event_engine_slice(session_id: str, current_state: dict[str, Any], scene_ids: list[str]) -> dict[str, Any]:
    location_id = current_state.get("current_location_id") if isinstance(current_state.get("current_location_id"), str) else None
    date_value = current_state.get("current_date") if isinstance(current_state.get("current_date"), str) else None

    event_seeds = state_container_items(read_json_state(session_id, "event_seeds.json"), "items")
    event_queue = state_container_items(read_json_state(session_id, "event_queue.json"), "items")
    director_notes = read_json_state(session_id, "director_notes.json")
    gossip_items = state_container_items(read_json_state(session_id, "gossip_state.json"), "items")
    rating_state = read_json_state(session_id, "rating_state.json")
    energy_items = state_container_items(read_json_state(session_id, "energy_incidents.json"), "items")

    rating_slice = {
        cid: compact_value(rating_state.get(cid, {}), max_depth=2, max_items=5, max_text=180)
        for cid in scene_ids
        if isinstance(rating_state.get(cid, {}), dict)
    }

    active_focus = director_notes.get("current_director_focus", [])
    if not isinstance(active_focus, list):
        active_focus = []

    return {
        "rules_source": "engine/event_engine_rules.md",
        "director_focus_compact": compact_value(active_focus[:3], max_depth=2, max_items=5, max_text=220),
        "event_seeds": slice_state_items(
            event_seeds,
            current_state,
            scene_ids,
            location_id,
            date_value,
            statuses={"seeded", "active", "maturing"},
            max_items=4,
        ),
        "event_queue": slice_state_items(
            event_queue,
            current_state,
            scene_ids,
            location_id,
            date_value,
            statuses={"ready", "active"},
            max_items=4,
        ),
        "gossip_state": slice_state_items(
            gossip_items,
            current_state,
            scene_ids,
            location_id,
            date_value,
            statuses={"active", "spreading", "new"},
            max_items=3,
        ),
        "rating_state": rating_slice,
        "energy_incidents": slice_state_items(
            energy_items,
            current_state,
            scene_ids,
            location_id,
            date_value,
            statuses={"active", "pending", "recent", "resolved_scene_hook"},
            max_items=3,
        ),
        "selection_protocol": [
            "First follow the current calendar beat.",
            "Choose one suitable queued event/seed only if it matches place, characters and pacing.",
            "Do not use locked/pending delayed-character entries until trigger_after / requires_story_flag is satisfied.",
            "After scene, save new seeds, queued events, gossip, rating or energy changes through applyTurnResultSimple.",
        ],
    }


def extract_calendar_day_block(calendar_text: str, day_id: str | None, date_value: str | None) -> str:
    lines = calendar_text.splitlines()
    start: int | None = None
    if day_id:
        pattern = f"  {day_id}:"
        for i, line in enumerate(lines):
            if line.startswith(pattern):
                start = i
                break
    if start is None and date_value:
        for i, line in enumerate(lines):
            if f'date: "{date_value}"' in line or f"date: '{date_value}'" in line or f"date: {date_value}" in line:
                for j in range(i, -1, -1):
                    if re.match(r"^  [A-Za-z0-9_]+:\s*$", lines[j]):
                        start = j
                        break
                break
    if start is None:
        return ""
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^  [A-Za-z0-9_]+:\s*$", lines[j]):
            end = j
            break
    return "\n".join(lines[start:end])


def build_calendar_slice(session_id: str, current_state: dict[str, Any]) -> dict[str, Any]:
    calendar_id = current_state.get("current_calendar_id") or "academy_start"
    current_day_id = current_state.get("current_day_id")
    current_date = current_state.get("current_date")

    source_file = f"story/calendar/{calendar_id}.yaml"
    calendar_text = safe_read_text(source_file, session_id, max_chars=35000)
    day_block = extract_calendar_day_block(
        calendar_text,
        current_day_id if isinstance(current_day_id, str) else None,
        current_date if isinstance(current_date, str) else None,
    )
    protocol = ""
    if "calendar_reading_protocol:" in calendar_text:
        protocol = trim_text(calendar_text.split("\ndays:", 1)[0], 900)

    return {
        "source_file": source_file,
        "calendar_id": calendar_id,
        "current_day_id": current_day_id,
        "current_date": current_date,
        "protocol_compact": protocol,
        "current_day_block": trim_text(day_block, 2500),
        "selection_rule": "Use only current_day_block for this turn unless the player explicitly skips time or asks for calendar audit.",
    }


def format_date_human(date_value: Any, weekday_value: Any) -> str:
    if not isinstance(date_value, str):
        return ""
    parts = date_value.split("-")
    if len(parts) != 3:
        return date_value
    try:
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
    except ValueError:
        return date_value
    month_name = MONTHS_RU.get(month, parts[1])
    weekday = WEEKDAY_SHORT.get(str(weekday_value or "").lower(), str(weekday_value or "").lower())
    if weekday:
        return f"{day} {month_name} {weekday} {year}"
    return f"{day} {month_name} {year}"


def format_time_human(time_value: Any, time_of_day: Any) -> str:
    tod = TIME_OF_DAY_RU.get(str(time_of_day or "").lower(), str(time_of_day or ""))
    if isinstance(time_value, str) and time_value:
        if tod:
            return f"{tod}, около {time_value}"
        return f"около {time_value}"
    return tod


def format_weather_human(weather: Any) -> str:
    if not isinstance(weather, dict):
        return ""
    parts: list[str] = []
    condition = weather.get("condition")
    temp = weather.get("temperature_c")
    wind = weather.get("wind")
    precipitation = weather.get("precipitation")
    ground = weather.get("ground")

    if condition:
        parts.append(str(condition))
    if temp is not None:
        parts.append(f"{temp}°C")
    if wind:
        parts.append(str(wind))
    if precipitation and precipitation not in {"нет", "none", "no"}:
        parts.append(str(precipitation))
    if ground and ground not in {"сухо", "сухая"}:
        parts.append(str(ground))
    return ", ".join(parts)


def format_pov_state_human(current_state: dict[str, Any]) -> str:
    pov_id = current_state.get("pov_character_id", "char_akira")
    status = {}
    if isinstance(current_state.get("character_status"), dict):
        status = current_state.get("character_status", {}).get(pov_id, {}) or {}

    bits: list[str] = []

    physical_state = status.get("physical_state")
    if physical_state:
        bits.append(str(physical_state))

    pain = status.get("pain")
    injuries = status.get("injuries")
    if isinstance(injuries, list) and injuries:
        bits.append("травмы: " + ", ".join(str(item) for item in injuries))
    if pain:
        bits.append(f"боль: {pain}")

    for key, label in (
        ("fatigue", "усталость"),
        ("hunger", "голод"),
        ("thirst", "жажда"),
        ("stress", "напряжение"),
    ):
        formatted = format_level_value(status.get(key), label)
        if formatted:
            bits.append(formatted)

    notes = status.get("state_notes") or status.get("notes")
    if isinstance(notes, list):
        for note in notes[:2]:
            if note:
                bits.append(str(note))
    elif isinstance(notes, str) and notes.strip():
        bits.append(notes.strip())

    return "; ".join(unique([p for p in bits if p])) or "состояние рабочее"


def format_context_human(current_state: dict[str, Any], location_text: str) -> str:
    pieces: list[str] = []
    scene_continuity = current_state.get("scene_continuity", {})
    visible_items = scene_continuity.get("visible_item_state") if isinstance(scene_continuity, dict) else {}

    if isinstance(visible_items, dict):
        for key, value in visible_items.items():
            if not value:
                continue
            if isinstance(value, bool):
                pieces.append(str(key))
            else:
                pieces.append(str(value))

    pov_id = current_state.get("pov_character_id", "char_akira")
    status = {}
    if isinstance(current_state.get("character_status"), dict):
        status = current_state.get("character_status", {}).get(pov_id, {}) or {}

    clothing_state = status.get("clothing_state")
    hair_state = status.get("hair_state")
    if clothing_state:
        pieces.append(str(clothing_state))
    if hair_state:
        pieces.append(str(hair_state))

    nearby = as_id_list(current_state.get("nearby_character_ids"))
    active = as_id_list(current_state.get("active_character_ids"))
    pov = current_state.get("pov_character_id")
    scene_people = [cid for cid in unique(active + nearby) if cid != pov]
    if scene_people:
        pieces.extend([character_header_label(cid) for cid in scene_people])

    context_line = simple_yaml_value(location_text, "header_context")
    if context_line:
        pieces.append(context_line)

    return ", ".join(unique([p for p in pieces if p]))


def location_human(session_id: str | None, location_id: Any) -> dict[str, str]:
    if not isinstance(location_id, str):
        return {"location_id": "", "display_name": "", "header_name": "", "short_name": "", "raw_card": ""}
    files = LOCATION_REQUIRED_FILES.get(location_id, [])
    card_path = files[0] if files else ""
    text = safe_read_text(card_path, session_id, max_chars=1200) if card_path else ""
    display = simple_yaml_value(text, "display_name") or location_id
    header = simple_yaml_value(text, "header_name") or display
    short = simple_yaml_value(text, "short_name") or display
    return {
        "location_id": location_id,
        "display_name": display,
        "header_name": header,
        "short_name": short,
        "raw_card": text,
    }


def build_current_frame(current_state: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
    pov_id = current_state.get("pov_character_id", "char_akira")
    status = {}
    if isinstance(current_state.get("character_status"), dict):
        status = current_state.get("character_status", {}).get(pov_id, {}) or {}
    loc = location_human(session_id, current_state.get("current_location_id"))
    weather_human = format_weather_human(current_state.get("weather", {}))
    date_human = format_date_human(current_state.get("current_date"), current_state.get("current_day_of_week"))
    time_human = format_time_human(current_state.get("current_time"), current_state.get("time_of_day"))
    pov_state_human = format_pov_state_human(current_state)
    context_human = format_context_human(current_state, loc.get("raw_card", ""))
    return {
        "date": current_state.get("current_date"),
        "day_of_week": current_state.get("current_day_of_week"),
        "time": current_state.get("current_time"),
        "time_of_day": current_state.get("time_of_day"),
        "location_id": current_state.get("current_location_id"),
        "location_display_name": loc.get("display_name"),
        "location_header_name": loc.get("header_name"),
        "location_short_name": loc.get("short_name"),
        "arc_id": current_state.get("current_arc_id"),
        "calendar_id": current_state.get("current_calendar_id"),
        "day_id": current_state.get("current_day_id"),
        "weather": current_state.get("weather", {}),
        "pov_character_id": pov_id,
        "pov_status_compact": compact_value(status, max_depth=2, max_items=6, max_text=160),
        "active_character_ids": as_id_list(current_state.get("active_character_ids")),
        "nearby_character_ids": as_id_list(current_state.get("nearby_character_ids")),
        "mentioned_character_ids": as_id_list(current_state.get("mentioned_character_ids")),
        "scheduled_character_ids": as_id_list(current_state.get("scheduled_character_ids")),
        "delayed_character_ids": as_id_list(current_state.get("delayed_character_ids")),
        "story_flags": compact_value(current_state.get("story_flags", {}), max_depth=2, max_items=8, max_text=120),
        "header_values": {
            "date_human": date_human,
            "time_human": time_human,
            "location_human": loc.get("header_name"),
            "weather_human": weather_human,
            "pov_state_human": pov_state_human,
            "context_human": context_human,
        },
    }


def header_contract() -> dict[str, Any]:
    return {
        "priority": "highest_for_header",
        "template_lines": [
            "📅 {date_human}",
            "🕒 {time_human}",
            "📍 Место: {location_human}",
            "🌤 Погода: {weather_human}",
            "🫀 Состояние Акиры: {pov_state_human}",
            "🎒 При себе / рядом: {context_human}",
        ],
        "omit_empty_lines": True,
        "rules": [
            "Use scene_contract.current_frame.header_values.",
            "Keep the header in this emoji format.",
            "🫀 is physical/internal state only: fatigue, hunger, pain, stress, injuries, short notes.",
            "🎒 is visible clothing/items/nearby objects: hoodie, jeans, bag, documents, phone, hair position, people nearby.",
            "Do not write dry/wet unless it is scene-relevant.",
            "If context_human is empty, omit the 🎒 line.",
        ],
    }


def response_format_contract() -> dict[str, Any]:
    return {
        "priority": "highest_for_scene_output",
        "scene_header_required": True,
        "meta_layer_forbidden": True,
        "dialogue_format": "**Имя или видимый дескриптор** — Реплика. (*короткая ремарка*)",
        "description_format": "*Описание действия/окружения отдельной строкой курсивом.*",
        "must_end_with": [
            "Что можно сделать: 1/2/3",
            "Что сказать: three quoted line options",
            "Мысли Акиры: three short true POV thoughts",
        ],
        "forbidden": [
            "technical commentary",
            "API/Actions/state/contract/debug mentions",
            "empty header before contract",
            "placeholder header fields",
            "Что делает Акира? instead of options",
            "freeform title header",
            "summary instead of scene",
            "generic polite line options for Akira v2",
        ],
        "quality_note": "Do not answer with a fast stub. Write a real scene with NPC dialogue, pressure and consequence.",
    }


def scene_density_contract() -> dict[str, Any]:
    return {
        "target_scene_beats": "4-6",
        "normal_scene_units": "7-12 short paragraphs/units; not a one-paragraph summary",
        "minimum_for_meaningful_scene": [
            "environment/system in motion",
            "visible POV observation",
            "active/nearby character-specific reaction or direct line",
            "concrete pressure/change",
            "world advances even if POV acts calmly",
            "no micro-action endings; continue to next meaningful choice",
            "real intervention point",
        ],
        "anti_null_scene": [
            "Do not end with nothing happened / nobody noticed unless another concrete trace exists.",
            "A careful action can reduce danger, not erase world reaction automatically.",
        ],
    }





def prose_style_contract() -> dict[str, Any]:
    return {
        "priority": "hard_style_gate",
        "core_rule": "Write clear factual scene prose, not decorative literary prose.",
        "style": [
            "short concrete sentences",
            "visible facts and physical consequences",
            "specific actions instead of abstract mood",
            "energy effects described as measurable physical traces",
            "NPC reactions through action/tone/look, not lyrical comparison",
        ],
        "avoid": [
            "poetic contrast descriptions",
            "decorative metaphors",
            "cinematic filler",
            "abstract atmosphere without consequence",
            "overexplaining what is already visible",
            "phrases like 'контрастируя с серостью коридора'",
            "phrases like 'словно сама сцена подстроилась'",
        ],
        "rewrite_examples": [
            {
                "bad": "Белые волосы отражают холодный свет панели, контрастируя с серостью коридора.",
                "good": "Белые волосы заметны в холодном свете панели.",
            },
            {
                "bad": "Воздух будто задержал дыхание.",
                "good": "Шум очереди стал тише на секунду.",
            },
            {
                "bad": "Система словно решила присмотреться к ней внимательнее.",
                "good": "На панели появилась серая пометка. Сотрудница задержала взгляд на браслете.",
            },
        ],
        "allowed_detail": "Descriptive detail is allowed only if it shows fact, pressure, physical state, energy trace, social reaction or consequence.",
    }


def scene_progress_contract() -> dict[str, Any]:
    return {
        "priority": "hard_scene_pacing_gate",
        "core_rule": "Do not stop on micro-actions. If the next step is obvious, narrate it and continue until a real decision/intervention point.",
        "micro_choices_forbidden": [
            "press a machine button",
            "wait for instructions",
            "look at the screen",
            "take a card",
            "walk to a nearby obvious point",
            "continue observing",
            "stand calmly",
            "repeat the same check with no new pressure",
        ],
        "real_choice_required": [
            "answer / stay silent when someone pressures POV",
            "obey official route / challenge / bypass / provoke",
            "hide energy / show controlled trace / risk a stronger move",
            "protect Livia / let her handle it / cut her off",
            "follow schedule / delay for information / exploit a mistake",
            "choose social position: sit, leave, approach, avoid, listen, confront",
        ],
        "auto_advance_rules": [
            "If user chooses an obvious transition, complete the transition and continue to the next meaningful pressure.",
            "If it is logical to get coffee, do not stop at the vending machine unless coffee itself creates pressure; take coffee and move to the social beat.",
            "If it is logical to pass registration, do not stop at 'wait for instructions'; give result, consequence, next route, and stop at the next real intervention.",
            "If nothing meaningful can happen in the current spot, summarize movement briefly and jump to the next scheduled/pressured beat.",
            "A calm/passive player action should still let the world advance.",
        ],
        "no_player_speech_without_input": "Do not write a direct Akira line unless the user gave it, or it is only an option in 'Что сказать'. Narration may describe her visible reaction.",
        "ending_rule": "End only when the player has a real decision, real reply, real risk, or real relationship/social consequence to choose.",
    }


def scene_quality_gate_contract() -> dict[str, Any]:
    return {
        "priority": "hard_quality_gate",
        "forbidden_fast_response_patterns": [
            "empty header before contract",
            "technical preface before scene",
            "summary instead of scene",
            "one-paragraph environment-only scene",
            "no direct NPC dialogue",
            "generic choices not tied to pressure",
            "passive player action causing passive world",
        ],
        "minimum_scene_requirements": [
            "Use filled header only after scene_contract is loaded.",
            "No visible API/contract/loading commentary.",
            "Scene body must be 7-12 short paragraphs/units for normal meaningful play.",
            "At least one active NPC must speak or make a character-specific visible move.",
            "At least one concrete pressure must change or press forward.",
            "Include at least one small ambient energy carrier detail unless scene location/state forbids it.",
            "If player action is passive, the world still advances: queue moves, staff calls, someone notices, route changes, rumor/attention starts.",
            "Do not stop at micro-actions; continue until a real choice/reply/risk exists.",
            "Choices must be in Akira's selected variant voice, not polite generic UI.",
            "Thoughts must be Akira's real tactical/poisonous thoughts, not author summary.",
        ],
        "rewrite_before_sending_if": [
            "header has empty fields",
            "scene contains 'нужно собрать контракт' or other technical text",
            "scene can be summarized as 'went calmly, observed, nothing happened'",
            "Livia is reduced to background/noise",
            "Akira v2 sounds polite or neutral",
            "there is no new pressure, consequence or intervention point",
        ],
    }


def npc_autonomy_contract() -> dict[str, Any]:
    return {
        "player_controls": ["POV actions", "POV speech", "POV attempts"],
        "player_does_not_control": ["NPC decisions", "NPC emotions", "NPC knowledge", "world/system reactions"],
        "rules": [
            "A player command to an NPC is an attempt, not a guaranteed result.",
            "A player thought is not world knowledge.",
            "NPCs act from goals, character, knowledge, relationships and pressure.",
            "Do not make NPCs helpful or compliant by default.",
        ],
    }


def relationship_behavior_contract() -> dict[str, Any]:
    return {
        "source": "relationship_slice + character_memory_slice",
        "levels": {
            "trust": "Higher trust allows softer proximity/protection; low trust creates guarded behavior.",
            "tension": "Sharpens tone, interruptions, avoidance, boundary-testing.",
            "respect": "Makes NPC take POV seriously even when disagreeing.",
            "curiosity": "Makes NPC observe, test, ask or approach again.",
            "jealousy": "Changes social positioning and indirect remarks.",
            "resentment": "Makes NPC remember slights and obstruct or cut colder.",
        },
        "behavior_next_rule": "behavior_next must influence the next relevant scene unless state prevents it.",
    }


def memory_write_contract() -> dict[str, Any]:
    return {
        "importance_levels": {
            "critical": "Must save: identity reveal, promise/debt, injury, access consequence, reputation shift, relationship turn, secret, major quote.",
            "high": "Save: sharp line changing tension/respect/curiosity, visible protection/refusal, suspicion, wrong belief, recurring pattern, seed.",
            "medium": "Save only if likely to matter later.",
            "low": "Do not save alone: routine movement, generic look, repeated banter, neutral observation.",
        },
        "spoken_line_rules": [
            "Save exact quotes only when they change relationship, reputation, knowledge, promise/debt, conflict, suspicion or future behavior.",
            "Do not save every line.",
        ],
    }


def knowledge_write_contract() -> dict[str, Any]:
    return {
        "rules": [
            "Knowledge requires source: saw, heard, was told, read, inferred from visible facts, or misunderstood.",
            "Suspicion is not certainty; store certainty/source.",
            "Player thought does not update NPC knowledge.",
            "Hidden lore is not character knowledge unless revealed in-scene with a source.",
        ],
    }


def scene_assembly_gate_contract() -> dict[str, Any]:
    return {
        "status": "hard_gate",
        "must_have": [
            "current_state",
            "scene_contract.current_frame.header_values",
            "header_contract",
            "response_format_contract",
            "scene_density_contract",
            "character_load_plan.full_character_ids",
            "character_slice runtime summaries",
            "relationship_slice",
            "knowledge_slice",
            "character_memory_slice",
            "npc_autonomy_contract",
            "relationship_behavior_contract",
            "memory_write_contract",
            "event_engine_slice",
        ],
        "failure_line": "Не удалось собрать scene assembly packet через Action. Без него я не продолжаю игровую сцену.",
        "no_fallback": [
            "Do not start from chat memory.",
            "Do not say the contract is too large and then write a safe intro.",
            "Do not expose API/debug/contract text.",
        ],
    }



def build_energy_atmosphere_slice(session_id: str, current_state: dict[str, Any], scene_ids: list[str]) -> dict[str, Any]:
    """Compact academy-energy background layer. Makes Academy feel like a place for energy carriers."""
    energy_index = safe_read_text("world/energy/energy_index.yaml", session_id, max_chars=600)
    atmosphere = safe_read_text("runtime/academy/energy_atmosphere.yaml", session_id, max_chars=1700)
    general = safe_read_text("world/energy/general_energy_rules.md", session_id, max_chars=900)
    classes = safe_read_text("world/energy/classes_and_levels.md", session_id, max_chars=1300)
    restrictions = safe_read_text("world/energy/restrictions.md", session_id, max_chars=900)

    active_energy: dict[str, Any] = {}
    for cid in scene_ids[:6]:
        folder = character_folder(cid)
        if not folder:
            continue
        energy_text = safe_read_text(f"characters/{folder}/energy.yaml", session_id, max_chars=900)
        if energy_text:
            active_energy[cid] = {
                "source": f"characters/{folder}/energy.yaml",
                "compact": trim_text(energy_text, 900),
            }

    current_location = current_state.get("current_location_id")
    current_time = current_state.get("current_time")
    energy_incidents = slice_state_items(
        state_container_items(read_json_state(session_id, "energy_incidents.json"), "items"),
        current_state,
        scene_ids,
        current_location if isinstance(current_location, str) else None,
        current_state.get("current_date") if isinstance(current_state.get("current_date"), str) else None,
        statuses={"active", "pending", "recent", "resolved_scene_hook"},
        max_items=3,
    )

    return {
        "priority": "ambient_required",
        "academy_rule": "Academy scenes must feel populated by young energy carriers, not ordinary students.",
        "sources": {
            "index": energy_index,
            "atmosphere": "runtime/academy/energy_atmosphere.yaml",
            "general": "world/energy/general_energy_rules.md",
            "classes": "world/energy/classes_and_levels.md",
            "restrictions": "world/energy/restrictions.md",
        },
        "atmosphere_compact": atmosphere,
        "general_rules_compact": general,
        "classes_compact": classes,
        "restrictions_compact": restrictions,
        "active_character_energy": active_energy,
        "energy_incidents": energy_incidents,
        "use_rules": [
            "Add 1-2 small energy background details in most Academy scenes.",
            "Use energy as physical consequence: heat, cold, pressure, light, vibration, smell, sensor reaction, body reaction or environmental change.",
            "Background energy must not steal the scene from POV/current beat.",
            "Do not make energy decorative magic or constant explosions.",
            "Students may show off, leak control under emotion, warm objects, cool air, vibrate surfaces, spark sensors, or get corrected by staff.",
            "Save meaningful energy slips/incidents through applyTurnResultSimple energy_incident_changes_json.",
        ],
    }


def build_scene_contract(session_id: str, current_state: dict[str, Any], mode: str) -> dict[str, Any]:
    selected = selected_character_ids(current_state)
    scene_ids = unique(selected["full"])
    arc_id = current_state.get("current_arc_id") or "arc_001_academy_start"
    arc_file = f"story/arcs/{arc_id}.yaml"
    location_id = current_state.get("current_location_id") or "loc_academy_main"
    location_files = LOCATION_REQUIRED_FILES.get(location_id, [])
    current_frame = build_current_frame(current_state, session_id)

    return {
        "version": "scene_contract_v4_compact_runtime_summaries",
        "mode": mode,
        "scene_assembly_gate": scene_assembly_gate_contract(),
        "current_frame": current_frame,
        "header_contract": header_contract(),
        "calendar_slice": build_calendar_slice(session_id, current_state),
        "arc_slice": {
            "source_file": arc_file,
            "content": safe_read_text(arc_file, session_id, max_chars=1200),
        },
        "location_slice": {
            "location_id": location_id,
            "source_files": location_files,
            "content": {path: safe_read_text(path, session_id, max_chars=800) for path in location_files[:2]},
        },
        "character_load_plan": {
            "full_character_ids": selected["full"],
            "reference_character_ids": selected["reference"][:6],
            "full_rule": "Use compact runtime summaries from character_slice for POV/active/nearby characters.",
            "reference_rule": "Mentioned/scheduled/delayed characters use runtime summaries only if they enter or matter.",
        },
        "character_slice": build_character_slice(session_id, current_state, selected["full"]),
        "character_memory_slice": build_character_memory_slice(session_id, scene_ids),
        "relationship_slice": build_relationship_slice(session_id, scene_ids),
        "relationship_behavior_contract": relationship_behavior_contract(),
        "knowledge_slice": build_knowledge_slice(session_id, scene_ids),
        "knowledge_write_contract": knowledge_write_contract(),
        "open_threads_slice": build_open_threads_slice(session_id, scene_ids),
        "shared_incidents_slice": build_shared_incidents_slice(session_id, scene_ids),
        "event_engine_slice": build_event_engine_slice(session_id, current_state, scene_ids),
        "energy_atmosphere_slice": build_energy_atmosphere_slice(session_id, current_state, scene_ids),
        "npc_autonomy_contract": npc_autonomy_contract(),
        "memory_write_contract": memory_write_contract(),
        "response_format_contract": response_format_contract(),
        "scene_density_contract": scene_density_contract(),
        "scene_quality_gate_contract": scene_quality_gate_contract(),
        "scene_progress_contract": scene_progress_contract(),
        "prose_style_contract": prose_style_contract(),
        "selection_rules": [
            "Use character_slice runtime_summary, not full behavior.md/voice.md, in normal play.",
            "Use relationship_slice and behavior_next before NPC reactions.",
            "Use knowledge_slice before NPC claims.",
            "Use event_engine_slice for pressure.",
            "Use energy_atmosphere_slice to keep Academy scenes visibly populated by energy carriers.",
            "Use scene_progress_contract: do not stop on micro-actions; advance to a real choice.",
            "Use prose_style_contract: clear facts, less decorative prose.",
            "After scene, save important memory by importance level, not every line.",
        ],
    }


@app.on_event("startup")
def startup() -> None:
    ensure_runtime_root()


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "status": "ok",
        "project": PROJECT_SLUG,
        "version": "3.4.8",
        "actions_schema": "/openapi-actions.json",
        "health": "/health",
        "debug_volume": "/debug/volume",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {"success": True, "project": PROJECT_SLUG, "version": "3.4.8", "time": utc_now()}


@app.get("/debug/volume")
def debug_volume() -> dict[str, Any]:
    try:
        return {"success": True, **debug_info()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/v1/sessions")
def create_session(req: CreateSessionRequest | None = None) -> dict[str, Any]:
    req = req or CreateSessionRequest()
    requested_session_id = req.session_id
    normalized_session_id = normalize_session_id_for_create(requested_session_id)
    sid, root_dir = ensure_session(normalized_session_id, reset=req.reset)
    return {
        "success": True,
        "session_id": sid,
        "session_root": str(root_dir),
        "state_root": str(session_state_root(sid)),
        "reset": req.reset,
        "requested_session_id": requested_session_id,
        "reserved_session_id_replaced": normalized_session_id is None and requested_session_id is not None,
        "next": {"turn_contract": f"/api/v1/sessions/{sid}/turn-contract"},
    }


@app.post("/api/v1/sessions/{session_id}/turn-contract")
def get_turn_contract(session_id: str, req: TurnContractRequest) -> dict[str, Any]:
    reject_reserved_session_id(session_id)
    sid, _ = ensure_session(session_id, reset=False)
    current_state = read_json_state(sid, "current_state.json")
    current_state = apply_user_variant_selection(sid, current_state, req.user_input)
    current_state = normalize_current_akira_variant_state(sid, current_state)
    required_files = build_required_files(current_state, req.mode)
    scene_contract = compact_scene_contract_for_tool(build_scene_contract(sid, current_state, req.mode))

    contents: dict[str, Any] = {}
    if req.include_file_contents:
        for path in required_files:
            try:
                contents[path] = trim(read_project_or_runtime_file(path, sid))
            except Exception as exc:
                contents[path] = {"error": str(exc), "truncated": False, "chars": 0, "content": ""}

    current_state_compact = compact_value(
        current_state,
        max_depth=2,
        max_items=8,
        max_text=140,
    )

    return {
        "success": True,
        "session_id": sid,
        "mode": req.mode,
        "is_game_turn": req.mode == "play",
        "current_state": current_state_compact,
        "scene_contract": scene_contract,
        "required_files": required_files[:32],
        "required_file_count": len(required_files),
        "required_file_contents": contents,
        "checks": [
            "Scene Assembly Gate is required before writing play scenes.",
            "Use compact runtime character summaries from character_slice.",
            "Do not fetch full behavior.md/voice.md in normal play unless summary missing.",
            "Use character_memory_slice, relationship_slice and knowledge_slice before NPC reactions.",
            "Do not continue from chat memory if Action/contract fails.",
            "After meaningful scene, call applyTurnResultSimple and save important memory only.",
            "Scene Quality Gate: no intermediate loading messages, no empty header, real pressure required.",
            "Energy atmosphere: Academy is for energy carriers; include small visible energy background detail.",
            "Scene Progress Gate: do not end on micro-actions; advance to real choice/reply/risk.",
            "Prose Style Gate: less artistic language; write clear physical facts and consequences.",
            "Scene Quality Gate: no fast stub, no empty header, no technical preface, real pressure required.",
        ],
    }


@app.post("/api/v1/sessions/{session_id}/apply-turn-result")
def apply_turn_result(session_id: str, req: ApplyTurnResultRequest) -> dict[str, Any]:
    reject_reserved_session_id(session_id)
    sid, _ = ensure_session(session_id, reset=False)
    state_root = session_state_root(sid)

    if req.technical:
        append_jsonl(
            session_root(sid) / "technical_history.jsonl",
            {"time": utc_now(), "scene_id": req.scene_id, "text": req.scene_text},
        )
        return {"success": True, "status": "technical_saved", "session_id": sid}

    append_jsonl(
        state_root / "scene_history.jsonl",
        {"time": utc_now(), "scene_id": req.scene_id, "scene_text": req.scene_text},
    )

    patch_map = [
        ("current_state.json", req.current_state_changes),
        ("knowledge_state.json", req.knowledge_changes),
        ("relationships.json", req.relationship_changes),
        ("open_threads.json", req.open_thread_changes),
        ("shared_incidents.json", req.shared_incident_changes),
        ("inventory_state.json", req.inventory_changes),
        ("event_seeds.json", req.event_seed_changes),
        ("event_queue.json", req.event_queue_changes),
        ("director_notes.json", req.director_note_changes),
        ("gossip_state.json", req.gossip_changes),
        ("rating_state.json", req.rating_changes),
        ("energy_incidents.json", req.energy_incident_changes),
    ]

    updated = ["scene_history.jsonl"]
    for filename, patch in patch_map:
        if patch:
            write_json_state(sid, filename, patch)
            updated.append(filename)

    for character_id, patch in req.character_memory_changes.items():
        if isinstance(patch, dict):
            path = state_root / "character_memory" / f"{character_id}.json"
            current = read_json(path, {})
            if not isinstance(current, dict):
                current = {}
            deep_merge(current, patch)
            current.setdefault("character_id", character_id)
            current["last_updated_scene_id"] = req.scene_id
            current["updated_at"] = utc_now()
            write_json_atomic(path, current)
            updated.append(f"character_memory/{character_id}.json")

    compaction = read_json_state(sid, "compaction_state.json")
    compaction["total_game_turns"] = int(compaction.get("total_game_turns", 0) or 0) + 1
    compaction["since_last_compaction"] = int(compaction.get("since_last_compaction", 0) or 0) + 1
    compaction["compact_every_turns"] = int(compaction.get("compact_every_turns", COMPACT_EVERY_TURNS) or COMPACT_EVERY_TURNS)
    compaction["needs_compaction"] = compaction["since_last_compaction"] >= compaction["compact_every_turns"]
    compaction["last_scene_id"] = req.scene_id
    compaction["updated_at"] = utc_now()
    write_state(sid, "compaction_state.json", compaction)
    updated.append("compaction_state.json")

    return {
        "success": True,
        "session_id": sid,
        "updated_files": updated,
        "needs_compaction": compaction.get("needs_compaction", False),
    }


@app.post("/api/v1/sessions/{session_id}/apply-turn-result-simple")
def apply_turn_result_simple(session_id: str, req: ApplyTurnResultSimpleRequest) -> dict[str, Any]:
    req = normalize_apply_turn_result_simple_request(req)
    return apply_turn_result(
        session_id,
        ApplyTurnResultRequest(
            scene_id=req.scene_id,
            scene_text=req.scene_text,
            technical=req.technical,
            current_state_changes=parse_json_text(req.current_state_changes_json, "current_state_changes_json"),
            knowledge_changes=parse_json_text(req.knowledge_changes_json, "knowledge_changes_json"),
            relationship_changes=parse_json_text(req.relationship_changes_json, "relationship_changes_json"),
            open_thread_changes=parse_json_text(req.open_thread_changes_json, "open_thread_changes_json"),
            shared_incident_changes=parse_json_text(req.shared_incident_changes_json, "shared_incident_changes_json"),
            inventory_changes=parse_json_text(req.inventory_changes_json, "inventory_changes_json"),
            character_memory_changes=parse_json_text(req.character_memory_changes_json, "character_memory_changes_json"),
            event_seed_changes=parse_json_text(req.event_seed_changes_json, "event_seed_changes_json"),
            event_queue_changes=parse_json_text(req.event_queue_changes_json, "event_queue_changes_json"),
            director_note_changes=parse_json_text(req.director_note_changes_json, "director_note_changes_json"),
            gossip_changes=parse_json_text(req.gossip_changes_json, "gossip_changes_json"),
            rating_changes=parse_json_text(req.rating_changes_json, "rating_changes_json"),
            energy_incident_changes=parse_json_text(req.energy_incident_changes_json, "energy_incident_changes_json"),
        ),
    )


@app.post("/api/v1/sessions/{session_id}/compact")
def compact_session(session_id: str, req: CompactRequest) -> dict[str, Any]:
    reject_reserved_session_id(session_id)
    sid, _ = ensure_session(session_id, reset=False)
    if req.recent_turns_md is not None:
        write_state(sid, "recent_turns.md", req.recent_turns_md)
    for filename, patch in req.state_updates.items():
        if isinstance(patch, dict) and filename.endswith(".json"):
            write_json_state(sid, filename, patch)
    compaction = read_json_state(sid, "compaction_state.json")
    compaction["last_compaction_at"] = utc_now()
    compaction["last_compaction_reason"] = req.reason
    compaction["since_last_compaction"] = 0
    compaction["needs_compaction"] = False
    write_state(sid, "compaction_state.json", compaction)
    return {"success": True, "session_id": sid, "status": "compacted"}


@app.get("/api/v1/sessions/{session_id}/state/{filename}")
def read_session_state_file(session_id: str, filename: str) -> PlainTextResponse:
    reject_reserved_session_id(session_id)
    try:
        safe_filename = safe_repo_path(filename)
        text = read_project_or_runtime_file(f"state/{safe_filename}", session_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PlainTextResponse(text)


@app.get("/api/v1/files/{file_path:path}")
def read_file(file_path: str, session_id: str | None = None) -> PlainTextResponse:
    try:
        text = read_project_or_runtime_file(safe_repo_path(file_path), session_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PlainTextResponse(text)


@app.get("/api/v1/file")
def read_file_query(path: str = Query(...), session_id: str | None = None) -> PlainTextResponse:
    try:
        text = read_project_or_runtime_file(safe_repo_path(path), session_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PlainTextResponse(text)


@app.get("/openapi-actions.json")
def openapi_actions() -> dict[str, Any]:
    server = PUBLIC_BASE_URL or "https://your-service.up.railway.app"
    return {
        "openapi": "3.1.0",
        "info": {"title": f"{PROJECT_SLUG} GPT Actions", "version": "3.4.8"},
        "servers": [{"url": server}],
        "paths": {
            "/health": {
                "get": {
                    "operationId": "healthCheck",
                    "summary": "Check API health",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/debug/volume": {
                "get": {
                    "operationId": "debugVolume",
                    "summary": "Check runtime volume",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/api/v1/sessions": {
                "post": {
                    "operationId": "createSession",
                    "summary": "Create a new runtime session",
                    "requestBody": {
                        "required": False,
                        "content": {"application/json": {"schema": CreateSessionRequest.model_json_schema()}},
                    },
                    "responses": {"200": {"description": "Session created"}},
                }
            },
            "/api/v1/sessions/{session_id}/turn-contract": {
                "post": {
                    "operationId": "getSessionTurnContract",
                    "summary": "Get compact smart scene contract for one turn",
                    "parameters": [
                        {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": TurnContractRequest.model_json_schema()}},
                    },
                    "responses": {"200": {"description": "Smart turn contract"}},
                }
            },
            "/api/v1/file": {
                "get": {
                    "operationId": "getProjectFileByQuery",
                    "summary": "Read one project or runtime file by query path",
                    "parameters": [
                        {"name": "path", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "session_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "Project or runtime file"}},
                }
            },
            "/api/v1/files/{file_path}": {
                "get": {
                    "operationId": "getProjectFile",
                    "summary": "Read one project or runtime file by path",
                    "parameters": [
                        {"name": "file_path", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "session_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "Project or runtime file"}},
                }
            },
            "/api/v1/sessions/{session_id}/apply-turn-result": {
                "post": {
                    "operationId": "applyTurnResult",
                    "summary": "Persist scene and state changes",
                    "parameters": [
                        {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": ApplyTurnResultRequest.model_json_schema()}},
                    },
                    "responses": {"200": {"description": "Saved"}},
                }
            },
            "/api/v1/sessions/{session_id}/apply-turn-result-simple": {
                "post": {
                    "operationId": "applyTurnResultSimple",
                    "summary": "Persist scene and state changes using JSON strings for GPT Actions",
                    "parameters": [
                        {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": ApplyTurnResultSimpleRequest.model_json_schema()}},
                    },
                    "responses": {
                        "200": {"description": "Saved"},
                        "400": {"description": "Invalid JSON in one of the JSON string fields"},
                    },
                }
            },
            "/api/v1/sessions/{session_id}/compact": {
                "post": {
                    "operationId": "compactSessionMemory",
                    "summary": "Persist memory compaction",
                    "parameters": [
                        {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": CompactRequest.model_json_schema()}},
                    },
                    "responses": {"200": {"description": "Compacted"}},
                }
            },
            "/api/v1/sessions/{session_id}/state/{filename}": {
                "get": {
                    "operationId": "getSessionStateFile",
                    "summary": "Read one runtime state file",
                    "parameters": [
                        {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "filename", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "State file"}},
                }
            },
        },
    }
