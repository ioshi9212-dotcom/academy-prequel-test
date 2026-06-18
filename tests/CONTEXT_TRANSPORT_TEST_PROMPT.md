Технический режим. Не считать игровым ходом. Сцену не продолжать. Ничего не сохранять.

Проверяем context transport hotfix v6 после фикса.

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
Не пересказывай сюжет.

Покажи только:
1. api/version из health.
2. Есть ли repairSceneRoster: найден / не найден.
3. current_state roster.
4. active_character_ids / nearby_character_ids из turn-contract.
5. required_files_count.
6. chunks_total из manifest.
7. chunk-вызовов выполнено.
8. Есть ли ResponseTooLargeError.
9. Полный список required_files.
10. Есть ли тяжёлые полные файлы:
   - gpt/engine_prompt.md
   - gpt/scene_format.md
   - canon/source_usage_rules.md
   - canon/relationship_memory_rules.md
   - gpt/locks/apply_state_after_turn_lock.md
11. Есть ли:
   - runtime/scene_context_digest.md
   - characters/akira/character.yaml
   - characters/livia/character.yaml
12. Топ-10 loaded files по size_chars.
13. Краткий вывод: стало ли быстрее и что всё ещё тяжёлое.
