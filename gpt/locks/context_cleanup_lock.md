# Context Cleanup Lock

Active sources after cleanup:

- Character behavior: `characters/{id}/character.yaml`, then `characters/{id}/past.yaml`, then `characters/{id}/main.yaml` if present.
- Character ID mapping: `characters/character_id_index.md`.
- Calendar: `calendar/calendar_index.yaml` + current day file + `state/calendar_runtime.json`.
- Lore: `canon_lore/`.
- State: `state/` files only for live save/progress.

Old `canon/`, old `characters/main/*.md`, old `state/academy_schedule.json`, old `app/selective_context_patch.py`, and old `app/session_routes.py` must not override the active runtime.
