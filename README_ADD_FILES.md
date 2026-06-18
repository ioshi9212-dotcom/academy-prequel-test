# Добавочные файлы для akira-academy-prequel

Этот архив НЕ меняет код и НЕ трогает рабочий запуск.

## Почему пути такие

Текущий рабочий запуск идёт через:

- `Procfile` → `app.server:app`
- `app/server.py` → `app.compact`
- `app.compact` синхронизирует в Railway Volume только:
  - `canon/`
  - `characters/`
  - `gpt/`
  - `templates/`
  - `state/`

Поэтому лор положен в `canon/lore/`, а правила директора — в `gpt/director/`.
Так они смогут попасть в `/data` без изменения `SYNC_FROM_REPO`.

## Что добавляется

- `canon/lore/*` — компактный лор мира, Академии, энергии, соцсетей, фракций, hidden и старта 1198.
- `gpt/director/*` — правила: каждая сцена что-то двигает, сжимать рутину, фоновые системы, короткий план, редкие сны.
- `state/*` — пустые session-local шаблоны для будущих соцсетей, рейтинга, open_threads, incidents и короткого плана.

## Что НЕ трогать этим архивом

- `Procfile`
- `app/compact.py`
- `app/server.py`
- `app/session_routes.py`
- текущий формат сцены
- createSession
- Railway Volume/ENV

## Следующий кодовый патч потом

После добавления файлов можно будет мягко обновить `app.compact`, чтобы turn-contract начал отдавать маленькие slices:

- `lore_slice`
- `social_slice`
- `rating_slice`
- `director_short_plan_slice`

Но это отдельный шаг.
