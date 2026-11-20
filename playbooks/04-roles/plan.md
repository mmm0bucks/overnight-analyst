# План

1. **Ветка** от предыдущего этапа: `git switch -c stage/04-roles`.
2. **Скопируй** из шаблона:
   | Откуда в шаблоне | Куда в репозитории агента |
   |---|---|
   | `agents/*.md` | `agents/` |
   | `examples/roles/src/orchestrator/check_roles.py` | `src/orchestrator/check_roles.py` |
   | `examples/roles/src/orchestrator/start_checks.py` | `src/orchestrator/start_checks.py` |
   | `examples/roles/tests/test_roles.py` | `tests/test_roles.py` |
3. **Тесты и проверки:** `python -m unittest discover -s tests`, затем `python src/orchestrator/check_roles.py` и `python src/orchestrator/start_checks.py`. Все должны пройти.
4. **Профили модели.** Проверь, что в `config/local.env` заполнены `MODEL_PROFILE_LOW` и `MODEL_PROFILE_HIGH`. Пусто — попроси владельца.
5. **Изучи, как в харнессе устроены субагенты.** Выбери вариант Р1, Р2 или Р3 (`spec.md`).
6. **Перенеси роли** в механизм харнесса. Для каждой: описание, текст роли как системный промпт, инструменты из `tools`, профиль модели, лимиты. Конфиг харнесса для ролей положи в `config/harness/` или запиши в решении, где он лежит.
7. **Роль в шлюз.** Код, запускающий роль, ставит её имя в сессию шлюза. Проверь, что модель не может его поменять.
8. **Скрипт запуска** агента (какой есть сейчас) первым вызывает `start_checks.py`; код не 0 — не запускать.
9. **Запиши решение** в `docs/decisions/0002-roles.md`: вариант и почему; где конфиг ролей; как имя роли попадает в шлюз; как держатся лимиты.
10. **Коммит:** `stage 04: roles`.
11. **Приёмка.** Живые проверки делай в учебной задаче, без запуска чего-либо в кластере.
