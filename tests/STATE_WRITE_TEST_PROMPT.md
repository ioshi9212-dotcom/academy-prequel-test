Технический режим. Не считать игровым ходом. Сцену не продолжать. Ничего не сохранять.

Проверь последнюю запись состояния.

Вызови:
1. getSessionContext
2. getSessionTurnContract
3. GET /api/v1/sessions/{session_id}/json/state/last_apply_result.json
4. GET /api/v1/sessions/{session_id}/json/state/relationships.json
5. GET /api/v1/sessions/{session_id}/json/state/story_lines.json
6. GET /api/v1/sessions/{session_id}/json/state/knowledge_state.json

Покажи коротко:
- last_apply_result.status
- last_apply_result.changed_files
- payload_sections_present
- обновились ли пары akira__raiden / akira__haru / livia__raiden / livia__haru
- появились ли active_lines haru_akira / akira_raiden_hidden_pull / livia_raiden_interest / livia_haru_interest
- если changed_files нет при значимой сцене — напиши: state-payload не был собран.
