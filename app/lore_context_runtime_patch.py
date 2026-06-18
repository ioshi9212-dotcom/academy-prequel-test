"""Lore context runtime patch v18: character-card energy blocks, no per-type files."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import app.context_transport_runtime_patch as rt
from app.context_transport_runtime_patch import app
from app import compact as base
import app.compact_context_patch as ccp
app.version = "0.3.40-character-card-energy-blocks-v18"
LORE_INDEX_FILE="canon_lore/index.yaml"
LORE_ALWAYS_FILES=["canon_lore/core/world_background.yaml","canon_lore/academy/academy_background.yaml","canon_lore/hidden/hidden_lore_policy.yaml"]
ENERGY_IDS={"akira","livia","haru","raiden","kir","kiara"}
HIDDEN_AKIRA_RAIDEN_FILE="canon_lore/hidden/raiden_akira_bond.yaml"
LORE_USAGE_LOCK="gpt/locks/lore_usage_lock.md"
_ORIG=rt.build_scene_context_digest

def _unique(xs):
    r=[]
    for x in xs:
        if x and x not in r: r.append(x)
    return r

def _read(path, session_id=None):
    try: return base.read_text(path, session_id=session_id)
    except Exception: return ""

def _cut(t, n=7000):
    t=str(t or "").strip(); return t if len(t)<=n else t[:n].rstrip()+"\n...<truncated>"

def _scene_text(current, story=None):
    parts=[]
    for k in ["current_location_id","current_location_text","current_scene_goal","last_player_input"]:
        if current.get(k): parts.append(str(current.get(k)))
    for f in ["active_characters","nearby_characters","mentioned_character_ids","scheduled_character_ids"]:
        vals=current.get(f,[])
        if isinstance(vals,list): parts += [str(v) for v in vals if v]
    if story:
        try: parts.append(json.dumps(story, ensure_ascii=False))
        except Exception: parts.append(str(story))
    return "\n".join(parts).lower()

def lore_files_for_context(current:dict[str,Any], scene_character_ids:list[str], story_lines:Any=None)->list[str]:
    text=_scene_text(current,story_lines)
    files=[LORE_INDEX_FILE]+LORE_ALWAYS_FILES
    if any(k in text for k in ["энерг","фонит","фонят","перегруз","выброс","датчик","пространств","резонанс","огонь","тепло","холод","воздух","магнит","иней","вибрация"]): files.append("canon_lore/world/energy_system.yaml")
    if any(k in text for k in ["нпс","слух","провокац","флирт","ревност","мини-ар","статус","фоновые"]): files.append("canon_lore/academy/academy_npc_social_rules.yaml")
    ids={rt.canonical_id(x) for x in scene_character_ids}
    if ids & ENERGY_IDS: files.append("canon_lore/world/energy_system.yaml")
    if {"akira","raiden"} <= ids: files.append(HIDDEN_AKIRA_RAIDEN_FILE)
    return [p for p in _unique(files) if base.repo_file_exists(p)]

def build_lore_slice(session_id,current,scene_character_ids,story_lines=None):
    files=lore_files_for_context(current,scene_character_ids,story_lines)
    return {"lore_mode":"canon_lore_v4_character_energy_blocks","energy_policy":"No separate per-type energy files. Personal energy is in character cards.","loaded_lore_files":files,"files":[{"path":p,"content":_cut(_read(p,session_id),9000 if p.endswith("energy_system.yaml") else 7000)} for p in files]}

def build_scene_context_digest_with_lore(session_id):
    base_digest=_ORIG(session_id)
    current=base.read_json("state/current_state.json",session_id,default={}) or {}
    future=base.read_json("state/future_locks_progress.json",session_id,default={}) or {}
    chars=rt.scene_character_ids(current,future)
    story=base.read_json("state/story_lines.json",session_id,default={}) or {}
    return base_digest+"\n"+rt._json_block("Lore slice", build_lore_slice(session_id,current,chars,story), 22000)+"\n## Lore reminder\nEnergy is in active character cards. Write it as felt prose: cold, heat, vibration, pressure, sound, trajectory, metal tremor. No separate per-type files; no dry physics.\n"
rt.build_lore_slice=build_lore_slice
rt.lore_files_for_context=lore_files_for_context
rt.build_scene_context_digest=build_scene_context_digest_with_lore
if LORE_USAGE_LOCK not in rt.MINIMAL_LOCK_FILES: rt.MINIMAL_LOCK_FILES.append(LORE_USAGE_LOCK)
ccp._read_required_file_for_bundle=rt.read_required_file_for_bundle
rt.app.version=app.version
