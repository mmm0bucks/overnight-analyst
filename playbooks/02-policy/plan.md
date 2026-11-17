# План

1. **Ветка.** В репозитории агента: `git switch -c stage/02-policy`.
2. **Python.** `python --version`. Ниже 3.11 — остановись, `НУЖНО УТОЧНИТЬ` (буква U в контрольном блоке).
3. **Скопируй образцы** из `examples/policy/` шаблона, сохраняя пути:
   | Откуда | Куда |
   |---|---|
   | `src/gateway/policy.py` | `src/gateway/policy.py` |
   | `src/orchestrator/check_policy.py` | `src/orchestrator/check_policy.py` |
   | `tests/test_policy.py` | `tests/test_policy.py` |
   | `config/policy/rules.example.toml` | `config/policy/rules.example.toml` и ещё раз как `config/policy/rules.toml` |
4. **Тесты.** Из корня репозитория агента:
   ```
   python -m unittest discover -s tests
   ```
   Все должны пройти.
5. **Попроси владельца утвердить политику.** Он сам выполняет из корня репозитория:
   ```
   python src/orchestrator/check_policy.py --approve
   ```
   Появится `config/policy/rules.sha256`. Пока его нет, переходи к приёмке пунктов, которые от него не зависят, и жди.
6. **Проверка при старте.** `python src/orchestrator/check_policy.py` должна вывести «политика в порядке», код выхода 0.
7. **Пометь в `AGENTS.md` репозитория агента** одной строкой: любой запуск агента начинается с `check_policy.py`; ненулевой код — не запускать. Сам запуск появится на этапе 7.
8. **Коммит** в ветке: `stage 02: policy and start check`.
9. **Приёмка** (`acceptance.md`) и контрольный блок.
