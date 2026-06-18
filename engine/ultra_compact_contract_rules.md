# Ultra Compact Contract Rules

## Why

Long sessions can make turn-contract responses too large for GPT Actions.

The API must return an ultra-compact scene_contract in play mode.

## Rule

`getSessionTurnContract` returns:

- current_frame/header_values;
- compact character_slice runtime summaries;
- compact relationship/knowledge/memory slices;
- compact event/energy slices;
- tiny gate contracts;
- source file list without file contents.

Full detailed files remain available in technical/audit mode.

## Never include in play response

- full behavior.md;
- full voice.md;
- full energy.yaml;
- full evidence logs;
- full relationship history;
- full open thread lists;
- full event queue;
- full contracts with long rule arrays.

## Character version drift

If any state field says Akira v2 is active, all Akira variant fields must be normalized to `version_2_poisonous`.

This prevents long-session drift where `pov_status_compact` says v2 but `character_status.char_akira` still says v1.
