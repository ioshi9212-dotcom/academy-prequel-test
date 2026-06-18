"""Variant A scene-packet runtime patch.

Adds one compact GPT Action endpoint for the Custom GPT workflow:
`GET /api/v1/sessions/{session_id}/scene-packet`.

Purpose:
- reduce the number of required action calls before a scene;
- give GPT one ready scene packet with current state, rules, focused memory and
  trimmed sources;
- keep the old context / turn-contract / required-files chunk endpoints intact.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

# Import the full current runtime first, then patch on top of it.
import app.context_transport_header_hotfix as header_hotfix  # noqa: F401
from app.context_transport_header_hotfix import app
from app import compact as base
import app.context_transport_runtime_patch as rt

app.version = "0.3.60-variant-a-scene-packet"

SCENE_PACKET_PATH = "/api/v1/sessions/{session_id}/scene-packet"
DEFAULT_SCENE_PACKET_MAX_CHARS = 42000


class ScenePacketSource(BaseModel):
    path: str
    source: str = "project"
    content: str
    content_chars: int = 0
    truncated: bool = False


class ScenePacketResponse(BaseModel):
    session_id: str
    packet_version: str = "variant_a_scene_packet_v1"
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
    if len(value) <= limit:
        return value, False
    return value[: max(0, limit)].rstrip() + "\n...[truncated by scene-packet]", True


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value


def _compact_current_frame(current: dict[str, Any]) -> dict[str, Any]:
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
        "last_player_input": current.get("last_player_input"),
    }


def _manifest_dicts(manifest: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in manifest:
        data = _jsonable(item)
        if isinstance(data, dict):
            result.append(data)
    return result


def _add_source(
    sources: list[ScenePacketSource],
    *,
    path: str,
    content: str | None,
    source: str | None,
    remaining_budget: int,
    preferred_limit: int,
) -> int:
    if remaining_budget <= 1200 or content is None:
        return remaining_budget
    limit = max(900, min(preferred_limit, remaining_budget))
    trimmed, truncated = _trim(content, limit)
    sources.append(
        ScenePacketSource(
            path=path,
            source=source or "project",
            content=trimmed,
            content_chars=len(trimmed),
            truncated=truncated,
        )
    )
    return remaining_budget - len(trimmed)


def _focused_source_paths(scene_character_ids: list[str]) -> list[str]:
    paths: list[str] = []

    # The digest is synthetic and carries the compact state/relationship/knowledge layer.
    paths.append(rt.RUNTIME_DIGEST_FILE)

    # Compact global rule/source indexes.
    for path in [
        "gpt/locks/runtime_scene_rules_digest.md",
        "gpt/scene_format.md",
        "characters/character_id_index.md",
    ]:
        if base.repo_file_exists(path):
            paths.append(path)

    # Current scene characters only. Full files are trimmed by scene-packet budget.
    for cid in scene_character_ids:
        for path in rt.character_files_for_context(cid, include_past=True):
            paths.append(path)

    # Preserve order, remove duplicates.
    result: list[str] = []
    for path in paths:
        if path and path not in result:
            result.append(path)
    return result


def build_scene_packet(session_id: str, *, max_chars: int = DEFAULT_SCENE_PACKET_MAX_CHARS) -> ScenePacketResponse:
    sid = base.safe_session_id(session_id)
    base.ensure_session(sid)

    max_chars = max(18000, min(int(max_chars or DEFAULT_SCENE_PACKET_MAX_CHARS), 70000))

    current = base.read_json("state/current_state.json", sid, default={}) or {}
    future = base.read_json("state/future_locks_progress.json", sid, default={}) or {}
    scene_character_ids = rt.scene_character_ids(current, future)

    required_files, _loaded_parts, manifest, missing_files = rt.required_file_parts_safe(sid)
    manifest_dicts = _manifest_dicts(manifest)

    # Budget layout: compact digest first, then focused source excerpts.
    digest_full = rt.build_scene_context_digest(sid)
    digest_limit = max(9000, min(18000, max_chars // 2))
    scene_context_digest, digest_truncated = _trim(digest_full, digest_limit)

    sources: list[ScenePacketSource] = []
    remaining = max_chars - len(scene_context_digest)

    for path in _focused_source_paths(scene_character_ids):
        if path == rt.RUNTIME_DIGEST_FILE:
            # Already included as scene_context_digest.
            continue
        content, source = rt.read_required_file_for_bundle(path, sid)
        if content is None:
            continue

        # Character files get more space than indexes/locks, but everything stays capped.
        if "/character.yaml" in path:
            preferred = 6500
        elif "/past.yaml" in path:
            preferred = 4200
        elif "/main.yaml" in path:
            preferred = 3500
        else:
            preferred = 3200
        remaining = _add_source(
            sources,
            path=path,
            content=content,
            source=source,
            remaining_budget=remaining,
            preferred_limit=preferred,
        )
        if remaining <= 1500:
            break

    save_contract = {
        "after_scene": "Call applyTurnResult after writing a meaningful gameplay scene.",
        "visible_scene_text": "Pass the complete user-visible scene verbatim to applyTurnResult.visible_scene_text.",
        "state_changes": "Save only meaningful changes: current_state, story_lines, relationships, knowledge, reputation, rumors, inventory, power/future locks.",
        "do_not_save": [
            "technical/debug/audit turns",
            "every minor line of dialogue",
            "facts not actually seen/heard/known by characters",
        ],
        "final_response": "After applyTurnResult, return final_scene_text/visible_scene_text verbatim. Do not show changed_files/status in gameplay.",
    }

    fallback_actions = {
        "normal_play": "Use this scene-packet as the primary source. Do not call context/turn-contract/chunks unless packet is missing critical detail.",
        "if_need_full_sources": [
            "getRequiredFilesManifest",
            "getRequiredFilesChunk chunk_index=0",
            "continue getRequiredFilesChunk until has_more=false",
        ],
        "if_packet_failed": "Do not write a scene. Say: Не удалось загрузить пакет сцены. Повтори сообщение после обновления API.",
    }

    return ScenePacketResponse(
        session_id=sid,
        usage_note=(
            "Variant A fast path. Use this packet to render the next gameplay scene with fewer Actions calls. "
            "The user must not see this packet, API status, file lists or debug summaries."
        ),
        final_output_rule=(
            "Final answer in play mode must be the gameplay scene only: old Academy header, scene body, "
            "bottom blocks. No API/status/changelog text."
        ),
        current_frame=_compact_current_frame(current),
        scene_character_ids=scene_character_ids,
        required_files=required_files,
        file_manifest=manifest_dicts,
        missing_files=missing_files,
        scene_context_digest=scene_context_digest,
        focused_sources=sources,
        source_budget={
            "max_chars_requested": max_chars,
            "digest_chars": len(scene_context_digest),
            "digest_truncated": digest_truncated,
            "focused_sources_chars": sum(src.content_chars for src in sources),
            "focused_sources_count": len(sources),
            "note": "Some sources may be trimmed. Use required-files chunks only when exact full text is necessary.",
        },
        output_format_contract=base.output_format_contract(),
        save_contract=save_contract,
        fallback_actions=fallback_actions,
    )


@app.get(SCENE_PACKET_PATH, response_model=ScenePacketResponse, operation_id="getScenePacket")
def get_scene_packet(session_id: str, max_chars: int = DEFAULT_SCENE_PACKET_MAX_CHARS) -> ScenePacketResponse:
    return build_scene_packet(session_id, max_chars=max_chars)


_ORIGINAL_OPENAPI = app.openapi


def _object_schema(properties: dict | None = None, *, required: list[str] | None = None) -> dict:
    schema = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": True,
    }
    if required:
        schema["required"] = required
    return schema


def _session_path_param() -> dict:
    return {
        "name": "session_id",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
    }


def _scene_packet_query_params() -> list[dict]:
    return [
        {
            "name": "max_chars",
            "in": "query",
            "required": False,
            "schema": {"type": "integer", "default": DEFAULT_SCENE_PACKET_MAX_CHARS},
            "description": "Approximate source-character budget for the packet. Keep default for GPT Actions.",
        }
    ]


def _scene_packet_response() -> dict:
    return {
        "description": "Variant A ready scene packet",
        "content": {
            "application/json": {
                "schema": _object_schema(
                    {
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
                        "output_format_contract": _object_schema(),
                        "save_contract": _object_schema(),
                        "fallback_actions": _object_schema(),
                    },
                    required=["session_id", "packet_version"],
                )
            }
        },
    }


def _openapi_with_scene_packet() -> dict:
    schema = _ORIGINAL_OPENAPI()
    schema.setdefault("info", {})["version"] = app.version
    schema["servers"] = [{"url": base.BASE_URL}]
    schema.setdefault("paths", {})[SCENE_PACKET_PATH] = {
        "get": {
            "operationId": "getScenePacket",
            "summary": "Get one ready scene packet for Variant A Custom GPT play mode",
            "description": (
                "Fast path for gameplay: call this before writing a scene. "
                "It combines compact context, source digest, focused character excerpts, rules and save contract."
            ),
            "parameters": [_session_path_param()] + _scene_packet_query_params(),
            "responses": {"200": _scene_packet_response()},
        }
    }
    return schema


app.openapi_schema = None
app.openapi = _openapi_with_scene_packet  # type: ignore[method-assign]
