# NPC Living Scene Rules

Short rule file for invented Academy NPCs who are not part of the fixed character roster yet.

## Purpose

The Academy is inhabited. Invented NPCs may appear to make public spaces feel alive, create social pressure, provide witnesses, and open small future hooks.

Do not replace main/supporting characters with random NPCs when an existing character should logically carry the scene.

## NPC types

### 1. Background NPCs

Use as atmosphere only:
- students passing by;
- staff at desks, doors, medical, canteen, dorm blocks;
- someone reacting to energy, reputation, noise, clothing, ranking, rumor;
- small groups whispering, laughing, avoiding, watching.

Rules:
- no full name unless needed;
- no private arc;
- no repeated importance unless saved;
- no scene takeover;
- not every scene needs background NPCs.

### 2. Emerging / important NPCs

Use when the NPC can affect story:
- repeats across scenes;
- has a name, role, goal, conflict, promise, threat, useful information, debt, rivalry, crush, grudge, duty, rumor-source, or future hook;
- changes relationship/reputation/knowledge/calendar/story direction;
- becomes a witness or source that matters later.

If an NPC becomes important, save them into `state/session_npcs.json` through apply-turn-result.

## Academy NPC behavior

Academy NPCs are not convenient props.

They are students/staff in a status-heavy, competitive academy. Many are strong, ambitious, proud, jealous, curious, bored, arrogant, insecure, or socially strategic.

Do not make all NPCs react the same way to Akira.

Akira's sharp look or cold tone may affect one person, but it should not make the whole room go silent, afraid, obedient, or respectful.

Use varied reactions:
- one student backs off;
- another laughs or mocks;
- another pushes harder;
- another tries to provoke;
- another watches for gossip;
- another envies attention from Haru/Raiden/Kir;
- another makes a wrong assumption;
- another ignores Akira because they have their own status.

NPCs can be brave, stupid, proud, petty, flirty, ambitious, jealous, or reckless. Do not make them too helpful unless their role/reason supports it.

## Rumors and social media

Use rumors/social media as believable background pressure or consequence, not as a constant main plot.

They should be mixed:
- neutral observations;
- jokes;
- envy;
- wrong guesses;
- private chat fragments;
- admiration;
- mockery;
- exaggeration;
- status games;
- fear or caution only when justified.

Do not make all rumors kind, all rumors hostile, or all students synchronized into one opinion.

If NPCs do not know a fact, rumors must be guesses, questions, visible reactions, or distortions — not hidden truth.

## Save criteria

Save an NPC only if at least one is true:
- named or clearly identifiable;
- likely to recur;
- created a conflict/hook;
- witnessed something important;
- knows or spreads a meaningful rumor;
- has a goal/arc that may continue;
- affected Akira/Livia/Raiden/Haru/Kir or reputation.

Do not save disposable background reactions.

## Session NPC memory

Use `state/session_npcs.json` for invented NPCs that are not in `characters/` yet.

Suggested payload key:

```json
{
  "session_npcs_changes": {
    "important_npcs": {
      "npc_id": {
        "name": "visible or given name",
        "role": "student/staff/etc",
        "status": "background|emerging|important",
        "first_seen": "date/time/location",
        "appearance": "short visible description",
        "personality": "short behavior pattern",
        "goal": "what they want",
        "arc_hook": "why they may return",
        "knowledge": ["what they know and source"],
        "relationships": {"akira": "short dynamic"},
        "last_seen": "date/time/location",
        "notes": ["only meaningful notes"]
      }
    },
    "open_npc_threads": [
      {
        "npc_id": "npc_id",
        "status": "open|due|closed",
        "hook": "what can return later",
        "conditions": ["when it can reappear"]
      }
    ]
  }
}
```

## Boundaries

- Do not create a new important NPC when an existing main/supporting character should logically carry the scene.
- Do not make every random student secretly important.
- Do not give NPCs hidden knowledge without a source.
- If unsure, keep them background and do not save.
