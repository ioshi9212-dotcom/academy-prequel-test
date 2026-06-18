"""Runtime header/footer hotfix v22.

Keeps runtime simple, serves a minimal GPT-compatible OpenAPI schema,
enables living NPC memory, and enables explicit non-Akira POV mode only when
latest input contains `POV:` / `пов:` with a non-Akira target.
"""
from __future__ import annotations

try:
    import app.calendar_context_runtime_patch as calendar_patch  # noqa: F401
except Exception:
    calendar_patch = None
try:
    import app.lore_context_runtime_patch as lore_patch  # noqa: F401
except Exception:
    lore_patch = None
try:
    import app.context_cleanup_runtime_patch as cleanup_patch  # noqa: F401
except Exception:
    cleanup_patch = None

import app.runtime_speed_patch as speed_patch  # noqa: F401
import app.context_transport_runtime_patch as rt
from app.runtime_speed_patch import app
from app import compact as base

rt.MINIMAL_LOCK_FILES = ["gpt/locks/runtime_scene_rules_digest.md"]

try:
    import app.scene_output_format_runtime_patch as scene_format_patch  # noqa: F401
except Exception:
    scene_format_patch = None
try:
    import app.npc_living_runtime_patch as npc_living_patch  # noqa: F401
except Exception:
    npc_living_patch = None
try:
    import app.pov_switch_runtime_patch as pov_switch_patch  # noqa: F401
except Exception:
    pov_switch_patch = None

app.version = "0.3.51-living-npc-pov-enabled"

rt.MEDIUM_STYLE_FORMAT_DIGEST = """
## Medium scene style digest — strict Academy scene format
Use old Academy header/footer. Energy should be visually/physically felt when relevant: cold, heat, sound, vibration, pressure, metal tremor, trajectory shift. Personal energy is in character cards, not in separate per-type files.
"""


def _object_schema(properties: dict | None = None, *, required: list[str] | None = None) -> dict:
    schema = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": True,
    }
    if required:
        schema["required"] = required
    return schema


def _response_schema(kind: str) -> dict:
    if kind == "health":
        return _object_schema(
            {
                "status": {"type": "string"},
                "app": {"type": "string"},
                "version": {"type": "string"},
                "public_base_url": {"type": "string"},
            }
        )
    if kind == "session":
        return _object_schema(
            {
                "session_id": {"type": "string"},
                "title": {"type": "string"},
                "created_at": {"type": "string"},
                "updated_at": {"type": "string"},
            },
            required=["session_id"],
        )
    if kind == "context":
        return _object_schema(
            {
                "session_id": {"type": "string"},
                "current_state": _object_schema(),
                "story_lines": _object_schema(),
                "relationships": _object_schema(),
                "knowledge_state": _object_schema(),
                "recommended_files": {"type": "array", "items": {"type": "string"}},
            }
        )
    if kind == "turn_contract":
        return _object_schema(
            {
                "session_id": {"type": "string"},
                "active_character_ids": {"type": "array", "items": {"type": "string"}},
                "nearby_character_ids": {"type": "array", "items": {"type": "string"}},
                "required_files": {"type": "array", "items": {"type": "string"}},
                "output_format_contract": _object_schema(),
                "prompt_preview": {"type": "string"},
            }
        )
    if kind == "manifest":
        return _object_schema(
            {
                "session_id": {"type": "string"},
                "required_files": {"type": "array", "items": {"type": "string"}},
                "files": {"type": "array", "items": _object_schema()},
                "missing_files": {"type": "array", "items": {"type": "string"}},
                "chunks_total": {"type": "integer"},
                "loaded_count": {"type": "integer"},
                "missing_count": {"type": "integer"},
            }
        )
    if kind == "chunk":
        return _object_schema(
            {
                "session_id": {"type": "string"},
                "chunk_index": {"type": "integer"},
                "chunks_total": {"type": "integer"},
                "has_more": {"type": "boolean"},
                "next_chunk_index": {"type": "integer"},
                "loaded_files": {"type": "array", "items": _object_schema()},
                "missing_files": {"type": "array", "items": {"type": "string"}},
            }
        )
    if kind == "apply":
        return _object_schema(
            {
                "status": {"type": "string"},
                "session_id": {"type": "string"},
                "changed_files": {"type": "array", "items": {"type": "string"}},
                "visible_scene_text": {"type": "string"},
                "final_scene_text": {"type": "string"},
            }
        )
    return _object_schema()


def _response(description: str, kind: str) -> dict:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": _response_schema(kind),
            }
        },
    }


def _session_path_param() -> dict:
    return {
        "name": "session_id",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
    }


def _chunk_query_params() -> list[dict]:
    return [
        {
            "name": "chunk_index",
            "in": "query",
            "required": False,
            "schema": {"type": "integer", "default": 0},
        },
        {
            "name": "max_chars",
            "in": "query",
            "required": False,
            "schema": {"type": "integer", "default": 30000},
        },
        {
            "name": "max_items",
            "in": "query",
            "required": False,
            "schema": {"type": "integer", "default": 3},
        },
    ]


def _minimal_gpt_openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Akira Academy Prequel Actions",
            "version": app.version,
        },
        "servers": [{"url": base.BASE_URL}],
        "paths": {
            "/health": {
                "get": {
                    "operationId": "health",
                    "summary": "Check API health and runtime version",
                    "responses": {"200": _response("API health status", "health")},
                }
            },
            "/api/v1/sessions": {
                "post": {
                    "operationId": "createSession",
                    "summary": "Create a new gameplay session",
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": _object_schema(
                                    {
                                        "session_id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "reset": {"type": "boolean"},
                                    }
                                )
                            }
                        },
                    },
                    "responses": {"200": _response("Created session", "session")},
                }
            },
            "/api/v1/sessions/{session_id}/context": {
                "get": {
                    "operationId": "getSessionContext",
                    "summary": "Get compact context for a session",
                    "parameters": [_session_path_param()],
                    "responses": {"200": _response("Compact session context", "context")},
                }
            },
            "/api/v1/sessions/{session_id}/turn-contract": {
                "get": {
                    "operationId": "getSessionTurnContract",
                    "summary": "Get turn contract, required files and output rules",
                    "parameters": [_session_path_param()],
                    "responses": {"200": _response("Turn contract", "turn_contract")},
                }
            },
            "/api/v1/sessions/{session_id}/required-files-manifest": {
                "get": {
                    "operationId": "getRequiredFilesManifest",
                    "summary": "Get required files manifest and chunk count",
                    "parameters": [_session_path_param()],
                    "responses": {"200": _response("Required files manifest", "manifest")},
                }
            },
            "/api/v1/sessions/{session_id}/required-files-chunk": {
                "get": {
                    "operationId": "getRequiredFilesChunk",
                    "summary": "Get one chunk of required file contents",
                    "parameters": [_session_path_param()] + _chunk_query_params(),
                    "responses": {"200": _response("Required files chunk", "chunk")},
                }
            },
            "/api/v1/sessions/{session_id}/required-files-bundle": {
                "get": {
                    "operationId": "getRequiredFilesBundle",
                    "summary": "Backward-compatible required files chunk endpoint",
                    "parameters": [_session_path_param()] + _chunk_query_params(),
                    "responses": {"200": _response("Required files chunk", "chunk")},
                }
            },
            "/api/v1/sessions/{session_id}/apply-turn-result": {
                "post": {
                    "operationId": "applyTurnResult",
                    "summary": "Apply meaningful scene changes to session state",
                    "parameters": [_session_path_param()],
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": _object_schema(
                                    {
                                        "turn_file": {"type": "string"},
                                        "data": _object_schema(),
                                        "dry_run": {"type": "boolean", "default": False},
                                        "visible_scene_text": {"type": "string"},
                                    }
                                )
                            }
                        },
                    },
                    "responses": {"200": _response("Apply result", "apply")},
                }
            },
        },
    }


def _stable_openapi() -> dict:
    return _minimal_gpt_openapi()


app.openapi_schema = None
app.openapi = _stable_openapi  # type: ignore[method-assign]
