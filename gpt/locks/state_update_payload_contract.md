# Lock: state update payload contract

A gameplay scene is not saved state. After a meaningful scene, the apply-turn-result payload must include the exact sections needed for persistence.

## Required when changed
- relationship_changes: if personal dynamics changed.
- story_lines_changes: if events, lines, obligations, rumors, dated consequences, or future hooks changed.
- knowledge_changes: if a character learned, heard, saw, misunderstood, or confirmed something.
- current_state_changes: if location/time/active/nearby/speaking/observing/mentioned/looked_at changed.

If a scene had conflict, interest, jealousy, rejection, respect, rumor, social attention, injury, promise, debt, obligation, new knowledge, or changed location and the payload has no matching state section, the turn is technically unfinished.

## Relationship format
Use pair ids with canonical short ids when possible:
- akira__raiden
- akira__haru
- livia__raiden
- livia__haru
- akira__livia
- akira__kir
- raiden__haru

At minimum include one of: metric delta, status, notes, memory, open_threads, behavior_next, triggers, last_interaction.

Example:
```json
{
  "relationship_changes": [
    {
      "pair": "livia__raiden",
      "tension_delta": 2,
      "curiosity_delta": 1,
      "notes": ["Райден сухо отрезал флирт Ливии; Ливия скрыла задетость улыбкой."],
      "last_interaction": "1198-08-15 registration corridor: rejection/flirt boundary"
    }
  ]
}
```

## Story line format
Use stable line ids and absolute dates. Add event/source access if knowledge matters.

Example:
```json
{
  "story_lines_changes": {
    "active_lines": {
      "livia_raiden_interest": {
        "status": "open",
        "date_started": "1198-08-15",
        "characters": ["livia", "raiden"],
        "summary": "Ливия заинтересовалась Райденом, но его первая реакция была холодной."
      }
    },
    "shared_events": [
      {
        "event_id": "1198_08_15_livia_raiden_first_rejection",
        "date": "1198-08-15",
        "time": "late_morning",
        "location": "academy_registration_route",
        "participants": ["livia", "raiden", "akira", "haru"],
        "witnesses": ["akira", "haru"],
        "known_by": ["livia", "raiden", "akira", "haru"],
        "not_known_by": ["kir", "kiara", "kael_north"],
        "summary": "Ливия попыталась зацепить внимание Райдена; Райден резко удержал дистанцию."
      }
    ]
  }
}
```

## Final check
Before final gameplay answer, apply state changes. If apply-turn-result returns no_changes_detected after a meaningful scene, repair the payload and apply again once. Never claim state was saved if changed_files is empty.
