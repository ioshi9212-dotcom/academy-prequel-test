"""
Runtime patch:
- clean YAML character files first;
- old md character files only as fallback;
- one gameplay response gate file;
- prompt_preview added to turn-contract;
- required files manifest/chunk endpoints added so GPT can load all required files without ResponseTooLargeError;
- OpenAPI schema for turn-contract includes prompt_preview.

No heavy lore. Adds player input anchor lock, visible-scene-before-state lock, chunked file loading, and apply-turn-result scene echo contract.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app import compact as base
from app.prompt_builder import build_prompt_preview

app = base.app
app.version = "0.3.13"

GAMEPLAY_RESPONSE_GATE_FILE = "gpt/locks/gameplay_response_gate.md"
PLAYER_INPUT_ANCHOR_LOCK_FILE = "gpt/locks/player_input_anchor_lock.md"
CURRENT_STATE_FILE = "state/current_state.json"
VISIBLE_SCENE_BEFORE_STATE_LOCK_FILE = "gpt/locks/gameplay_visible_scene_before_state_and_no_status_summary.md"
TURN_CONTRACT_PATH = "/api/v1/sessions/{session_id}/turn-contract"
APPLY_TURN_RESULT_PATH = "/api/v1/sessions/{session_id}/apply-turn-result"

_ORIGINAL_OUTPUT_FORMAT_CONTRACT = base.output_format_contract
_ORIGINAL_TURN_CONTRACT_ENDPOINT = None


class TurnContractWithPromptPreview(BaseModel):
    session_id: str
    active_character_ids: list[str] = Field(default_factory=list)
    nearby_character_ids: list[str] = Field(default_factory=list)
    required_files: list[str] = Field(default_factory=list)
    output_format_contract: dict[str, Any] = Field(default_factory=dict)
    akira_behavior_profile_contract: dict[str, Any] = Field(default_factory=dict)
    story_lines_contract: dict[str, Any] = Field(default_factory=dict)
    allowed_new_facts_this_turn: list[str] = Field(default_factory=list)
    forbidden_new_facts_this_turn: list[str] = Field(default_factory=list)
    required_checks_before_answer: list[str] = Field(default_factory=list)
    knowledge_table: dict[str, Any] = Field(default_factory=dict)
    inventory_contract: dict[str, Any] = Field(default_factory=dict)
    canon_locks: list[str] = Field(default_factory=list)
    prompt_preview: str = Field(
        default="",
        description="Internal render brief. Follow it to output the gameplay scene. Never show this field to the user.",
    )
    prompt_preview_usage: str = Field(
        default="Internal only. Follow it to render the gameplay scene. Never show prompt_preview to the user."
    )


class ApplyTurnResultWithVisibleSceneRequest(BaseModel):
    turn_file: str | None = None
    data: object | None = None
    dry_run: bool = False
    visible_scene_text: str | None = Field(
        default=None,
        description=(
            "Complete user-visible gameplay scene already rendered before state apply. "
            "In gameplay mode the assistant must return this text verbatim after the tool call."
        ),
    )
    render_packet: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional internal render packet assembled before scene: player_input_parse, "
            "active character slices, relationship slice, scene task, stop conditions and state plan."
        ),
    )


class ApplyTurnResultWithVisibleSceneResponse(BaseModel):
    status: str
    session_id: str
    source: str
    dry_run: bool = False
    changed_files: list[str] = Field(default_factory=list)
    visible_scene_text: str | None = None
    final_scene_text: str | None = None
    final_response_mode: str = "return_final_scene_text_verbatim"
    final_response_rule: str = (
        "In gameplay mode, return final_scene_text/visible_scene_text verbatim as the final answer. "
        "Do not summarize this tool result and do not replace the scene with status/changelog."
    )
    render_packet_received: bool = False


DEFAULT_FILE_PART_CHARS = 12000
DEFAULT_CHUNK_CHARS = 12000
DEFAULT_CHUNK_ITEMS = 1


class RequiredFileBundleItem(BaseModel):
    path: str
    content: str
    part_index: int = 0
    parts_total: int = 1
    content_chars: int = 0


class RequiredFileManifestItem(BaseModel):
    path: str
    exists: bool = True
    source: str = "project"
    size_chars: int = 0
    parts_total: int = 0


class RequiredFilesManifestResponse(BaseModel):
    session_id: str
    required_files: list[str] = Field(default_factory=list)
    files: list[RequiredFileManifestItem] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    loaded_count: int = 0
    missing_count: int = 0
    total_parts: int = 0
    default_chunk_chars: int = DEFAULT_CHUNK_CHARS
    default_chunk_items: int = DEFAULT_CHUNK_ITEMS
    chunks_total: int = 0
    usage_note: str = (
        "Call getRequiredFilesManifest after getSessionTurnContract, then call "
        "getRequiredFilesChunk with chunk_index=0..chunks_total-1 before rendering gameplay."
    )


class RequiredFilesChunkResponse(BaseModel):
    session_id: str
    required_files: list[str] = Field(default_factory=list)
    chunk_index: int = 0
    chunks_total: int = 0
    has_more: bool = False
    next_chunk_index: int | None = None
    loaded_files: list[RequiredFileBundleItem] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    loaded_count: int = 0
    missing_count: int = 0
    total_loaded_parts: int = 0
    usage_note: str = (
        "This is a size-limited chunk of required file contents. "
        "If has_more=true, call getRequiredFilesChunk again with next_chunk_index."
    )


NEW_CHARACTER_FOLDERS: dict[str, str] = {
    "akira": "akira", "char_akira": "akira",
    "livia": "livia", "livia_cross": "livia", "char_livia": "livia",
    "kir": "kir", "kir_knox": "kir", "char_kir": "kir",
    "haru": "haru", "haru_foster": "haru", "char_haru": "haru",
    "raiden": "raiden", "raiden_sterling": "raiden", "char_raiden": "raiden",
    "kiara": "kiara", "kiara_volt": "kiara", "char_kiara": "kiara",
    "kael": "kael_north", "kael_north": "kael_north", "char_kael_north": "kael_north",
}


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = str(value).strip() if value else ""
        if item and item not in result:
            result.append(item)
    return result


def character_files_for(character_id: str) -> list[str]:
    cid = str(character_id).strip()
    files: list[str] = []

    folder = NEW_CHARACTER_FOLDERS.get(cid)
    if folder:
        for rel in (
            f"characters/{folder}/main.yaml",
            f"characters/{folder}/character.yaml",
            f"characters/{folder}/past.yaml",
        ):
            if base.repo_file_exists(rel):
                files.append(rel)

    if files:
        return _unique(files)

    legacy = base.MAIN_CHARACTER_FILES.get(cid)
    if legacy and base.repo_file_exists(legacy):
        return [legacy]

    npc = f"characters/npc/{cid}.md"
    if base.repo_file_exists(npc):
        return [npc]

    return []


def character_file(character_id: str) -> str:
    files = character_files_for(character_id)
    if files:
        return files[0]
    return base.MAIN_CHARACTER_FILES.get(character_id, f"characters/npc/{character_id}.md")


def active_scene_characters(current: dict[str, Any], future: dict[str, Any] | None = None) -> list[str]:
    future = future or {}

    active = list(current.get("active_characters", []) or [])
    nearby = list(current.get("nearby_characters", []) or [])
    speaking = list(current.get("speaking_character_ids", []) or [])
    observing = list(current.get("observing_character_ids", []) or [])
    addressed = list(current.get("addressed_character_ids", []) or [])
    looked_at = list(current.get("looked_at_character_ids", []) or [])

    scheduled = list(current.get("scheduled_character_ids", []) or current.get("scheduled_characters", []) or [])
    mentioned = list(current.get("mentioned_character_ids", []) or current.get("mentioned_characters", []) or [])
    delayed = list(current.get("delayed_character_ids", []) or current.get("delayed_characters", []) or [])

    triggered: list[str] = []
    for thread in current.get("open_threads", []) or []:
        if isinstance(thread, dict) and thread.get("status") in {"due", "active", "triggered"}:
            triggered.extend(thread.get("participants", []) or [])

    for lock in (future.get("locks") or {}).values():
        if isinstance(lock, dict) and lock.get("status") in {"due", "active", "triggered"}:
            triggered.extend(lock.get("participants", []) or [])

    return _unique(["akira"] + active + nearby + speaking + observing + addressed + looked_at + scheduled + mentioned + delayed + triggered)


def recommended_files_for_context(current: dict[str, Any] | None = None, future: dict[str, Any] | None = None) -> list[str]:
    current = current or {}
    future = future or {}
    scene_chars = active_scene_characters(current, future)

    character_files: list[str] = []
    for cid in scene_chars:
        character_files.extend(character_files_for(cid))

    akira_profile_files: list[str] = []
    profile_id = current.get("akira_behavior_profile")
    profiles = current.get("akira_behavior_profiles") or {}
    if profile_id and isinstance(profiles, dict):
        profile_file = profiles.get(profile_id)
        if profile_file and base.repo_file_exists(profile_file):
            akira_profile_files.append(profile_file)

    files = _unique(
        base.CORE_RECOMMENDED_FILES
        + base.CORE_LOCK_FILES
        + ([GAMEPLAY_RESPONSE_GATE_FILE] if base.repo_file_exists(GAMEPLAY_RESPONSE_GATE_FILE) else [])
        + ([PLAYER_INPUT_ANCHOR_LOCK_FILE] if base.repo_file_exists(PLAYER_INPUT_ANCHOR_LOCK_FILE) else [])
        + ([CURRENT_STATE_FILE] if base.repo_file_exists(CURRENT_STATE_FILE) else [])
        + ([VISIBLE_SCENE_BEFORE_STATE_LOCK_FILE] if base.repo_file_exists(VISIBLE_SCENE_BEFORE_STATE_LOCK_FILE) else [])
        + character_files
        + akira_profile_files
        + base.character_lock_files(scene_chars)
        + base.DEFAULT_STATE_FILES
    )
    return [path for path in files if base.repo_file_exists(path)]


def base_recommended_files() -> list[str]:
    return recommended_files_for_context({"active_characters": ["akira"]}, {})


def output_format_contract() -> dict:
    contract = _ORIGINAL_OUTPUT_FORMAT_CONTRACT()
    rules = contract.setdefault("rules", [])
    extra_rules = [
        "Gameplay response must include the scene header. If missing, rewrite before sending.",
        "Gameplay response must include full scene body, not summary or recap.",
        "Gameplay response must include NPC/world reaction and at least one consequence, hook, observation, conflict, relationship movement or time movement.",
        "Gameplay response must include bottom block: Что можно сделать / Что Акира могла бы сказать / Мысли Акиры.",
        "Characters must act strictly according to loaded character files, relationship state, knowledge_state, current mood, goals, limits and scene pressure.",
        "If any character line or reaction contradicts the loaded character file, relationship state or knowledge source, rewrite before sending.",
        "Do not show API/debug/contract/saving commentary in gameplay mode.",
        "If any required section is missing, rewrite silently before sending. Do not apologize inside gameplay.",
        "Everything the player writes outside parentheses must appear verbatim as Akira's spoken line; never replace it with a recap.",
        "Everything inside parentheses is action/pause/body state/intention, not speech.",
        "If the player waits for registration/check/scanner, do not auto-complete the procedure; stop before the player-facing action.",
        "If the current player input contains no spoken text outside parentheses, do not create new Akira dialogue lines in the scene body; put possible Akira lines only in the bottom block.",
        "In gameplay mode, show the full visible scene before applying state; after apply-turn-result, the final visible answer must still be the gameplay scene, not status/summary.",
        "If apply-turn-result was called before a visible scene was shown, output a repair-render of that saved event without applying state again.",
        "Before calling apply-turn-result in gameplay mode, assemble complete visible_scene_text and pass it into apply-turn-result.",
        "After apply-turn-result returns, final answer must be exactly final_scene_text/visible_scene_text from the tool response, not a status summary.",
    ]
    for rule in extra_rules:
        if rule not in rules:
            rules.append(rule)
    contract["gameplay_response_gate"] = {
        "required": [
            "scene_header",
            "full_scene_body",
            "npc_or_world_reaction",
            "character_fidelity",
            "scene_movement_or_hook",
            "bottom_action_block",
            "akira_thoughts_block",
            "no_visible_technical_commentary",
        ],
        "rewrite_if_missing": True,
    }
    return contract


def _remove_existing_turn_contract_route():
    global _ORIGINAL_TURN_CONTRACT_ENDPOINT
    for route in list(app.router.routes):
        if getattr(route, "path", None) == TURN_CONTRACT_PATH and "GET" in (getattr(route, "methods", set()) or set()):
            if _ORIGINAL_TURN_CONTRACT_ENDPOINT is None:
                _ORIGINAL_TURN_CONTRACT_ENDPOINT = getattr(route, "endpoint", None)
            app.router.routes.remove(route)


def _remove_existing_apply_turn_result_route():
    for route in list(app.router.routes):
        if getattr(route, "path", None) == APPLY_TURN_RESULT_PATH and "POST" in (getattr(route, "methods", set()) or set()):
            app.router.routes.remove(route)


# Patch selector functions used by /context and /turn-contract.
base.character_files_for = character_files_for
base.character_file = character_file
base.active_scene_characters = active_scene_characters
base.recommended_files_for_context = recommended_files_for_context
base.base_recommended_files = base_recommended_files
base.output_format_contract = output_format_contract

_remove_existing_turn_contract_route()
_remove_existing_apply_turn_result_route()


@app.get(TURN_CONTRACT_PATH, response_model=TurnContractWithPromptPreview, operation_id="getSessionTurnContract")
def session_turn_contract_with_prompt_preview(session_id: str) -> TurnContractWithPromptPreview:
    sid = base.safe_session_id(session_id)
    base.ensure_session(sid)

    if _ORIGINAL_TURN_CONTRACT_ENDPOINT is not None:
        data = _ORIGINAL_TURN_CONTRACT_ENDPOINT(sid)
    else:
        data = {}

    if hasattr(data, "model_dump"):
        data = data.model_dump()
    elif not isinstance(data, dict):
        data = dict(data or {})

    current = base.read_json("state/current_state.json", sid, default={}) or {}
    knowledge = base.read_json("state/knowledge_state.json", sid, default={}) or {}
    inventory = base.read_json("state/inventory_state.json", sid, default={}) or {}
    future = base.read_json("state/future_locks_progress.json", sid, default={}) or {}
    story_lines = base.read_json("state/story_lines.json", sid, default={}) or {}
    relationships = base.read_json("state/relationships.json", sid, default={}) or {}

    required_files = recommended_files_for_context(current, future)
    scene_chars = active_scene_characters(current, future)

    data["session_id"] = sid
    data["active_character_ids"] = _unique(list(current.get("active_characters", []) or []))
    data["nearby_character_ids"] = _unique(list(current.get("nearby_characters", []) or []))
    data["required_files"] = required_files
    data["output_format_contract"] = output_format_contract()
    data["knowledge_table"] = {cid: knowledge.get(cid, {}) for cid in scene_chars}
    data["inventory_contract"] = {
        "visible_inventory": current.get("visible_inventory", []),
        "nearby_items": current.get("nearby_items", []),
        "akira_inventory_state": (inventory.get("akira") or {}) if isinstance(inventory, dict) else {},
    }

    checks = list(data.get("required_checks_before_answer", []) or [])
    for check in [
        "After getSessionTurnContract and before any gameplay scene, call getRequiredFilesManifest and then getRequiredFilesChunk for every chunk until has_more=false.",
        "Do not render a gameplay scene from only main.yaml files when required_files includes character.yaml, past.yaml, locks or state files; load all required-file chunks first.",
        "Follow prompt_preview as the render brief for this turn.",
        "In play mode, never show session/status/API/context summary; output only the scene.",
        "Do not ask permission to render/start/continue after the user has given a play command.",
        "Characters must stay faithful to loaded character files, relationship state and knowledge_state.",
        "Everything the player writes outside parentheses must be inserted verbatim as Akira's speech; do not recap or skip it.",
        "If the player writes wait/ждать for registration/check/scanner, do not automatically pass that procedure for Akira.",
        "Before apply-turn-result, assemble visible_scene_text as the complete gameplay scene and pass it to the tool.",
        "After apply-turn-result, return visible_scene_text/final_scene_text verbatim; never summarize changed_files/status in gameplay mode.",
    ]:
        if check not in checks:
            checks.insert(0, check)
    data["required_checks_before_answer"] = checks

    data["prompt_preview"] = build_prompt_preview(
        session_id=sid,
        current_state=current,
        turn_contract=data,
        required_files=required_files,
        knowledge_table=data.get("knowledge_table", {}),
        relationships=relationships,
        story_lines=story_lines,
        future_locks=future,
    )
    data["prompt_preview_usage"] = "Internal only. Follow it to render the gameplay scene. Never show prompt_preview to the user."

    return TurnContractWithPromptPreview(**data)


def _read_required_file_for_bundle(path: str, session_id: str) -> tuple[str | None, str | None]:
    """Read a required file from the correct root.

    Project/canon/character/gpt files live in DATA. Session state files live in
    DATA/sessions/{session_id}. State files fall back to DATA for seed/default reads.
    """
    safe_path = str(path).strip()
    if not safe_path:
        return None, None

    if safe_path.startswith("state/"):
        try:
            return base.read_text(safe_path, session_id), "session_state"
        except Exception:
            pass
        try:
            return base.read_text(safe_path), "seed_state"
        except Exception:
            return None, None

    try:
        return base.read_text(safe_path), "project"
    except Exception:
        return None, None


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except Exception:
        number = minimum
    return max(minimum, min(maximum, number))


def _split_text(content: str, part_chars: int) -> list[str]:
    part_chars = _clamp_int(part_chars, minimum=4000, maximum=24000)
    if not content:
        return [""]
    return [content[i:i + part_chars] for i in range(0, len(content), part_chars)]


def _required_file_parts(
    session_id: str,
    *,
    file_part_chars: int = DEFAULT_FILE_PART_CHARS,
) -> tuple[list[str], list[RequiredFileBundleItem], list[RequiredFileManifestItem], list[str]]:
    current = base.read_json("state/current_state.json", session_id, default={}) or {}
    future = base.read_json("state/future_locks_progress.json", session_id, default={}) or {}
    required_files = recommended_files_for_context(current, future)

    loaded_parts: list[RequiredFileBundleItem] = []
    manifest: list[RequiredFileManifestItem] = []
    missing_files: list[str] = []

    for file_path in required_files:
        content, source = _read_required_file_for_bundle(file_path, session_id)
        if content is None:
            missing_files.append(file_path)
            manifest.append(RequiredFileManifestItem(path=file_path, exists=False, source="missing"))
            continue

        pieces = _split_text(content, file_part_chars)
        parts_total = len(pieces)
        manifest.append(
            RequiredFileManifestItem(
                path=file_path,
                exists=True,
                source=source or "project",
                size_chars=len(content),
                parts_total=parts_total,
            )
        )
        for index, piece in enumerate(pieces):
            loaded_parts.append(
                RequiredFileBundleItem(
                    path=file_path,
                    content=piece,
                    part_index=index,
                    parts_total=parts_total,
                    content_chars=len(piece),
                )
            )

    return required_files, loaded_parts, manifest, missing_files


def _chunk_loaded_parts(
    loaded_parts: list[RequiredFileBundleItem],
    *,
    max_chars: int = DEFAULT_CHUNK_CHARS,
    max_items: int = DEFAULT_CHUNK_ITEMS,
) -> list[list[RequiredFileBundleItem]]:
    max_chars = _clamp_int(max_chars, minimum=8000, maximum=70000)
    max_items = _clamp_int(max_items, minimum=1, maximum=10)

    chunks: list[list[RequiredFileBundleItem]] = []
    current: list[RequiredFileBundleItem] = []
    current_chars = 0

    for part in loaded_parts:
        part_chars = len(part.content or "")
        if current and (len(current) >= max_items or current_chars + part_chars > max_chars):
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(part)
        current_chars += part_chars

    if current:
        chunks.append(current)
    return chunks


def _required_files_chunk_response(
    session_id: str,
    *,
    chunk_index: int = 0,
    max_chars: int = DEFAULT_CHUNK_CHARS,
    max_items: int = DEFAULT_CHUNK_ITEMS,
) -> RequiredFilesChunkResponse:
    sid = base.safe_session_id(session_id)
    base.ensure_session(sid)

    required_files, loaded_parts, _manifest, missing_files = _required_file_parts(sid)
    chunks = _chunk_loaded_parts(loaded_parts, max_chars=max_chars, max_items=max_items)
    chunks_total = len(chunks)

    safe_chunk_index = _clamp_int(chunk_index, minimum=0, maximum=max(chunks_total - 1, 0)) if chunks_total else 0
    selected = chunks[safe_chunk_index] if chunks_total else []
    has_more = bool(chunks_total and safe_chunk_index < chunks_total - 1)
    next_chunk_index = safe_chunk_index + 1 if has_more else None

    return RequiredFilesChunkResponse(
        session_id=sid,
        required_files=required_files,
        chunk_index=safe_chunk_index,
        chunks_total=chunks_total,
        has_more=has_more,
        next_chunk_index=next_chunk_index,
        loaded_files=selected,
        missing_files=missing_files,
        loaded_count=len({part.path for part in loaded_parts}),
        missing_count=len(missing_files),
        total_loaded_parts=len(loaded_parts),
    )


@app.get("/api/v1/sessions/{session_id}/required-files-manifest", response_model=RequiredFilesManifestResponse, operation_id="getRequiredFilesManifest")
def get_required_files_manifest(session_id: str) -> RequiredFilesManifestResponse:
    sid = base.safe_session_id(session_id)
    base.ensure_session(sid)

    required_files, loaded_parts, manifest, missing_files = _required_file_parts(sid)
    chunks = _chunk_loaded_parts(loaded_parts)

    return RequiredFilesManifestResponse(
        session_id=sid,
        required_files=required_files,
        files=manifest,
        missing_files=missing_files,
        loaded_count=len([item for item in manifest if item.exists]),
        missing_count=len(missing_files),
        total_parts=len(loaded_parts),
        chunks_total=len(chunks),
    )


@app.get("/api/v1/sessions/{session_id}/required-files-chunk", response_model=RequiredFilesChunkResponse, operation_id="getRequiredFilesChunk")
def get_required_files_chunk(
    session_id: str,
    chunk_index: int = 0,
    max_chars: int = DEFAULT_CHUNK_CHARS,
    max_items: int = DEFAULT_CHUNK_ITEMS,
) -> RequiredFilesChunkResponse:
    return _required_files_chunk_response(
        session_id,
        chunk_index=chunk_index,
        max_chars=max_chars,
        max_items=max_items,
    )


@app.get("/api/v1/sessions/{session_id}/required-files-bundle", response_model=RequiredFilesChunkResponse, operation_id="getRequiredFilesBundle")
def get_required_files_bundle(
    session_id: str,
    chunk_index: int = 0,
    max_chars: int = DEFAULT_CHUNK_CHARS,
    max_items: int = DEFAULT_CHUNK_ITEMS,
) -> RequiredFilesChunkResponse:
    """Backward-compatible endpoint name.

    v1 returned all files in one large response and could hit ResponseTooLargeError.
    v2 returns a size-limited chunk. Use has_more/next_chunk_index to continue.
    """
    return _required_files_chunk_response(
        session_id,
        chunk_index=chunk_index,
        max_chars=max_chars,
        max_items=max_items,
    )


@app.post(APPLY_TURN_RESULT_PATH, response_model=ApplyTurnResultWithVisibleSceneResponse, operation_id="applyTurnResult")
def apply_turn_result_with_visible_scene(
    session_id: str,
    request: ApplyTurnResultWithVisibleSceneRequest = ApplyTurnResultWithVisibleSceneRequest(),
) -> ApplyTurnResultWithVisibleSceneResponse:
    """Apply state changes while echoing the already-rendered gameplay scene.

    The backend is not a renderer. GPT must assemble visible_scene_text before this
    call. This endpoint persists state and returns that scene text back so the
    final assistant answer can be the scene, not a tool-status summary.
    """
    sid = base.safe_session_id(session_id)
    base.ensure_session(sid)

    source, payload = base.read_turn_payload(sid, request)
    changed_files: list[str] = []

    if base.apply_relationship_changes(sid, payload, request.dry_run):
        changed_files.append("state/relationships.json")

    for path, names in base.STATE_SECTION_MAP:
        if base.apply_json_section(sid, payload, path, names, request.dry_run):
            changed_files.append(path)

    scene_text = request.visible_scene_text
    return ApplyTurnResultWithVisibleSceneResponse(
        status="applied" if changed_files else "no_changes_detected",
        session_id=sid,
        source=source,
        dry_run=request.dry_run,
        changed_files=changed_files,
        visible_scene_text=scene_text,
        final_scene_text=scene_text,
        render_packet_received=isinstance(request.render_packet, dict),
    )

def patch_after_routes() -> None:
    """
    Patch app.session_routes after it is imported by app.server.
    This covers optional legacy constants, without adding extra routes.
    """
    try:
        import app.session_routes as routes
    except Exception:
        return

    routes.character_file = character_file

    if hasattr(routes, "BASE_REQUIRED_FILES"):
        base_required = list(getattr(routes, "BASE_REQUIRED_FILES", []) or [])
        for required_path in (GAMEPLAY_RESPONSE_GATE_FILE, PLAYER_INPUT_ANCHOR_LOCK_FILE, CURRENT_STATE_FILE, VISIBLE_SCENE_BEFORE_STATE_LOCK_FILE):
            if required_path not in base_required and base.repo_file_exists(required_path):
                base_required.append(required_path)
        routes.BASE_REQUIRED_FILES = base_required

    if hasattr(routes, "OUTPUT_FORMAT_CONTRACT"):
        contract = getattr(routes, "OUTPUT_FORMAT_CONTRACT", {})
        if isinstance(contract, dict):
            rules = contract.setdefault("rules", [])
            for rule in [
                "Gameplay response must include scene header.",
                "Gameplay response must not be a compressed summary or recap.",
                "Gameplay response must include bottom block: Что можно сделать / Что Акира могла бы сказать / Мысли Акиры.",
                "Characters must act strictly according to loaded character files, relationship state and knowledge_state.",
                "No visible API/debug/contract commentary in gameplay mode.",
                "If required section is missing, rewrite before sending.",
            ]:
                if rule not in rules:
                    rules.append(rule)
            contract["gameplay_response_gate"] = {
                "required": [
                    "scene_header",
                    "full_scene_body",
                    "npc_or_world_reaction",
                    "character_fidelity",
                    "scene_movement_or_hook",
                    "bottom_action_block",
                    "akira_thoughts_block",
                    "no_visible_technical_commentary",
                ],
                "rewrite_if_missing": True,
            }
            routes.OUTPUT_FORMAT_CONTRACT = contract
