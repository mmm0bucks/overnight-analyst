# План

Образцы файлов лежат в `examples/repo-skeleton/` этого репозитория. Копируй их, не переписывай.

1. **Проверь git.** `git --version`. Нет git — остановись, `НУЖНО УТОЧНИТЬ: git не установлен`.
2. **Спроси владельца путь к папке агента**, если его нет в задаче. Папка должна быть пустой или не существовать.
3. **Создай репозиторий.**
   ```
   git init -b main <ПАПКА_АГЕНТА>
   ```
4. **Создай структуру** из `BUILD.md`. В каждую пустую папку положи `README.md` в одну строку: что будет лежать в папке.
5. **Скопируй образцы** из `examples/repo-skeleton/`:
   | Откуда | Куда |
   |---|---|
   | `dot-gitignore` | `.gitignore` |
   | `dot-gitattributes` | `.gitattributes` |
   | `AGENTS.md` | `AGENTS.md` |
   | `tools/hooks/pre-commit`, `tools/hooks/pre-push` | `tools/hooks/` |
   | `config/allowed_remote.txt` (пустой) | `config/allowed_remote.txt` |
   | `config/local.env.example` | `config/local.env.example` |
6. **Скопируй конституцию** `blueprint/constitution.md` в корень как `constitution.md`.
7. **Запиши версию шаблона:** коммит этого репозитория, по которому работаешь, одной строкой в `TEMPLATE_VERSION`.
8. **Включи хуки** для этого репозитория:
   ```
   git -C <ПАПКА_АГЕНТА> config core.hooksPath tools/hooks
   ```
9. **Автор коммитов** — владелец. Возьми имя и почту из его глобальной настройки git. Если её нет — спроси владельца и задай только для этого репозитория (`git config user.name`, `git config user.email` без `--global`).
10. **Создай `config/local.env`** по образцу `local.env.example` и заполни, что знаешь. Он в `.gitignore`, в коммит не попадёт. Чего не знаешь — оставь пустым и перечисли в отчёте.
11. **Первый коммит.**
    ```
    git add -A
    git commit -m "init: skeleton from template <TEMPLATE_VERSION>"
    ```
12. **Пройди приёмку** (`acceptance.md`) и заполни отчёт (`playbooks/REPORT.md`).

## Потом, когда владелец создаст внутренний репозиторий

Это делает владелец, не сборщик:

```
git remote add origin <адрес>
```

Тот же адрес одной строкой — в `config/allowed_remote.txt`, коммит. После этого push работает только на этот адрес.
