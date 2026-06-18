# Academy start cleanup patch

Пакет правит конфликтные файлы для `akira-academy-prequel`.

## Что исправлено

1. Стартовая локация 15 августа 1198:
   - было: главный двор / размытый подход;
   - стало: `academy_back_court_exit` — задний выход Академии со стороны корта / баскетбольные площадки.

2. Стартовая одежда Акиры:
   - стало: кроссовки, чёрные штаны карго, топ, бордовый худи;
   - форма Академии не считается надетой без действия игрока или `uniform_worn=true`.

3. Телефон:
   - телефон лежит внутри багажа;
   - не показывать телефон в visible header, пока Акира не достала его действием.

4. Календарь:
   - `state/academy_schedule.json` и `canon/august_15_calendar.yaml` синхронизированы;
   - старый `state/academy_schedule_patch_v2.json` помечен к удалению.

5. Локации:
   - `canon/academy_locations.md` — базовая карта;
   - `state/location_registry.md` — только сыгранные/уточнённые локации, без дубля всего canon.

6. Runtime lock:
   - добавлен `gpt/locks/academy_start_cleanup_lock.md`;
   - `app/context_transport_header_hotfix.py` подключает этот lock в required files.

## Как заливать

Рекомендуемая ветка:

```txt
cleanup/academy-start-court-outfit
```

1. Создать новую ветку от текущего `main`.
2. Залить файлы из ZIP с сохранением путей.
3. Удалить файлы из `patch_notes/DELETE_THESE_ON_BRANCH.md`.
4. Задеплоить / дождаться Railway.
5. Создать новую сессию и проверить current_state / required files.

## Проверка после заливки

В техрежиме проверить:

- `current_location_id = academy_back_court_exit`;
- `current_location_text` содержит задний выход / корт / баскетбольные площадки;
- `current_outfit` содержит штаны карго;
- `uniform_worn = false`;
- `visible_inventory` не содержит телефон;
- required files содержит `gpt/locks/academy_start_cleanup_lock.md`.
