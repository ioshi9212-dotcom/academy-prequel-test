# Lock: восстановление состояния при сбое загрузки

Если состояние сессии не загрузилось с первого раза, нельзя продолжать сцену из памяти чата.

Но нельзя сразу останавливать новеллу без попытки восстановления.

## Порядок восстановления

1. Повторить загрузку session context.
2. Проверить health.
3. Проверить список sessions и наличие текущего session_id.
4. Повторить загрузку session context.
5. Если полный context всё ещё не загрузился, вручную загрузить основные state-файлы:
   - state/current_state.json
   - state/relationships.json
   - state/knowledge_state.json
   - state/inventory_state.json
   - state/reputation_state.json
   - state/rumors_state.json, если нужен контекст слухов.
6. Если state-файлы загрузились, можно продолжать сцену строго по ним.
7. Если не загрузился ни context, ни state, остановиться и указать, какой запрос упал и с какой ошибкой.

## При ошибке слишком большого ответа

Если полный context слишком большой, перейти на ручную загрузку state-файлов и нужных карточек.

Минимум перед сценой:

- gpt/engine_prompt.md
- gpt/scene_format.md
- canon/novella_goal.md
- canon/character_story_roles.md
- characters/main/akira.md
- карточки active/nearby персонажей
- relevant locks из gpt/locks и characters/locks.

## Запрещено

- продолжать сцену только по памяти чата;
- брать события из старой сессии;
- восстанавливать state догадками;
- останавливаться без попытки recovery;
- писать новую сцену, если не загрузился ни context, ни fallback state.

## Короткая фраза при успехе

Если recovery успешен:

`Context восстановлен через state-файлы. Продолжаю по текущему state.`

Если recovery не успешен:

`Не удалось загрузить session context и fallback state. Ошибка: ...`
