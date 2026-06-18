Технический режим. Не считать игровым ходом. Сцену не продолжать. Ничего не сохранять.

Проверь selective context runtime.

Вызови:
1. getSessionContext
2. getSessionTurnContract
3. getRequiredFilesManifest
4. getRequiredFilesChunk chunk_index=0 max_chars=12000 max_items=1
5. продолжай getRequiredFilesChunk по next_chunk_index, пока has_more=false.

Не вызывай apply-turn-result.
Не пиши сцену.

Покажи только:
- session_id
- api/version
- active_character_ids
- nearby_character_ids
- required_files
- chunks_total
- loaded_count
- есть ли runtime/scene_context_digest.md
- есть ли лишние character files вне active/nearby/mentioned/scheduled
- есть ли в digest: Current state / Relationship slice / Story lines slice / Knowledge slice / State update reminder
- сколько chunk-вызовов выполнено

Норма: chunks_total <= 24 для обычной игровой сцены. Full bundle разрешён только при force_full_context/context_mode=diagnostic.
