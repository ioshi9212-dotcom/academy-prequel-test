# Lore Usage Lock

Use `canon_lore/` as the active lore source.

Old `canon/` files may exist in the repository, but after the new lore module is connected they are not the primary lore source unless explicitly loaded.

## Required behavior

- Always keep `canon_lore/core/world_background.yaml` as background.
- Always keep `canon_lore/academy/academy_background.yaml` as Academy background.
- Always keep `canon_lore/hidden/hidden_lore_policy.yaml` as hidden-lore policy.
- If a scene mentions Echo, Kairos, energy, second world, continents, Academy rules, uniform, training, ratings, locations or hidden lore, use matching tagged lore files.
- If Akira and Raiden are both in the scene, always use `canon_lore/hidden/raiden_akira_bond.yaml`.
- Hidden lore is author/engine knowledge, not automatic NPC knowledge.
- Character behavior still comes from character cards first.

## Do not

- Do not dump lore as an exposition lecture.
- Do not confuse hidden author lore with character knowledge.
- Do not let old `canon/august_15_calendar.yaml` override the new calendar or state.
- Do not use old canon files as active source unless required_files explicitly contains them.
