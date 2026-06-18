"""Runtime state persistence patch v2."""
from __future__ import annotations
import json
from datetime import datetime
from typing import Any
import app.compact_context_patch as ccp
from app.compact_context_patch import app
from app import compact as base

APPLY_TURN_RESULT_PATH = ccp.APPLY_TURN_RESULT_PATH
LAST_APPLY_RESULT_FILE = "state/last_apply_result.json"
SCENE_HISTORY_FILE = "state/scene_history.json"
CALENDAR_RUNTIME_FILE = "state/calendar_runtime.json"
WORLD_INTEGRITY_STATE_FILE = "state/world_integrity_state.json"
REL_METRICS = list(getattr(base, "REL_METRICS", ["affection","trust","tension","jealousy","respect","curiosity","resentment"]))
ID_ALIASES = {"livia_cross":"livia","haru_foster":"haru","raiden_sterling":"raiden","kir_knox":"kir","kiara_volt":"kiara","kael":"kael_north","north":"kael_north"}


def canonical_id(v: Any) -> str:
    s = str(v or "").strip()
    return ID_ALIASES.get(s, s)


def find_section(payload, names):
    for n in names:
        if n in payload: return payload[n]
    data = payload.get("data")
    if isinstance(data, dict):
        for n in names:
            if n in data: return data[n]
    return None


def normalize_relationship_items(section):
    if not section: return []
    if isinstance(section, list): return [x for x in section if isinstance(x, dict)]
    if not isinstance(section, dict): return []
    if isinstance(section.get("pairs"), dict):
        return [{"pair_id": k, **v} for k, v in section["pairs"].items() if isinstance(v, dict)]
    for k in ["changes","items"]:
        if isinstance(section.get(k), list): return [x for x in section[k] if isinstance(x, dict)]
    if any(k in section for k in ["pair","pair_id","id"]): return [section]
    return [{"pair_id": k, **v} for k, v in section.items() if "__" in str(k) and isinstance(v, dict)]


def same_pair(a, b):
    ap = [canonical_id(x) for x in str(a).split("__") if x]
    bp = [canonical_id(x) for x in str(b).split("__") if x]
    return len(ap) == 2 and len(bp) == 2 and set(ap) == set(bp)


def resolve_pair(pairs, pair):
    if pair in pairs: return pair
    for existing in pairs:
        if same_pair(existing, pair): return existing
    parts = [canonical_id(x) for x in str(pair).split("__") if x]
    return "__".join(parts) if len(parts) == 2 else pair


def default_rel():
    if hasattr(base, "default_relationship"): return base.default_relationship()
    return {**{m:0 for m in REL_METRICS}, "status":"отношения появились после сцены", "notes":[], "memory":[], "open_threads":[], "behavior_next":[], "triggers":[], "last_interaction":None}


def merge_list(rel, field, value):
    if value is None: return False
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list): return False
    target = rel.setdefault(field, [])
    if not isinstance(target, list):
        target = []; rel[field] = target
    changed = False
    for item in items:
        if item and item not in target:
            target.append(item); changed = True
    return changed


def apply_relationship_changes_robust(session_id, payload, dry_run):
    items = normalize_relationship_items(find_section(payload, ["relationship_changes","relationships_changes","relationship_deltas","relationships"]))
    if not items: return False
    state = base.read_json("state/relationships.json", session_id, default={}) or {}
    pairs = state.setdefault("pairs", {})
    changed = False
    for item in items:
        pair = item.get("pair") or item.get("pair_id") or item.get("id")
        if isinstance(pair, list) and len(pair) == 2: pair = f"{pair[0]}__{pair[1]}"
        if not pair or "__" not in str(pair): continue
        rel = pairs.setdefault(resolve_pair(pairs, str(pair)), default_rel())
        deltas = item.get("deltas") if isinstance(item.get("deltas"), dict) else {}
        values = item.get("values") if isinstance(item.get("values"), dict) else {}
        for m in REL_METRICS:
            d = item.get(f"{m}_delta", deltas.get(m, deltas.get(f"{m}_delta")))
            if d is not None:
                rel[m] = max(0, min(100, int(rel.get(m,0)) + int(d or 0))); changed = True
            elif isinstance(item.get(m, values.get(m)), int):
                rel[m] = max(0, min(100, int(item.get(m, values.get(m))))); changed = True
        if isinstance(item.get("status"), str): rel["status"] = item["status"]; changed = True
        for field in ["notes","memory","open_threads","behavior_next","triggers"]:
            if merge_list(rel, field, item.get(field) or item.get(f"add_{field}") or (item.get("note") if field=="notes" else None)): changed = True
        if item.get("last_interaction") is not None: rel["last_interaction"] = item.get("last_interaction"); changed = True
    if changed and not dry_run: base.write_json("state/relationships.json", state, session_id)
    return changed


def apply_json_section_robust(session_id, payload, path, names, dry_run):
    section = find_section(payload, names)
    if not isinstance(section, dict) or not section: return False
    state = base.read_json(path, session_id, default={}) or {}
    old = json.dumps(state, ensure_ascii=False, sort_keys=True)
    new = base.deep_merge(state, section)
    if json.dumps(new, ensure_ascii=False, sort_keys=True) != old:
        if not dry_run: base.write_json(path, new, session_id)
        return True
    return False


def extract_scene_text(request, payload):
    data = payload.get("data")
    values = [request.visible_scene_text, payload.get("visible_scene_text"), payload.get("final_scene_text"), payload.get("scene_text")]
    if isinstance(data, dict): values += [data.get("visible_scene_text"), data.get("final_scene_text"), data.get("scene_text")]
    for v in values:
        if isinstance(v, str) and v.strip(): return v.strip()
    return ""


def entries_root(history):
    if isinstance(history, list): return history, history
    if not isinstance(history, dict): history = {"schema":"scene_history_v2", "entries":[]}
    entries = history.setdefault("entries", [])
    if not isinstance(entries, list): entries = []; history["entries"] = entries
    return history, entries


def append_scene_history(session_id, payload, scene_text, changed_files, dry_run):
    if dry_run or not scene_text: return False
    current = base.read_json("state/current_state.json", session_id, default={}) or {}
    story = base.read_json("state/story_lines.json", session_id, default={}) or {}
    counter = story.get("turn_counter", {}) if isinstance(story, dict) else {}
    turn = next((int(counter.get(k) or 0) for k in ["game_turn_number","total_game_turns","game_turn","turn_number","scene_count"] if str(counter.get(k) or "").isdigit()), 0) if isinstance(counter, dict) else 0
    entry = {"id":f"scene_{turn or 'unknown'}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}","kind":"gameplay","is_gameplay":True,"turn_number":turn or None,"created_at":datetime.utcnow().isoformat(),"current_date":current.get("current_date"),"current_time":current.get("current_time"),"location_id":current.get("current_location_id"),"location_text":current.get("current_location_text"),"active_characters":current.get("active_characters",[]),"nearby_characters":current.get("nearby_characters",[]),"player_input":current.get("last_player_input") or payload.get("player_input") or "","visible_scene_text":scene_text,"scene_text":scene_text,"changed_files_snapshot":list(changed_files)}
    root, entries = entries_root(base.read_json(SCENE_HISTORY_FILE, session_id, default={"schema":"scene_history_v2","entries":[]}))
    if entries and isinstance(entries[-1], dict) and entries[-1].get("visible_scene_text") == scene_text: return False
    entries.append(entry)
    if isinstance(root, dict):
        root["schema"] = root.get("schema") or "scene_history_v2"; root["total_entries"] = len(entries); root["last_updated_at"] = datetime.utcnow().isoformat()
    base.write_json(SCENE_HISTORY_FILE, root, session_id)
    return True


def write_world_integrity_state(session_id, changed_files):
    root, entries = entries_root(base.read_json(SCENE_HISTORY_FILE, session_id, default={}))
    state = base.read_json(WORLD_INTEGRITY_STATE_FILE, session_id, default={}) or {}
    check = {"checked_at":datetime.utcnow().isoformat(),"scene_history_entries":len(entries),"changed_files_snapshot":list(changed_files),"issues":[],"status":"ok"}
    checks = state.setdefault("checks", [])
    if not isinstance(checks, list): checks = []
    checks.append(check); state["checks"] = checks[-50:]; state["last_check"] = check; state["open_issues"] = []; state["rule"] = "Diagnostics only."
    base.write_json(WORLD_INTEGRITY_STATE_FILE, state, session_id)
    return True


def section_summary(payload):
    return {name: bool(find_section(payload, names)) for name, names in {
        "relationship_changes":["relationship_changes","relationships_changes","relationship_deltas","relationships"],
        "story_lines_changes":["story_lines_changes","story_line_changes","story_lines","story_lines_state"],
        "knowledge_changes":["knowledge_changes","knowledge_state_changes","knowledge_state"],
        "current_state_changes":["current_state_changes","current_state","state_changes"],
        "reputation_changes":["reputation_changes","reputation_state_changes","reputation_state"],
        "rumors_changes":["rumor_changes","rumors_changes","rumors_state_changes","rumors_state"],
        "inventory_changes":["inventory_changes","inventory_state_changes","inventory_state"],
        "future_locks_changes":["future_locks_changes","future_locks_progress_changes","future_locks_progress"],
        "calendar_runtime_changes":["calendar_runtime_changes","calendar_runtime","calendar_changes"],
    }.items()}


def remove_route(path, method="POST"):
    app.router.routes = [r for r in app.router.routes if not (getattr(r, "path", None) == path and method in (getattr(r, "methods", set()) or set()))]


base.apply_relationship_changes = apply_relationship_changes_robust
remove_route(APPLY_TURN_RESULT_PATH, "POST")


@app.post(APPLY_TURN_RESULT_PATH, response_model=ccp.ApplyTurnResultWithVisibleSceneResponse, operation_id="applyTurnResult")
def apply_turn_result_persistent(session_id: str, request: ccp.ApplyTurnResultWithVisibleSceneRequest = ccp.ApplyTurnResultWithVisibleSceneRequest()):
    sid = base.safe_session_id(session_id); base.ensure_session(sid)
    source, payload = base.read_turn_payload(sid, request)
    changed = []
    if apply_relationship_changes_robust(sid, payload, request.dry_run): changed.append("state/relationships.json")
    for path, names in list(base.STATE_SECTION_MAP) + [(CALENDAR_RUNTIME_FILE, ["calendar_runtime_changes","calendar_runtime","calendar_changes"])]:
        if apply_json_section_robust(sid, payload, path, names, request.dry_run): changed.append(path)
    scene_text = extract_scene_text(request, payload)
    if append_scene_history(sid, payload, scene_text, changed, request.dry_run): changed.append(SCENE_HISTORY_FILE)
    if not request.dry_run and write_world_integrity_state(sid, changed): changed.append(WORLD_INTEGRITY_STATE_FILE)
    sections = section_summary(payload)
    last = {"status":"applied" if changed else "no_changes_detected","session_id":sid,"source":source,"dry_run":request.dry_run,"changed_files":changed,"payload_sections_present":sections,"scene_history_written":SCENE_HISTORY_FILE in changed,"relationship_state_written":"state/relationships.json" in changed,"world_integrity_written":WORLD_INTEGRITY_STATE_FILE in changed}
    if not request.dry_run:
        base.write_json(LAST_APPLY_RESULT_FILE, last, sid)
        if LAST_APPLY_RESULT_FILE not in changed: changed.append(LAST_APPLY_RESULT_FILE)
    return ccp.ApplyTurnResultWithVisibleSceneResponse(status="applied" if changed else "no_changes_detected", session_id=sid, source=source, dry_run=request.dry_run, changed_files=changed, visible_scene_text=scene_text or request.visible_scene_text, final_scene_text=scene_text or request.visible_scene_text, render_packet_received=isinstance(request.render_packet, dict))

app.version = "0.3.47-state-persistence-v2"
