import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

APP_NAME = "Akira Academy Prequel API"
BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://akira-academy-prequel-production.up.railway.app").rstrip("/")
ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv("DATA_DIR", "/data"))

SYNC_FROM_REPO = ["canon", "characters", "gpt", "templates"]
STATE_SEED = ["state"]
SESSION_RE = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")

REL_METRICS = ["affection", "trust", "tension", "jealousy", "respect", "curiosity", "resentment"]

STATE_SECTION_MAP = [
    ("state/current_state.json", ["current_state_changes", "current_state", "state_changes"]),
    ("state/story_lines.json", ["story_lines_changes", "story_line_changes", "story_lines", "story_lines_state"]),
    ("state/knowledge_state.json", ["knowledge_changes", "knowledge_state_changes", "knowledge_state"]),
    ("state/reputation_state.json", ["reputation_changes", "reputation_state_changes", "reputation_state"]),
    ("state/rumors_state.json", ["rumor_changes", "rumors_changes", "rumors_state_changes", "rumors_state"]),
    ("state/inventory_state.json", ["inventory_changes", "inventory_state_changes", "inventory_state"]),
    ("state/power_state.json", ["power_changes", "power_state_changes", "power_state"]),
    ("state/future_locks_progress.json", ["future_locks_changes", "future_locks_progress_changes", "future_locks_progress"]),
]

app = FastAPI(title=APP_NAME, version="0.3.12", servers=[{"url": BASE_URL}])


class FileUpdate(BaseModel):
    content: str


class JsonUpdate(BaseModel):
    data: object


class SessionCreateRequest(BaseModel):
    session_id: str | None = None
    title: str | None = None


class ApplyTurnResultRequest(BaseModel):
    turn_file: str | None = None
    data: object | None = None
    dry_run: bool = False


class HealthResponse(BaseModel):
    status: str
    app: str
    data_dir: str
    volume_seeded: bool
    public_base_url: str


class RootResponse(BaseModel):
    app: str
    health: str
    context: str
    compact_context: str
    sessions: str
    files: str
    repair_start_state: str
    apply_turn_result: str
    openapi: str


class FilesResponse(BaseModel):
    data_dir: str
    files: list[str] = Field(default_factory=list)


class TextFileResponse(BaseModel):
    path: str
    content: str


class SaveResponse(BaseModel):
    status: str
    path: str
    bytes: int


class JsonFileResponse(BaseModel):
    path: str
    data: object


class SessionInfo(BaseModel):
    session_id: str
    title: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    context: str


class SessionsResponse(BaseModel):
    sessions: list[SessionInfo] = Field(default_factory=list)


class CompactContextResponse(BaseModel):
    session_id: str | None = None
    current_state: object | None = None
    story_lines: object | None = None
    relationships: object | None = None
    reputation_state: object | None = None
    power_state: object | None = None
    rumors_state: object | None = None
    knowledge_state: object | None = None
    inventory_state: object | None = None
    future_locks_progress: object | None = None
    academy_schedule: object | None = None
    api_usage_note: str
    recommended_files: list[str] = Field(default_factory=list)


class RepairResponse(BaseModel):
    status: str
    changed_files: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


MAIN_CHARACTER_FILES = {
    "akira": "characters/main/akira.md",
    "livia_cross": "characters/main/livia_cross.md",
    "livia": "characters/main/livia_cross.md",
    "raiden_sterling": "characters/main/raiden_sterling.md",
    "raiden": "characters/main/raiden_sterling.md",
    "haru_foster": "characters/main/haru_foster.md",
    "haru": "characters/main/haru_foster.md",
    "samuel_sterling": "characters/main/samuel_sterling.md",
    "samuel": "characters/main/samuel_sterling.md",
    "ray_carter": "characters/main/ray_carter.md",
    "ray": "characters/main/ray_carter.md",
    "jun_carter": "characters/main/jun_carter.md",
    "jun": "characters/main/jun_carter.md",
    "daniel_dante_weiss": "characters/main/daniel_dante_weiss.md",
    "daniel": "characters/main/daniel_dante_weiss.md",
    "dante": "characters/main/daniel_dante_weiss.md",
    "elias_aster": "characters/main/elias_seline_aster.md",
    "elias": "characters/main/elias_seline_aster.md",
    "seline_aster": "characters/main/elias_seline_aster.md",
    "seline": "characters/main/elias_seline_aster.md",
    "kael_north": "characters/main/kael_north.md",
    "kael": "characters/main/kael_north.md",
    "kiara_volt": "characters/main/kiara_volt.md",
    "kiara": "characters/main/kiara_volt.md",
    "noa_rian": "characters/main/noa_rian.md",
    "noa": "characters/main/noa_rian.md",
    "veronica_ellard": "characters/main/veronica_ellard.md",
    "veronica": "characters/main/veronica_ellard.md",
    "eiren_vale": "characters/main/eiren_vale.md",
    "eiren": "characters/main/eiren_vale.md",
}

CORE_RECOMMENDED_FILES = [
    "gpt/engine_prompt.md",
    "gpt/scene_format.md",
    "canon/novella_goal.md",
    "canon/character_story_roles.md",
    "canon/source_usage_rules.md",
    "canon/academy_rules_index.md",
    "canon/academy_combat_and_weapon_rules.md",
    "canon/character_depth_and_rotation.md",
    "canon/relationship_memory_rules.md",
    "characters/character_id_index.md",
    "state/memory_update_rules.md",
    "state/story_lines_extensions.md",
]

CORE_LOCK_FILES = [
    "gpt/locks/no_empty_scenes_lock.md",
    "gpt/locks/dialogue_format_strict_lock.md",
    "gpt/locks/apply_state_after_turn_lock.md",
    "gpt/locks/story_lines_memory_lock.md",
    "gpt/locks/character_presence_rotation_lock.md",
]

AKIRA_LOCK_FILES = [
    "characters/locks/akira_no_passive_glitches_lock.md",
    "characters/locks/akira_no_reused_player_lines_lock.md",
    "characters/locks/akira_micro_reactions_lock.md",
]

DEFAULT_STATE_FILES = [
    "state/story_lines.json",
    "state/knowledge_state.json",
    "state/relationships.json",
    "state/scene_history.json",
    "state/reputation_state.json",
    "state/rumors_state.json",
]


def safe(p: str) -> Path:
    path = Path(p)
    if path.is_absolute() or ".." in path.parts:
        raise HTTPException(status_code=400, detail="Unsafe path")
    return path


def safe_session_id(session_id: str) -> str:
    if not SESSION_RE.match(session_id):
        raise HTTPException(status_code=400, detail="Unsafe session_id")
    return session_id


def copy_missing(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.is_dir():
        for item in src.rglob("*"):
            if item.is_file():
                rel = item.relative_to(src)
                target = dst / rel
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target)
    elif not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def sync_from_repo(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.is_dir():
        for item in src.rglob("*"):
            if item.is_file():
                rel = item.relative_to(src)
                target = dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def seed() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    for name in SYNC_FROM_REPO:
        sync_from_repo(ROOT / name, DATA / name)
    for name in STATE_SEED:
        sync_from_repo(ROOT / name, DATA / name)
    (DATA / "sessions").mkdir(parents=True, exist_ok=True)
    (DATA / ".seeded").write_text("seeded\n", encoding="utf-8")


def session_dir(session_id: str) -> Path:
    return DATA / "sessions" / safe_session_id(session_id)


def ensure_session(session_id: str) -> Path:
    d = session_dir(session_id)
    if not d.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    return d


def file_root(session_id: str | None = None) -> Path:
    return ensure_session(session_id) if session_id else DATA


def read_text(path: str, session_id: str | None = None) -> str:
    file = file_root(session_id) / safe(path)
    if not file.exists() or not file.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return file.read_text(encoding="utf-8")


def save_text(path: str, content: str, session_id: str | None = None) -> dict:
    file = file_root(session_id) / safe(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content, encoding="utf-8")
    if session_id:
        touch_session(session_id)
    return {"path": path, "bytes": len(content.encode("utf-8"))}


def read_json(path: str, session_id: str | None = None, default=None):
    try:
        return json.loads(read_text(path, session_id=session_id))
    except HTTPException:
        return default


def write_json(path: str, data, session_id: str | None = None) -> None:
    save_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n", session_id=session_id)


def touch_session(session_id: str) -> None:
    meta_path = session_dir(session_id) / "session.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    meta["session_id"] = session_id
    meta["updated_at"] = datetime.utcnow().isoformat()
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = str(value).strip() if value else ""
        if item and item not in result:
            result.append(item)
    return result


def repo_file_exists(path: str) -> bool:
    return (ROOT / path).exists() or (DATA / path).exists()


def character_file(character_id: str) -> str:
    return MAIN_CHARACTER_FILES.get(character_id, f"characters/npc/{character_id}.md")


def active_scene_characters(current: dict[str, Any], future: dict[str, Any] | None = None) -> list[str]:
    future = future or {}
    active = list(current.get("active_characters", []) or [])
    nearby = list(current.get("nearby_characters", []) or [])
    speaking = list(current.get("speaking_character_ids", []) or [])
    observing = list(current.get("observing_character_ids", []) or [])
    addressed = list(current.get("addressed_character_ids", []) or [])
    looked_at = list(current.get("looked_at_character_ids", []) or [])

    triggered: list[str] = []
    for thread in current.get("open_threads", []) or []:
        if isinstance(thread, dict) and thread.get("status") in {"due", "active", "triggered"}:
            triggered.extend(thread.get("participants", []) or [])

    for lock in (future.get("locks") or {}).values():
        if isinstance(lock, dict) and lock.get("status") in {"due", "active", "triggered"}:
            triggered.extend(lock.get("participants", []) or [])

    return unique(["akira"] + active + nearby + speaking + observing + addressed + looked_at + triggered)


def character_lock_files(scene_chars: list[str]) -> list[str]:
    files = list(AKIRA_LOCK_FILES)

    if "livia_cross" in scene_chars or "livia" in scene_chars:
        files.extend([
            "characters/locks/livia_akira_friendship_lock.md",
            "characters/locks/akira_school_past_livia_dynamic_lock.md",
        ])

    if "raiden_sterling" in scene_chars or "raiden" in scene_chars:
        files.append("characters/locks/raiden_lazy_mask_social_lock.md")
        if "akira" in scene_chars:
            files.append("canon/hidden_raiden_akira_bond.md")

    if ("haru_foster" in scene_chars or "haru" in scene_chars) and (
        "raiden_sterling" in scene_chars or "raiden" in scene_chars
    ):
        files.append("characters/locks/haru_raiden_attraction_social_reactions_lock.md")

    return unique(files)


def recommended_files_for_context(current: dict[str, Any] | None = None, future: dict[str, Any] | None = None) -> list[str]:
    current = current or {}
    future = future or {}
    scene_chars = active_scene_characters(current, future)
    character_files = [character_file(cid) for cid in scene_chars]
    akira_profile_files = []
    profile_id = (current or {}).get("akira_behavior_profile")
    profiles = (current or {}).get("akira_behavior_profiles") or {}
    if profile_id and isinstance(profiles, dict):
        profile_file = profiles.get(profile_id)
        if profile_file:
            akira_profile_files.append(profile_file)
    files = unique(
        CORE_RECOMMENDED_FILES
        + CORE_LOCK_FILES
        + character_files
        + akira_profile_files
        + character_lock_files(scene_chars)
        + DEFAULT_STATE_FILES
    )
    return [path for path in files if repo_file_exists(path)]


def base_recommended_files() -> list[str]:
    return recommended_files_for_context({"active_characters": ["akira"]}, {})


def pair_in_focus(pair_id: str, focus_ids: set[str]) -> bool:
    parts = pair_id.split("__")
    return any(part in focus_ids for part in parts)


def compact_relationships(state: Any, focus_ids: list[str]) -> Any:
    if not isinstance(state, dict):
        return state
    focus = set(focus_ids or ["akira"])
    pairs = state.get("pairs")
    if isinstance(pairs, dict):
        filtered = {pair: data for pair, data in pairs.items() if pair_in_focus(str(pair), focus)}
        return {
            "pairs": filtered,
            "_context_filter": {
                "mode": "active_nearby_pairs_only",
                "focus_character_ids": sorted(focus),
                "visible_pairs": len(filtered),
                "total_pairs": len(pairs),
                "note": "Use /api/v1/sessions/{session_id}/json/state/relationships.json for full relationship memory when needed.",
            },
        }
    filtered = {key: value for key, value in state.items() if "__" in str(key) and pair_in_focus(str(key), focus)}
    if filtered:
        return {**filtered, "_context_filter": {"mode": "active_nearby_pairs_only", "focus_character_ids": sorted(focus), "visible_pairs": len(filtered), "total_keys": len(state)}}
    return state


def compact_knowledge(state: Any, focus_ids: list[str]) -> Any:
    if not isinstance(state, dict):
        return state
    focus = set(focus_ids or ["akira"])
    filtered = {cid: data for cid, data in state.items() if cid in focus}
    return {
        **filtered,
        "_context_filter": {
            "mode": "active_nearby_knowledge_only",
            "focus_character_ids": sorted(focus),
            "visible_characters": len(filtered),
            "total_characters": len(state),
            "note": "Use /api/v1/sessions/{session_id}/json/state/knowledge_state.json for full knowledge state when needed.",
        },
    }


def compact_story_lines(state: Any, focus_ids: list[str]) -> Any:
    if not isinstance(state, dict):
        return state
    focus = set(focus_ids or ["akira"])
    lines = state.get("lines")
    if not isinstance(lines, dict):
        return compact_if_large(state, 5500)

    visible = {}
    for line_id, line in lines.items():
        if not isinstance(line, dict):
            continue
        ids = set(line.get("character_ids", []) or []) | set(line.get("related_ids", []) or [])
        if ids & focus or line_id in {"line_academy", "line_reputation", "line_social_media_rumors", "line_obligations"}:
            visible[line_id] = line

    timeline = state.get("daily_timeline", {})
    shared_events = state.get("shared_events", [])
    if isinstance(shared_events, list) and len(shared_events) > 25:
        shared_events = shared_events[-25:]

    return {
        "schema": state.get("schema"),
        "turn_counter": state.get("turn_counter", {}),
        "calendar_policy": state.get("calendar_policy", {}),
        "daily_timeline": compact_if_large(timeline, 3000),
        "shared_events_recent": shared_events,
        "lines": visible,
        "_context_filter": {
            "mode": "active_nearby_story_lines_plus_global_lines",
            "focus_character_ids": sorted(focus),
            "visible_lines": list(visible.keys()),
            "total_lines": len(lines),
            "note": "Use /api/v1/sessions/{session_id}/json/state/story_lines.json for full story line memory.",
        },
    }


def compact_future_locks(state: Any) -> Any:
    if not isinstance(state, dict):
        return state
    locks = state.get("locks")
    if not isinstance(locks, dict):
        return state
    keep_status = {"active", "scheduled", "due", "triggered", "available_but_rare"}
    filtered = {lock_id: lock for lock_id, lock in locks.items() if isinstance(lock, dict) and lock.get("status") in keep_status}
    return {"locks": filtered, "_context_filter": {"mode": "active_or_scheduled_locks_only", "visible_locks": len(filtered), "total_locks": len(locks)}}


def compact_if_large(value: Any, max_chars: int = 4500) -> Any:
    try:
        dumped = json.dumps(value, ensure_ascii=False)
    except Exception:
        return value
    if len(dumped) <= max_chars:
        return value
    if isinstance(value, dict):
        return {"_context_filter": {"mode": "large_object_summary", "total_keys": len(value), "keys": list(value.keys())[:30], "note": "Object is too large for /context. Load exact file through /json or /files when needed."}}
    if isinstance(value, list):
        return {"_context_filter": {"mode": "large_list_summary", "total_items": len(value), "sample": value[:10], "note": "List is too large for /context. Load exact file through /json or /files when needed."}}
    return value


def context_payload(session_id: str | None = None) -> CompactContextResponse:
    seed()
    note = "Use /turn-contract every turn. /context is a balanced snapshot: active/nearby relationships, story lines and knowledge are shown; large full state files should be loaded through /json only when needed."
    current = read_json("state/current_state.json", session_id, default={}) or {}
    future = read_json("state/future_locks_progress.json", session_id, default={}) or {}
    focus_ids = active_scene_characters(current, future)
    return CompactContextResponse(
        session_id=session_id,
        current_state=current,
        story_lines=compact_story_lines(read_json("state/story_lines.json", session_id, default={}) or {}, focus_ids),
        relationships=compact_relationships(read_json("state/relationships.json", session_id, default={}) or {}, focus_ids),
        reputation_state=compact_if_large(read_json("state/reputation_state.json", session_id, default={}) or {}, 3500),
        power_state=compact_if_large(read_json("state/power_state.json", session_id, default={}) or {}, 3500),
        rumors_state=compact_if_large(read_json("state/rumors_state.json", session_id, default={}) or {}, 3500),
        knowledge_state=compact_knowledge(read_json("state/knowledge_state.json", session_id, default={}) or {}, focus_ids),
        inventory_state=compact_if_large(read_json("state/inventory_state.json", session_id, default={}) or {}, 3500),
        future_locks_progress=compact_future_locks(future),
        academy_schedule=compact_if_large(read_json("state/academy_schedule.json", session_id, default={}) or {}, 3500),
        api_usage_note=note,
        recommended_files=recommended_files_for_context(current, future),
    )


def repair_state(session_id: str | None = None) -> RepairResponse:
    seed()
    changed, notes = [], []
    current = read_json("state/current_state.json", session_id, default={}) or {}
    inventory = read_json("state/inventory_state.json", session_id, default={}) or {}
    active = current.setdefault("active_characters", [])
    nearby = current.setdefault("nearby_characters", [])
    if "akira" not in active:
        active.append("akira")
    if "livia_cross" not in active and "livia_cross" not in nearby:
        nearby.append("livia_cross")
        notes.append("Added livia_cross as nearby at academy start.")
    current.setdefault("visible_inventory", [])
    current.setdefault("nearby_items", [])
    current.setdefault("current_scene_goal", "прибытие в Академию Астрейн и первые социальные контакты")
    write_json("state/current_state.json", current, session_id)
    changed.append("state/current_state.json")

    akira_inv = inventory.setdefault("akira", {})
    akira_inv.setdefault("visible_inventory", [])
    akira_inv.setdefault("nearby_items", [])
    akira_inv.setdefault("academy_issued_items", [])
    for item in current.get("visible_inventory", []):
        if item not in akira_inv["visible_inventory"]:
            akira_inv["visible_inventory"].append(item)
    for item in current.get("nearby_items", []):
        if item not in akira_inv["nearby_items"]:
            akira_inv["nearby_items"].append(item)
    write_json("state/inventory_state.json", inventory, session_id)
    changed.append("state/inventory_state.json")
    return RepairResponse(status="repaired", changed_files=changed, notes=notes)


def output_format_contract() -> dict:
    return {
        "priority": "highest_for_scene_output",
        "dialogue_format": "**Имя или видимый дескриптор** — Реплика. (*короткая ремарка*)",
        "description_format": "*Описание действия, окружения или атмосферы отдельной строкой курсивом.*",
        "rules": [
            "Every spoken line starts with bold speaker name or visible descriptor.",
            "Do not use names Akira has not heard or read yet.",
            "After speaker name use long dash.",
            "Dialogue text is plain.",
            "Optional stage note must be short and italic in parentheses: (*тихо*), (*смеётся*), (*смотрит в сторону*).",
            "No stage notes like (тихо) without italic asterisks.",
            "No long actions in parentheses.",
            "No character thoughts in parentheses.",
            "Descriptions are separate italic paragraphs.",
            "No direct Akira thoughts inside the scene.",
            "Akira thoughts only in bottom block: Мысли Акиры.",
            "No empty scenes: every scene needs a hook, conflict, conversation, observation, social reaction, rumor, consequence, or time skip.",
            "Livia is Akira's close school friend for about six years, not a new roommate.",
            "Roommates, named NPCs, conflicts, character rotation and knowledge sources must persist/check through character_presence_rotation_lock.",
            "Events, obligations and dated memories must persist in state/story_lines.json; do not create one-scene state files.",
            "Check dialogue_format_strict_lock and story_lines_memory_lock; if any line violates them, rewrite before sending.",
            "Raiden is always dark-haired.",
            "Raiden does not patiently tolerate sticky female touches; trigger comes from stepmother history, but most people do not know that.",
            "Haru flirts easily, but tires when people see only the charismatic red-haired image, not him.",
            "No passive space or technical glitches around Akira without a direct reason.",
            "If output format is wrong, rewrite before sending.",
        ],
    }


def latest_turn_file(session_id: str) -> Path:
    root = ensure_session(session_id)
    candidates = []
    for folder in [root / "turn_results", root / "turns", DATA / "turn_results"]:
        if folder.exists():
            candidates += [p for p in folder.glob("turn_*.json") if p.is_file()]
    if not candidates:
        raise HTTPException(status_code=404, detail="No turn_results files found")
    return sorted(candidates, key=lambda p: p.name)[-1]


def read_turn_payload(session_id: str, req: ApplyTurnResultRequest) -> tuple[str, dict]:
    if isinstance(req.data, dict):
        return "inline", req.data
    root = ensure_session(session_id)
    if req.turn_file:
        safe_name = Path(req.turn_file).name
        candidates = [root / safe(req.turn_file), root / "turn_results" / safe_name]
        turn_path = next((p for p in candidates if p.exists() and p.is_file()), None)
        if turn_path is None:
            raise HTTPException(status_code=404, detail="Turn result file not found")
    else:
        turn_path = latest_turn_file(session_id)
    try:
        return str(turn_path.relative_to(root)), json.loads(turn_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid turn result JSON: {exc}") from exc


def deep_merge(dst, src):
    if not isinstance(src, dict):
        return dst
    if not isinstance(dst, dict):
        dst = {}
    for key, value in src.items():
        if isinstance(value, dict):
            dst[key] = deep_merge(dst.get(key, {}), value)
        elif isinstance(value, list):
            existing = dst.get(key, [])
            if not isinstance(existing, list):
                existing = []
            for item in value:
                if item not in existing:
                    existing.append(item)
            dst[key] = existing
        else:
            dst[key] = value
    return dst


def find_section(payload: dict, names: list[str]):
    for name in names:
        if name in payload:
            return payload[name]
    data = payload.get("data")
    if isinstance(data, dict):
        for name in names:
            if name in data:
                return data[name]
    return None


def normalize_change_items(section):
    if not section:
        return []
    if isinstance(section, dict):
        result = []
        for key, value in section.items():
            if isinstance(value, dict):
                result.append({"id": key, **value})
            else:
                result.append({"id": key, "value": value})
        return result
    if isinstance(section, list):
        return [x for x in section if isinstance(x, dict)]
    return []


def default_relationship(status: str = "отношения появились после сцены") -> dict:
    data = {metric: 0 for metric in REL_METRICS}
    data["status"] = status
    data["notes"] = []
    data["memory"] = []
    data["open_threads"] = []
    data["behavior_next"] = []
    data["triggers"] = []
    data["last_interaction"] = None
    return data


def merge_unique_list(rel: dict, field: str, value: Any) -> bool:
    if value is None:
        return False
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list):
        return False
    target = rel.setdefault(field, [])
    if not isinstance(target, list):
        target = []
        rel[field] = target
    changed = False
    for item in items:
        if item and item not in target:
            target.append(item)
            changed = True
    return changed


def apply_relationship_changes(session_id: str, payload: dict, dry_run: bool) -> bool:
    section = find_section(payload, ["relationship_changes", "relationships_changes", "relationship_deltas", "relationships"])
    items = normalize_change_items(section)
    if not items:
        return False
    state = read_json("state/relationships.json", session_id, default={}) or {}
    pairs = state.setdefault("pairs", {})
    changed = False
    for item in items:
        pair = item.get("pair") or item.get("pair_id") or item.get("id")
        if not pair or "__" not in str(pair):
            continue
        rel = pairs.setdefault(str(pair), default_relationship())
        for metric in REL_METRICS:
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
        write_json("state/relationships.json", state, session_id)
    return changed


def apply_json_section(session_id: str, payload: dict, file_path: str, names: list[str], dry_run: bool) -> bool:
    section = find_section(payload, names)
    if not isinstance(section, dict) or not section:
        return False
    state = read_json(file_path, session_id, default={}) or {}
    old_dump = json.dumps(state, ensure_ascii=False, sort_keys=True)
    new_state = deep_merge(state, section)
    new_dump = json.dumps(new_state, ensure_ascii=False, sort_keys=True)
    if new_dump != old_dump:
        if not dry_run:
            write_json(file_path, new_state, session_id)
        return True
    return False


@app.on_event("startup")
def startup():
    seed()


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", app=APP_NAME, data_dir=str(DATA), volume_seeded=(DATA / ".seeded").exists(), public_base_url=BASE_URL)


@app.get("/", response_model=RootResponse)
def root():
    return RootResponse(app=APP_NAME, health="/health", context="/api/v1/context", compact_context="/api/v1/context/compact", sessions="/api/v1/sessions", files="/api/v1/files", repair_start_state="/api/v1/repair/start-state", apply_turn_result="/api/v1/sessions/{session_id}/apply-turn-result", openapi="/openapi.json")


@app.post("/api/v1/sessions", response_model=SessionInfo)
def create_session(payload: SessionCreateRequest):
    seed()
    sid = safe_session_id(payload.session_id or f"session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}")
    d = session_dir(sid)
    if not d.exists():
        d.mkdir(parents=True, exist_ok=True)
        copy_missing(DATA / "state", d / "state")
        meta = {"session_id": sid, "title": payload.title or "Academy Prequel Session", "created_at": datetime.utcnow().isoformat(), "updated_at": datetime.utcnow().isoformat()}
        (d / "session.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta = read_json("session.json", sid) or {}
    return SessionInfo(session_id=sid, title=meta.get("title"), created_at=meta.get("created_at"), updated_at=meta.get("updated_at"), context=f"/api/v1/sessions/{sid}/context")


@app.get("/api/v1/sessions", response_model=SessionsResponse)
def list_sessions():
    seed()
    items = []
    for d in sorted((DATA / "sessions").iterdir() if (DATA / "sessions").exists() else []):
        if d.is_dir() and (d / "session.json").exists():
            meta = json.loads((d / "session.json").read_text(encoding="utf-8"))
            items.append(SessionInfo(session_id=meta.get("session_id", d.name), title=meta.get("title"), created_at=meta.get("created_at"), updated_at=meta.get("updated_at"), context=f"/api/v1/sessions/{d.name}/context"))
    return SessionsResponse(sessions=items)


@app.get("/api/v1/sessions/{session_id}/context", response_model=CompactContextResponse)
def session_context(session_id: str):
    return context_payload(safe_session_id(session_id))


@app.get("/api/v1/sessions/{session_id}/turn-contract")
def session_turn_contract(session_id: str):
    sid = safe_session_id(session_id)
    ensure_session(sid)
    current = read_json("state/current_state.json", sid, default={}) or {}
    knowledge = read_json("state/knowledge_state.json", sid, default={}) or {}
    inventory = read_json("state/inventory_state.json", sid, default={}) or {}
    future = read_json("state/future_locks_progress.json", sid, default={}) or {}
    story_lines = read_json("state/story_lines.json", sid, default={}) or {}
    active = unique(list(current.get("active_characters", []) or []))
    nearby = unique(list(current.get("nearby_characters", []) or []))
    scene_chars = active_scene_characters(current, future)
    locks = []
    for lock_id, lock in (future.get("locks") or {}).items():
        if lock.get("status") in {"active", "scheduled", "not_started", "available_but_rare"}:
            locks.append(f"{lock_id}: {lock.get('description', '')}")
    return {
        "session_id": sid,
        "active_character_ids": active,
        "nearby_character_ids": nearby,
        "required_files": recommended_files_for_context(current, future),
        "output_format_contract": output_format_contract(),
        "akira_behavior_profile_contract": {
            "active_profile": current.get("akira_behavior_profile", "akira_default_cold"),
            "available_profiles": current.get("akira_behavior_profiles", {}),
            "rule": "Use only the selected Akira behavior profile on top of characters/main/akira.md. Do not blend inactive Akira profiles. If user says 'используем Акиру-1/1', set akira_behavior_profile=akira_default_cold. If user says 'используем Акиру-2/2', set akira_behavior_profile=akira_post_kai_chaotic_mask."
        },
        "story_lines_contract": {
            "required_file": "state/story_lines.json",
            "schema": story_lines.get("schema"),
            "calendar_policy": story_lines.get("calendar_policy", {}),
            "turn_counter": story_lines.get("turn_counter", {}),
            "next_beats": story_lines.get("next_beats", {}),
            "rule": "Do not create one-scene state files. Store dated events, obligations, rumors, line progress, next_beats and compaction state in state/story_lines.json.",
        },
        "allowed_new_facts_this_turn": [
            "neutral sensory details",
            "minor gestures, pauses, tone, clothing details",
            "small social reactions from present characters",
            "new named NPC only if saved after scene when meaningful",
            "scene consequences derived from player input and current context",
        ],
        "forbidden_new_facts_this_turn": [
            "empty scenes where nothing happens and no line moves",
            "future 1206 events as current 1198 facts",
            "hidden nature of Akira revealed without scene basis",
            "Raiden hybrid nature revealed without scene basis",
            "NPC knowledge from unseen scenes",
            "new items without state update",
            "dialogue without bold speaker names",
            "dialogue remarks like (тихо) without italic asterisks; use (*тихо*)",
            "long actions inside dialogue parentheses",
            "direct Akira thoughts inside scene text",
            "one-scene state files instead of state/story_lines.json",
            "relative date words like yesterday without checking absolute event date",
            "Livia treated as new roommate/new acquaintance",
            "Roommate or named conflict NPC forgotten after scene",
            "Raiden described as light-haired",
            "Raiden treated as literally lazy or absent from academy life",
            "Raiden calmly accepting sticky female touches",
            "Haru treated as a flat womanizer without the image-vs-real-person reason",
            "passive space or technical glitches around Akira without cause",
            "social media becoming the main plot of every scene",
            "Haru or Raiden treated as invisible/unnoticed ordinary students in public academy scenes",
        ],
        "required_checks_before_answer": [
            "Load /turn-contract every turn.",
            "Use /context as a compact snapshot only; load full json files only when needed.",
            "Obey output_format_contract exactly.",
            "Read required_files before scene.",
            "Before writing Akira behavior, check current_state.akira_behavior_profile and load only the selected characters/variants profile; do not blend inactive Akira profiles.",
            "Check dialogue_format_strict_lock before sending; every spoken line must use **Name/descriptor** — speech. (*short italic remark*) when a remark is needed.",
            "Check story_lines_memory_lock before and after scene; dated events and obligations go to state/story_lines.json, not one-scene files.",
            "Check story_lines.next_beats before scene; use it as a mini-plan for near future hooks, not as a rigid script.",
            "If a next_beat is due by date or condition, show it, delay it with a reason, or close it with a consequence. Do not silently forget due beats.",
            "Check story_lines.turn_counter.since_last_compaction after every game turn.",
            "If since_last_compaction reaches 15, compact repeated minor events while preserving dates, knowledge sources, relationships, obligations, open threads, and meaningful remembered quotes.",
            "Do not count technical/debug/audit/rule-edit/API-check turns as game turns.",
            "Check active and nearby character cards before writing lines.",
            "Check character_id_index and character_presence_rotation before replacing a main supporting character with a random NPC.",
            "Check character_depth_and_rotation before reducing important characters to scene functions.",
            "Check relationship_memory_rules before using relationship scores as the only source.",
            "Check character_presence_rotation_lock before roommate, dorm, corridor conflict, named NPC, repeating NPC, character rotation, and knowledge-source scenes.",
            "Check academy social ecosystem before public scenes: ranking, status, rumors, social media, closed chats, and competition for attention must exist as background pressure.",
            "Do not make social media the main plot of every scene; use it as recurring background, consequence, rumor, or pressure.",
            "Before scenes with Haru, remember he is visible, popular, flirtatious, and attracts attention; some students may watch, gossip, compete, or try to sit closer.",
            "Before scenes with Raiden, remember he is visible, high-status, cold, feared and watched; his attention is valuable because he rarely gives it.",
            "Before cafeteria/training/ranking/social scenes, check who receives attention and who may react with jealousy, envy, interest, fear, or rivalry.",
            "Academy rivalry is not only about power: students also compete for status, partners, instructor attention, senior attention, rumors, and proximity to popular students.",
            "Check knowledge_state before every NPC claim.",
            "Before any NPC states a factual claim, verify a knowledge source: knowledge_state, participant, witness, heard_by, told_to, public_to, known_by, rumor, message, or duty access.",
            "If no knowledge source exists, rewrite the NPC line as a question, suspicion, visible reaction, wrong assumption, or silence.",
            "Do not treat story_lines or scene_history summaries as global NPC knowledge.",
            "After scene, save meaningful remembered quotes only: phrases that changed relationship, created a trigger, promise, threat, boundary, rumor, reputation effect, or future reaction. Do not save all dialogue.",
            "Check story_lines.calendar_policy before using 'вчера', 'позавчера' or 'несколько дней назад'.",
            "Check inventory_state before mentioning usable items.",
            "No empty scenes: if Akira goes for coffee/sleeps/walks, add a hook or compress to the next meaningful event.",
            "Livia has known Akira for about six years and knows Jun, Ray, windows/edges, no relationships, and public space energy.",
            "Raiden is strictly dark-haired.",
            "No passive tech/space glitches around Akira without direct cause.",
            "After scene, apply turn result to state files or call /api/v1/sessions/{session_id}/apply-turn-result.",
            "Rewrite before sending if format or locks are wrong.",
        ],
        "knowledge_table": {cid: knowledge.get(cid, {}) for cid in scene_chars},
        "inventory_contract": {"visible_inventory": current.get("visible_inventory", []), "nearby_items": current.get("nearby_items", []), "akira_inventory_state": (inventory.get("akira") or {})},
        "canon_locks": locks[:12],
    }


@app.post("/api/v1/sessions/{session_id}/apply-turn-result")
def apply_turn_result(session_id: str, request: ApplyTurnResultRequest = ApplyTurnResultRequest()):
    sid = safe_session_id(session_id)
    ensure_session(sid)
    source, payload = read_turn_payload(sid, request)
    changed_files = []
    if apply_relationship_changes(sid, payload, request.dry_run):
        changed_files.append("state/relationships.json")
    for path, names in STATE_SECTION_MAP:
        if apply_json_section(sid, payload, path, names, request.dry_run):
            changed_files.append(path)
    return {"status": "applied" if changed_files else "no_changes_detected", "session_id": sid, "source": source, "dry_run": request.dry_run, "changed_files": changed_files}


@app.get("/api/v1/sessions/{session_id}/json/{file_path:path}", response_model=JsonFileResponse)
def get_session_json(session_id: str, file_path: str):
    data = json.loads(read_text(file_path, safe_session_id(session_id)))
    return JsonFileResponse(path=file_path, data=data)


@app.put("/api/v1/sessions/{session_id}/json/{file_path:path}", response_model=SaveResponse)
def put_session_json(session_id: str, file_path: str, update: JsonUpdate):
    sid = safe_session_id(session_id)
    r = save_text(file_path, json.dumps(update.data, ensure_ascii=False, indent=2) + "\n", sid)
    return SaveResponse(status="saved", path=r["path"], bytes=r["bytes"])


@app.post("/api/v1/sessions/{session_id}/repair/start-state", response_model=RepairResponse)
def repair_session_start_state(session_id: str):
    return repair_state(safe_session_id(session_id))


@app.get("/api/v1/files", response_model=FilesResponse)
def list_files():
    seed()
    files = [str(p.relative_to(DATA)) for p in DATA.rglob("*") if p.is_file() and p.name != ".seeded"]
    return FilesResponse(data_dir=str(DATA), files=sorted(files))


@app.get("/api/v1/files/{file_path:path}", response_model=TextFileResponse)
def get_file(file_path: str):
    seed()
    return TextFileResponse(path=file_path, content=read_text(file_path))


@app.put("/api/v1/files/{file_path:path}", response_model=SaveResponse)
def put_file(file_path: str, update: FileUpdate):
    seed()
    r = save_text(file_path, update.content)
    return SaveResponse(status="saved", path=r["path"], bytes=r["bytes"])


@app.get("/api/v1/json/{file_path:path}", response_model=JsonFileResponse)
def get_json(file_path: str):
    try:
        data = json.loads(read_text(file_path))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    return JsonFileResponse(path=file_path, data=data)


@app.put("/api/v1/json/{file_path:path}", response_model=SaveResponse)
def put_json(file_path: str, update: JsonUpdate):
    r = save_text(file_path, json.dumps(update.data, ensure_ascii=False, indent=2) + "\n")
    return SaveResponse(status="saved", path=r["path"], bytes=r["bytes"])


@app.get("/api/v1/context", response_model=CompactContextResponse)
def context():
    return context_payload()


@app.get("/api/v1/context/compact", response_model=CompactContextResponse)
def compact_context():
    return context_payload()


@app.post("/api/v1/repair/start-state", response_model=RepairResponse)
def repair_start_state():
    return repair_state()
