"""Compact scene-packet runtime patch for Academy Prequel TEST.

Fixes GPT Actions ResponseTooLargeError by making getScenePacket small by default.
Adds:
GET /api/v1/sessions/{session_id}/scene-packet
operationId: getScenePacket
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Import current runtime first, then patch on top of it.
import app.context_transport_header_hotfix as header_hotfix  # noqa: F401
from app.context_transport_header_hotfix import app
from app import compact as base
import app.context_transport_runtime_patch as rt

app.version = "0.3.61-compact-scene-packet"

SCENE_PACKET_PATH = "/api/v1/sessions/{session_id}/scene-packet"
DEFAULT_SCENE_PACKET_MAX_CHARS = 16000
HARD_MAX_SCENE_PACKET_CHARS = 24000


class ScenePacketSource(BaseModel):
    path: str
    source: str = "project"
    content: str
    content_chars: int = 0
    truncated: bool = False


class ScenePacketResponse(BaseModel):
    session_id: str
    packet_version: str = "variant_a_compact_scene_packet_v2"
    mode: str = "play"
    usage_note: str
    final_output_rule: str
    current_frame: dict[str, Any] = Field(default_factory=dict)
    scene_character_ids: list[str] = Field(default_factory=list)
    required_files: list[str] = Field(default_factory=list)
    file_manifest: list[dict[str, Any]] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    scene_context_digest: str = ""
    focused_sources: list[ScenePacketSource] = Field(default_factory=list)
    source_budget: dict[str, Any] = Field(default_factory=dict)
    output_format_contract: dict[str, Any] = Field(default_factory=dict)
    save_contract: dict[str, Any] = Field(default_factory=dict)
    fallback_actions: dict[str, Any] = Field(default_factory=dict)


def _trim(text: Any, limit: int) -> tuple[str, bool]:
    value = "" if text is None else str(text)
    limit = max(0, int(limit))
    if len(value) <= limit:
        return value, False
    return value[:limit].rstrip() + "\n...[truncated]", True


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result


def _compact_current_frame(current: dict[str, Any]) -> dict[str, Any]:
    last_input, last_input_truncated = _trim(current.get("last_player_input"), 900)
    return {
        "current_date": current.get("current_date"),
        "current_time": current.get("current_time"),
        "current_day_part": current.get("current_day_part"),
        "current_location_id": current.get("current_location_id"),
        "current_location_text": current.get("current_location_text"),
        "current_scene_goal": current.get("current_scene_goal"),
        "scene_tags": current.get("scene_tags", []),
        "akira_state": current.get("akira_state"),
        "current_outfit": current.get("current_outfit"),
        "uniform_worn": current.get("uniform_worn"),
        "visible_inventory": current.get("visible_inventory", []),
        "nearby_items": current.get("nearby_items", []),
        "active_characters": current.get("active_characters", []),
        "nearby_characters": current.get("nearby_characters", []),
        "speaking_character_ids": current.get("speaking_character_ids", []),
        "observing_character_ids": current.get("observing_character_ids", []),
        "addressed_character_ids": current.get("addressed_character_ids", []),
        "looked_at_character_ids": current.get("looked_at_character_ids", []),
        "mentioned_character_ids": current.get("mentioned_character_ids", []),
        "scheduled_character_ids": current.get("scheduled_character_ids", []),
        "delayed_character_ids": current.get("delayed_character_ids", []),
        "story_flags": current.get("story_flags", {}),
        "last_player_input": last_input,
        "last_player_input_truncated": last_input_truncated,
    }


def _slim_manifest(manifest: list[Any], limit: int = 30) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in manifest[:limit]:
        data: dict[str, Any]
        if hasattr(item, "model_dump"):
            data = item.model_dump()
        elif isinstance(item, dict):
            data = item
        else:
            continue
        out.append({
            "path": data.get("path"),
            "source": data.get("source"),
            "chars": data.get("chars") or data.get("content_chars") or data.get("size"),
            "missing": data.get("missing", False),
        })
    if len(manifest) > limit:
        out.append({"path": "...[manifest truncated]", "remaining_items": len(manifest) - limit})
    return out


def _focused_source_paths(scene_character_ids: list[str]) -> list[str]:
    paths: list[str] = []
    for path in [
        "gpt/locks/runtime_scene_rules_digest.md",
        "gpt/scene_format.md",
        "characters/character_id_index.md",
    ]:
        if base.repo_file_exists(path):
            paths.append(path)

    # Keep only currently relevant character files. Avoid loading every required file.
    for cid in scene_character_ids:
        for path in rt.character_files_for_context(cid, include_past=True):
            paths.append(path)
    return _dedupe(paths)


def _preferred_limit(path: str, remaining: int) -> int:
    if "/character.yaml" in path:
        return min(3200, remaining)
    if "/main.yaml" in path:
        return min(1800, remaining)
    if "/past.yaml" in path:
        return min(1600, remaining)
    if path.endswith("runtime_scene_rules_digest.md"):
        return min(2200, remaining)
    if path.endswith("scene_format.md"):
        return min(1800, remaining)
    return min(1300, remaining)


def _add_source(sources: list[ScenePacketSource], path: str, sid: str, remaining: int) -> int:
    if remaining <= 900:
        return remaining
    content, source = rt.read_required_file_for_bundle(path, sid)
    if content is None:
        return remaining
    limit = max(500, _preferred_limit(path, remaining))
    trimmed, truncated = _trim(content, limit)
    sources.append(ScenePacketSource(
        path=path,
        source=source or "project",
        content=trimmed,
        content_chars=len(trimmed),
        truncated=truncated,
    ))
    return remaining - len(trimmed)


def _compact_output_contract() -> dict[str, Any]:
    return {
        "scene_format": "Use Academy scene header, body, and bottom choice blocks from instructions/current rules.",
        "dialogue": "**Name** — Replica. (*short action note*)",
        "do_not_show": ["API", "JSON", "session_id", "debug", "file lists", "tool status"],
        "do_not_write_for_akira": "Do not answer for Akira on direct questions/challenges.",
    }


def build_scene_packet(session_id: str, *, max_chars: int = DEFAULT_SCENE_PACKET_MAX_CHARS) -> ScenePacketResponse:
    sid = base.safe_session_id(session_id)
    base.ensure_session(sid)

    try:
        requested = int(max_chars or DEFAULT_SCENE_PACKET_MAX_CHARS)
    except Exception:
        requested = DEFAULT_SCENE_PACKET_MAX_CHARS
    max_chars = max(9000, min(requested, HARD_MAX_SCENE_PACKET_CHARS))

    current = base.read_json("state/current_state.json", sid, default={}) or {}
    future = base.read_json("state/future_locks_progress.json", sid, default={}) or {}
    scene_character_ids = rt.scene_character_ids(current, future)

    required_files, _loaded_parts, manifest, missing_files = rt.required_file_parts_safe(sid)

    digest_full = rt.build_scene_context_digest(sid)
    digest_limit = max(4500, min(8000, max_chars // 2))
    scene_context_digest, digest_truncated = _trim(digest_full, digest_limit)

    remaining = max_chars - len(scene_context_digest)
    sources: list[ScenePacketSource] = []
    for path in _focused_source_paths(scene_character_ids):
        remaining = _add_source(sources, path, sid, remaining)
        if remaining <= 900 or len(sources) >= 8:
            break

    save_contract = {
        "after_scene": "Call applyTurnResult after a meaningful gameplay scene.",
        "visible_scene_text": "Pass only the final visible scene text.",
        "save_only": ["state", "relationships", "knowledge", "reputation", "rumors", "inventory", "important hooks"],
        "do_not_save": ["debug", "technical turns", "decorative lines", "unknown hidden facts"],
    }

    fallback_actions = {
        "normal_play": "Use scene-packet first.",
        "if_need_full_sources": ["getRequiredFilesManifest", "getRequiredFilesChunk"],
        "if_packet_failed": "Retry getScenePacket with max_chars=9000. If it still fails, use context/turn-contract/chunks.",
    }

    return ScenePacketResponse(
        session_id=sid,
        usage_note="Compact scene-packet for GPT Actions. Do not reveal API/debug details to user.",
        final_output_rule="Final answer in play mode must be the gameplay scene only.",
        current_frame=_compact_current_frame(current),
        scene_character_ids=scene_character_ids,
        required_files=required_files[:60],
        file_manifest=_slim_manifest(manifest),
        missing_files=missing_files[:40],
        scene_context_digest=scene_context_digest,
        focused_sources=sources,
        source_budget={
            "max_chars_requested": max_chars,
            "digest_chars": len(scene_context_digest),
            "digest_truncated": digest_truncated,
            "focused_sources_chars": sum(src.content_chars for src in sources),
            "focused_sources_count": len(sources),
            "manifest_truncated": len(manifest) > 30,
            "required_files_truncated": len(required_files) > 60,
            "hard_response_goal": "avoid GPT Actions ResponseTooLargeError",
        },
        output_format_contract=_compact_output_contract(),
        save_contract=save_contract,
        fallback_actions=fallback_actions,
    )


@app.get(SCENE_PACKET_PATH, response_model=ScenePacketResponse, operation_id="getScenePacket")
def get_scene_packet(session_id: str, max_chars: int = DEFAULT_SCENE_PACKET_MAX_CHARS) -> ScenePacketResponse:
    return build_scene_packet(session_id, max_chars=max_chars)


_ORIGINAL_OPENAPI = app.openapi


def _object_schema(properties: dict | None = None, *, required: list[str] | None = None) -> dict:
    schema = {"type": "object", "properties": properties or {}, "additionalProperties": True}
    if required:
        schema["required"] = required
    return schema


def _session_path_param() -> dict:
    return {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string"}}


def _scene_packet_query_params() -> list[dict]:
    return [{
        "name": "max_chars",
        "in": "query",
        "required": False,
        "schema": {"type": "integer", "default": DEFAULT_SCENE_PACKET_MAX_CHARS},
        "description": "Approximate compact packet budget. Default is safe for GPT Actions.",
    }]


def _scene_packet_response() -> dict:
    return {
        "description": "Compact Variant A ready scene packet",
        "content": {"application/json": {"schema": _object_schema({
            "session_id": {"type": "string"},
            "packet_version": {"type": "string"},
            "usage_note": {"type": "string"},
            "final_output_rule": {"type": "string"},
            "current_frame": _object_schema(),
            "scene_character_ids": {"type": "array", "items": {"type": "string"}},
            "required_files": {"type": "array", "items": {"type": "string"}},
            "file_manifest": {"type": "array", "items": _object_schema()},
            "missing_files": {"type": "array", "items": {"type": "string"}},
            "scene_context_digest": {"type": "string"},
            "focused_sources": {"type": "array", "items": _object_schema()},
            "source_budget": _object_schema(),
            "output_format_contract": _object_schema(),
            "save_contract": _object_schema(),
            "fallback_actions": _object_schema(),
        }, required=["session_id", "packet_version"])}}
    }


def _openapi_with_scene_packet() -> dict:
    schema = _ORIGINAL_OPENAPI()
    schema.setdefault("info", {})["version"] = app.version
    schema["servers"] = [{"url": base.BASE_URL}]
    schema.setdefault("paths", {})[SCENE_PACKET_PATH] = {
        "get": {
            "operationId": "getScenePacket",
            "summary": "Get compact ready scene packet for Custom GPT play mode",
            "description": "Fast compact path for gameplay. Smaller response to avoid ResponseTooLargeError.",
            "parameters": [_session_path_param()] + _scene_packet_query_params(),
            "responses": {"200": _scene_packet_response()},
        }
    }
    return schema


app.openapi_schema = None
app.openapi = _openapi_with_scene_packet  # type: ignore[method-assign]
