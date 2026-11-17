# Приёмка

Каждая проверка в контрольный блок строкой `02 A<номер> PASS` или `02 A<номер> FAIL <буква>`.

- **A1.** `python -m unittest discover -s tests` — все тесты пройдены, тестов не меньше 14.
- **A2.** `python src/orchestrator/check_policy.py` — код выхода 0.
- **A3.** Допиши в конец `config/policy/rules.toml` пустую строку и запусти проверку — код выхода 1, сообщение «не утверждён». Затем `git checkout -- config/policy/rules.toml` и снова проверка — код 0.
- **A4.** Переименуй `config/policy/rules.toml` во временное имя и запусти проверку — код выхода 1, сообщение «нет файла политики». Верни имя, проверка — код 0.
- **A5.** Решение по политике для запрещённого всегда:
  ```
  python -c "import sys; sys.path.insert(0,'src/gateway'); import policy as p; r=p.load_rules('config/policy/rules.toml'); print(p.decide(r,'git.push','*','lead','day'), p.decide(r,'kernel.run_read','*','analyst','day',('untrusted_read',)))"
  ```
  Вывод: `deny deny`.
- **A6.** `git diff --stat main` показывает только файлы из таблицы «Что получится» и `AGENTS.md`.
