# academy_prequel_clean_context_patch_v1

Это ZIP без lock-файлов и без тяжёлого лора.

Цель: аккуратно подключить новую схему персонажей `characters/<id>/main.yaml + character.yaml + past.yaml`
к уже работающему `app.compact`, не переписывая основу движка.

## Почему не заменяем весь app/compact.py

`app/compact.py` большой и рабочий. Чтобы не сломать основу, этот пакет не переписывает его целиком.

Вместо этого:
- добавляется маленький модуль `app/compact_context_patch.py`;
- `app/server.py` начинает импортировать его;
- модуль импортирует старый `app.compact`, мягко заменяет только функции выбора файлов;
- все старые маршруты, createSession, applyTurnResult, format contract и Railway Volume остаются как были.

## Что меняется

Теперь `required_files/recommended_files` должны брать clean YAML персонажей:

- `characters/akira/main.yaml`
- `characters/akira/character.yaml`
- `characters/akira/past.yaml`
- `characters/livia/main.yaml`
- `characters/livia/character.yaml`
- `characters/kir/main.yaml`
- `characters/kir/character.yaml`
- `characters/kir/past.yaml`

Старые `characters/main/*.md` используются только как fallback, если YAML-папки нет.

## Что НЕ делаем

- не добавляем новые lock-файлы;
- не подключаем весь `canon/lore/*`;
- не подключаем весь `gpt/director/*`;
- не форсим Кира через `scheduled_character_ids`;
- не меняем createSession;
- не меняем формат сцены;
- не чиним пока routing памяти applyTurnResult.

## Как применять

1. Распакуй ZIP в корень репозитория.
2. Загрузи файлы в GitHub с заменой:
   - `app/server.py`
   - `app/compact_context_patch.py`
   - `state/current_state.json`
3. Дождись deploy.
4. Начни новую сессию.
5. Проверь тех.диагностикой, попали ли `characters/akira/character.yaml`, `characters/livia/character.yaml`, `characters/kir/character.yaml` в required/recommended.
