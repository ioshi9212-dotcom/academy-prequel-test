# Selective Context Runtime Lock

Normal gameplay must use selective context, not full project bundle.

Rules:
- Load runtime/scene_context_digest.md.
- Load full character.yaml/past.yaml only for active, nearby, mentioned, scheduled, addressed, looked_at scene characters.
- Do not load full state/*.json files in normal gameplay; use digest slices.
- Relationships must include only pairs where both characters are in current scene focus, unless a third character is explicitly mentioned or scheduled.
- Roster fields in current_state are replacement lists, not append-only memory.
- If a character has not appeared, is not nearby, not mentioned, and not scheduled, do not keep them active by inertia.
- Use repairSceneRoster if active_character_ids are polluted by stale scene characters.
- Chunk transport must stay safe: do not request huge max_chars/max_items values that can trigger ResponseTooLargeError.


## Medium quality mode

Do not make scene output look like a technical form.
The runtime digest contains medium style/canon/source/relationship slices.
Use them to preserve prose quality without loading full heavy files every turn.

Expected behavior:
- slower than ultra-fast, faster than full 50+ chunk bundle;
- character files for scene characters remain authoritative;
- runtime digest carries enough style/canon/state rules for normal gameplay.
