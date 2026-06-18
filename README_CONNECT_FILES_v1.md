# academy_prequel_connect_files_v1

Безопасный ZIP для ручной заливки в `akira-academy-prequel`.

## Как применять

1. Распаковать в корень репозитория.
2. Запустить: `python apply_connect_files_patch.py`
3. Проверить `git diff`.
4. Задеплоить.
5. Начать новую сессию.

## Что делает

- подключает clean YAML персонажей раньше старых `characters/main/*.md`;
- добавляет `canon/lore/*` и `gpt/director/*` в recommended files;
- добавляет play mode silence lock;
- ставит стартовый `akira_behavior_profile: akira_v2_poisonous`;
- добавляет Кира как раннего scheduled персонажа;
- добавляет state-заготовки под память.

## Что НЕ чинит

Не чинит полную раскладку `applyTurnResult` по relationships/open_threads/shared_incidents/character_memory.
