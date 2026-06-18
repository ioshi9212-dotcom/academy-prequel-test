# Runtime Scene Rules Digest

This single compact lock replaces the normal stack of old gameplay locks in required_files.

## Source priority

1. User's latest direct instruction.
2. Latest visible scene facts from scene_history / recent played messages.
3. API/session current_state.
4. turn-contract and required_files chunks.
5. Character YAML files for active scene characters.
6. relationships / knowledge_state / inventory / story_lines / calendar_runtime.
7. calendar/ current day hooks.
8. canon_lore/ background and hidden policy.
9. Chat memory only as visible gameplay scene text or the user's latest action, not as loose source of truth.

## Required loading

- In gameplay mode, use getSessionTurnContract first.
- Then call getRequiredFilesManifest.
- Then call getRequiredFilesChunk from chunk_index=0 until has_more=false.
- Use all loaded chunks before writing the scene.
- Do not write gameplay from memory only.
- Before writing the next scene, read and respect the last visible scene facts available in scene_history / runtime digest / recent played messages.

## Immediate continuity

- The last visible scene is binding for physical continuity unless the player explicitly changes it.
- Track concrete object positions and holders: ball, tray, cup, phone, documents, bag, door, chair, food, clothes, weapons, cards.
- If the last scene says Haru caught the ball and it is in his hands, the ball must stay in Haru's hands until a visible action moves it.
- Do not resurrect an object near Akira just because an old option, old setup, or previous state mentioned it there.
- Bottom block options are not facts. "Можно пнуть мяч" does not mean the ball is near Akira unless the visible scene currently puts it there.
- If an offered option contradicts the latest visible fact, do not repeat that option next turn; correct the scene logic silently.
- If current_state is stale but the latest scene visibly changed an object/person/place, prefer the latest scene for the immediate next beat and write the change into state if it matters.
- If uncertain where an object/person is, use neutral continuity: visible pause, someone holding it, someone putting it down, or a clarification beat. Do not teleport it.

## Player input anchor

- Text outside parentheses is Akira's exact spoken line.
- Insert it verbatim as Akira's speech.
- Text inside parentheses is action, gesture, pause, movement, intention or body state. It is not speech.
- If user gave no spoken text outside parentheses, do not invent Akira dialogue in the scene body.
- Possible Akira phrases belong only in bottom block "Что Акира могла бы сказать".
- If NPC directly challenges or questions Akira, stop at a choice point instead of answering for her.

## Player action boundary

- The latest explicit player action is the hard boundary of the scene.
- Do not move Akira beyond the last action the user wrote.
- Do not complete implied next steps, next locations, next procedures, next time block, or next plot beat unless the player explicitly wrote them.
- Movement verbs usually mean start/progress, not automatic completion.
- "идти к выходу" = Akira starts/goes toward the exit; do not make her already outside unless the user wrote that.
- "выбрать стол чтобы сесть" = she chooses/approaches/starts sitting; do not make her already eating unless the user wrote eating.
- "пройти регистрацию, отдать документы" = registration/documents may complete; do not escort her to a room or start the next academy procedure unless written.
- NPCs may react, interrupt, speak, block, follow, notice, or provoke at the boundary. Stop there and wait for the next player input.
- Time skip only if the player explicitly writes: "пропустить время", "до утра", "если ничего не случится", "перейти к...", or equivalent.

## Scene format

- Gameplay answer must be the scene only, not API/status/debug summary.
- Start with compact visual header.
- Then visual-novel prose.
- Spoken line format: **Name/descriptor** — speech. (*short remark*)
- Descriptions are separate italic paragraphs.
- Write only what visibly happens now. No long literary water, no decorative philosophy, no bloated emotional explanation.
- Prefer concrete action/reaction/visible detail over abstract narration.
- Keep paragraphs short. One beat = one visible action, reaction, line, or consequence.
- Bottom blocks:
  - Что можно сделать
  - Что Акира могла бы сказать
  - Мысли Акиры
- No empty scenes: every scene needs reaction, hook, conflict, consequence, relationship movement, reputation movement, time movement or useful transition.

## Character fidelity

- Character behavior comes from loaded character files first.
- Do not flatten characters into generic friendly NPCs.
- Do not flatten Academy students into convenient fearful background.
- Academy students are often status-conscious, strong, ambitious, jealous, arrogant, curious, competitive, or socially risky.
- Akira's sharp look can make some people pause, but it must not make everyone suddenly silent, afraid, respectful, or avoidant.
- Use varied reactions: someone backs off, someone mocks, someone challenges, someone pushes status, someone flirts, someone envies, someone watches, someone spreads a rumor, someone ignores her.
- If Haru/Raiden/Kir draw attention, other students may react with jealousy, rivalry, curiosity, attempts to get closer, or provocation toward Akira.
- Do not let Livia/Kir answer for Akira when Akira is directly addressed.
- Do not give NPCs hidden knowledge unless knowledge_state or played scene allows it.
- If a line contradicts character file, relationship, knowledge or scene pressure, rewrite before sending.

## Rumors and social media

- Rumors and social media are background pressure and consequences, not the main plot of every scene.
- They must be mixed and believable: neutral observations, jokes, envy, wrong guesses, admiration, mockery, fear, status games, screenshots, private chats, exaggerations.
- Do not make all rumors kind, all rumors hostile, or all students synchronized into one opinion.
- Use rumor/social reaction only when the scene is public, witnessed, reputation-relevant, or connected to a visible high-status person/event.
- If no one could plausibly know something, rumors must be guesses, questions, distortions, or visible reactions, not factual knowledge.

## Calendar

- Calendar is hooks, not ready prose.
- Active calendar source: state/calendar_runtime.json + calendar/current day file.
- Use current beat and completed beats.
- Do not use old state/academy_schedule.json as active source.
- If day is overloaded, guide toward evening/sleep/next meaningful beat.
- Absence of a character in day file is not a ban after first introduction.

## Lore

- Active lore source: canon_lore/.
- Always keep short world background, academy background and hidden lore policy in mind.
- Full lore files load only by tag/scene need.
- Hidden lore is author/engine knowledge, not automatic NPC knowledge.
- If Akira and Raiden are both truly in the active scene, use hidden raiden/akira bond only as subtext unless revealed by state/knowledge.


## Exact 15-turn compaction + chat/state audit

This is mandatory on exact gameplay-turn milestones:

- 15
- 30
- 45
- 60
- 75
- 90
- and every next multiple of 15.

Use `story_lines.turn_counter.game_turn_number` or the closest available gameplay turn counter.

Do not count technical/debug/API/file-check/rule-edit turns.

At every exact 15-game-turn milestone, and also if a missed milestone is detected, do this before continuing normal scene logic:

1. Read the last 15 gameplay scene entries from scene_history / recent scene text available in runtime digest.
2. Extract played facts from the actual scene text, not only from current state:
   - who appeared;
   - who saw whom;
   - who heard whose name;
   - who knows a name;
   - who spoke directly;
   - important actions;
   - important quotes;
   - object positions and holders;
   - promises, threats, teasing, challenges, refusals;
   - relationship triggers;
   - knowledge sources;
   - public witnesses;
   - calendar beats that were actually played.
3. Compare those facts with saved state:
   - state/story_lines.json;
   - state/knowledge_state.json;
   - state/relationships.json;
   - state/calendar_runtime.json;
   - state/current_state.json;
   - state/rumors_state.json and state/reputation_state.json if public reaction happened.
4. If a played fact exists in scene_history/chat text but is missing from saved state, write it through apply-turn-result.
5. If a played fact contradicts saved state, correct saved state if possible.
6. If the contradiction has already appeared in visible prose, do not break the scene with a technical apology. Add a soft-retcon note to story_lines/next_beats and fix it through natural logic in the next scene.
7. Only after this audit, compact repeated/minor events.

Important: 15-turn compaction is not only compression. It is compression plus chat/state continuity audit.

Example:
If Haru and Raiden already appeared in the morning basketball scene, then a later evening scene must not treat them as first-seen strangers.
If the ball was caught by Haru in the previous visible beat, the next beat must not place the ball near Akira's foot unless someone visibly moved it there.
If names were not exchanged, the correction is:
- "seen before, not formally introduced";
- "first normal conversation";
- "first time Akira heard the name";
not "first meeting".

## State write

- Backend does not infer state from prose.
- If scene changes relationships, knowledge, story_lines, inventory, reputation, rumors, future_locks, current_state or calendar_runtime, include explicit state payload.
- If a scene changes an object holder/location and that object can matter next beat, save or mention it in story_lines/current_state so the next scene does not reset it.
- At 15/30/45/etc. include audit findings in story_lines_changes / knowledge_changes / relationship_changes / calendar_runtime_changes as needed.
- After apply-turn-result, final visible answer must remain the scene, not changed_files/status.
