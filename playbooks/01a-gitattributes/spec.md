# Плейбук 01a. Хуки с LF в уже собранном репозитории

Для репозиториев, собранных по плейбуку 01 до того, как в образец добавили `.gitattributes`. Новым сборкам не нужен: файл уже входит в плейбук 01.

## Зачем

Git для Windows может при checkout заменить концы строк на CRLF. С CRLF строка `#!/bin/sh` в хуке не работает, и хуки секретов и push молча перестают действовать.

## Шаги

1. Отдельная ветка: `git switch -c fix/gitattributes`.
2. Скопируй `examples/repo-skeleton/dot-gitattributes` из шаблона в корень репозитория агента как `.gitattributes`.
3. `git add --renormalize .` и `git add .gitattributes`.
4. Коммит: `fix: keep LF in hooks (.gitattributes)`.
5. Обнови `TEMPLATE_VERSION` на коммит шаблона, по которому работал, тем же коммитом.

## Приёмка

Каждая проверка в контрольный блок строкой `01a A<номер> PASS` или `01a A<номер> FAIL <буква>`.

- **A1.** `git check-attr eol tools/hooks/pre-commit tools/hooks/pre-push` выводит `eol: lf` для обоих.
- **A2.** Проверки хуков из `playbooks/01-repo/acceptance.md` (секрет и push) снова проходят.
- **A3.** `git status --short` пусто.

## Откат

Владелец не вливает ветку `fix/gitattributes` или удаляет её.
