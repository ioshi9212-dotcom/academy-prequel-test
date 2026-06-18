Технический режим. Не считать игровым ходом. Сцену не продолжать. Ничего не сохранять.

Проверяем context medium quality v7.

Используй текущую игровую сессию:
session_20260610_102936_f7c22ecd

Вызови строго:
1. health / api version
2. getSessionContext
3. getSessionTurnContract
4. getRequiredFilesManifest
5. getRequiredFilesChunk chunk_index=0
6. продолжай getRequiredFilesChunk по next_chunk_index, пока has_more=false.

Не вызывай apply-turn-result.
Не пиши сцену.

Покажи только:
- api/version
- repairSceneRoster найден / не найден
- active_character_ids / nearby_character_ids
- required_files_count
- chunks_total
- chunk-вызовов выполнено
- ResponseTooLargeError был / не был
- runtime/scene_context_digest.md есть / нет
- size_chars runtime/scene_context_digest.md
- есть ли в digest блоки Medium scene style / Medium source usage / Medium relationship memory
- есть ли в required_files тяжёлые full files: engine_prompt, scene_format, source_usage_rules, relationship_memory_rules, apply_state_after_turn_lock
- топ-10 loaded files
- краткий вывод: скорость стала средняя / слишком тяжёлая / слишком сухая
