# overnight-analyst

[![ci](https://github.com/mmm0bucks/overnight-analyst/actions/workflows/ci.yml/badge.svg)](https://github.com/mmm0bucks/overnight-analyst/actions/workflows/ci.yml)

[Русский](#русский) · [English](#english)

## Русский

LLM-агент, который **за ночь** делает утреннюю домашку аналитика данных: читает трекер
задач и командную вики, проверяет гипотезы о качестве данных SQL-запросами **только на
чтение** и кладёт в Obsidian короткий отчёт, где у каждого утверждения есть источник.

Самое интересное здесь не модель, а обвязка вокруг неё: что модели делать **нельзя** и что
после неё проверяет обычный код.

> Проект сделан с нуля на синтетических данных. Он повторяет идеи внутреннего инструмента,
> который я построил на работе, но кода, промптов, данных и названий оттуда здесь нет.

### Быстрый старт (ключ API не нужен)

```bash
uv sync
uv run overnight init-demo                 # синтетическая база с заложенными ошибками
uv run overnight run --today 2026-10-27    # офлайн-режим: весь пайплайн бесплатно
```

Результат: `vault/Overnight/Reports/<дата> <run_id>.md`, `vault/Overnight/Hypotheses.md`
и все промежуточные файлы в `runs/<run_id>/`.

С настоящей моделью (любой OpenAI-совместимый API с вызовом инструментов):

```bash
cp .env.example .env   # впишите ключ; адрес и модель уже заполнены
uv run --env-file .env overnight run --llm http --vault "/путь/к/вашему/vault"
```

### Оценка на нескольких прогонах

```bash
uv run --env-file .env overnight eval --runs 3 --llm http --today 2026-10-27
```

Каждый прогон идёт в своей папке `eval/<время>/<n>`, чтобы не видеть гипотезы, закрытые
прошлым прогоном. Итог сверяется с `demo/expected.json` и пишется в
`eval/<время>/summary.md`: таблица прогонов и точность по каждой гипотезе.

### Docker

```bash
docker build -t overnight-analyst .
docker run --rm overnight-analyst            # бесплатное офлайн-демо
docker run --rm --env-file .env \
  -v "$PWD/state:/app/state" -v "$PWD/vault:/app/vault" \
  overnight-analyst sh -c "overnight init-demo && overnight run --llm http"
```

`state/` монтируется, чтобы общий счётчик токенов ключа жил между запусками контейнера.
CI собирает образ и запускает в нём офлайн-демо на каждом PR.

### Как это работает

```
preflight → collect → analyze → synthesize → critique → finalize (проверки) → publisher
             LLM       LLM        LLM          LLM         код                    код
```

* **Узкие этапы, у каждого свой чистый контекст.** Сбор не анализирует, синтез не
  добавляет фактов, критика только проверяет. Каждый этап возвращает JSON по контракту.
* **Инструменты только на чтение.** Трекер, вики и SQL. Инструментов записи нет вообще.
* **Источники везде.** Каждый вызов инструмента получает номер `S1, S2, ...`, и каждое
  утверждение на них ссылается.
* **Проверки в коде, а не в промпте.** После этапов с моделью обычный код решает, чем
  закончился прогон: `ok`, `partial` или `failed`.
* **Один писатель.** В vault и в память агента пишет только publisher: атомарно, с бэкапом,
  с вычисткой секретов и только внутри своих блоков, не трогая ваши заметки.

Подробнее: [docs/architecture.ru.md](docs/architecture.ru.md) · решения:
[docs/decisions](docs/decisions)

### Защита

| Риск | Что защищает | Тест |
|---|---|---|
| Модель меняет или удаляет данные | инструментов записи нет; проверка SQL + подключение к базе `read_only` | `test_sqlguard.py` |
| Модель читает произвольные файлы через SQL | `read_*`, `glob`, `COPY`, `ATTACH`… запрещены | `test_sqlguard.py` |
| Выдуманные или неверно посчитанные числа | каждое `value` должно встречаться в указанном источнике | `test_gates.py` |
| Синтез добавляет неподтверждённые факты | синтез может ссылаться только на источники прошлых этапов | `test_gates.py` |
| Бесконечный цикл или перерасход | лимит токенов, вызовов и времени перед каждым вызовом; лимит ходов | `test_agent.py` |
| Нестабильный API | повтор при 429/5xx с паузами 2/4/8 с; остальные 4xx не повторяются | `test_llm_http.py` |
| Плохой прогон портит память | список гипотез обновляется, только если прошли все проверки | `test_pipeline.py` |
| Никто не заметил упавшую ночь | при сбое preflight всё равно публикуется заметка `failed` | `test_pipeline.py` |
| Два прогона за день затирают друг друга | уникальный `run_id`, а не дата | `test_pipeline.py` |
| Перезаписаны заметки человека | маркеры управляемого блока, атомарная запись + бэкап | `test_publisher.py` |

### Оценка

Демо-база генерируется с фиксированным seed и **заложенными ошибками** (дубли откликов,
клиенты сразу в тесте и контроле, отклики раньше контакта), плюс одна ложная гипотеза.
Это бесплатная «правда», с которой можно сверять агента:

| Гипотеза | Правда | Офлайн-режим | LLM (`--llm http`) |
|---|---|---|---|
| H1 дубли откликов | да, 15 строк | подтверждена | подтверждена, 15 |
| H2 пересечение теста и контроля | да, 25 клиентов | подтверждена | подтверждена, 25 |
| H3 отклик раньше контакта | да, 12 строк | подтверждена | подтверждена, 12 |
| H4 кампания кончается раньше старта | нет | отклонена | отклонена, 0 |
| H5 тест лучше контроля во всех кампаниях | да (4 из 4) | пропущена (нет готового SQL) | подтверждена, SQL написала сама |

Колонка LLM — `qwen3.8-27b-noreason`. Оценка `overnight eval --runs 3`, каждый прогон в
чистой папке:

| Оценка (3 прогона) | Верно | Статус | Токенов на прогон | Время на прогон |
|---|---|---|---|---|
| 2026-10-30, до исправления | 0 из 15 | 3× `partial` | 55–57 тыс. | 187–297 с |
| 2026-10-30, после | **15 из 15** | 3× `ok` | 49–65 тыс. | 218–384 с |

«До» analyze каждый раз падал одинаково: исправление битого JSON выпадало на последний ход и
терялось. «После» в одном прогоне модель снова прислала испорченный JSON
(`"sources": ["S": [], ...`) — исправление сработало, прогон дошёл до `ok`.
Подробности: [разбор первой оценки](docs/postmortems/2026-10-30-first-eval.ru.md) и
[разбор первых прогонов](docs/postmortems/2026-10-28-collect-retry-loop.ru.md).

Время уходит в основном на то, что провайдер генерирует итоговый JSON этапа, а не на
инструменты. Три прогона на одной модели и одних данных — это ещё не бенчмарк: следующий
шаг — регрессионная проверка в CI, см. [ROADMAP.ru.md](ROADMAP.ru.md).

Офлайн-режим — детерминированная заглушка (не LLM), чтобы CI прогонял весь пайплайн.

### Разработка

```bash
uv run ruff check . && uv run mypy && uv run pytest -q
```

Как проект делался с помощью AI и что решалось и проверялось вручную:
[AI_WORKFLOW.ru.md](AI_WORKFLOW.ru.md).

### Известные ограничения

* Проверка SQL лексическая; настоящая страховка — подключение только на чтение. Это не
  песочница уровня ОС.
* Лимит времени проверяется между вызовами, поэтому один медленный HTTP-вызов ограничен
  только таймаутом клиента (120 с).
* Поиск по вики — простой поиск подстроки, без эмбеддингов.

### Лицензия

MIT

---

## English

An LLM agent that does a data analyst's morning homework **overnight**: it reads the task
tracker and the team wiki, checks data-quality hypotheses against the warehouse with
**read-only** SQL, and publishes a short report — where every claim cites its source — into
an Obsidian vault.

The interesting part is not the LLM. It is the harness around it: what the model is
**not** allowed to do, and what plain code checks after it.

> Clean-room project on synthetic data. It reuses design ideas from an internal tool I
> built at work; no code, prompts, data or names from that project are included.

### Quickstart (no API key needed)

```bash
uv sync
uv run overnight init-demo                 # synthetic warehouse with planted defects
uv run overnight run --today 2026-10-27    # offline policy, full pipeline, zero cost
```

Output: `vault/Overnight/Reports/<date> <run_id>.md`, `vault/Overnight/Hypotheses.md`,
and every intermediate artifact in `runs/<run_id>/`.

With a real model (any OpenAI-compatible endpoint with tool calling):

```bash
cp .env.example .env   # put your key; base URL and model are prefilled
uv run --env-file .env overnight run --llm http --vault "/path/to/your/vault"
```

### Evaluation over several runs

```bash
uv run --env-file .env overnight eval --runs 3 --llm http --today 2026-10-27
```

Every run gets its own folder `eval/<time>/<n>`, so it never sees hypotheses closed by an
earlier run. Results are checked against `demo/expected.json` and written to
`eval/<time>/summary.md`: one row per run plus accuracy per hypothesis.

### Docker

```bash
docker build -t overnight-analyst .
docker run --rm overnight-analyst            # free offline demo
docker run --rm --env-file .env \
  -v "$PWD/state:/app/state" -v "$PWD/vault:/app/vault" \
  overnight-analyst sh -c "overnight init-demo && overnight run --llm http"
```

`state/` is mounted so the key's lifetime token counter survives container restarts.
CI builds the image and runs the offline demo in it on every PR.

### How it works

```
preflight → collect → analyze → synthesize → critique → finalize (gates) → publisher
             LLM       LLM        LLM          LLM         code              code
```

* **Narrow stages, fresh context each.** Collect does not analyze, synthesize adds no
  facts, critique only reviews. Each stage returns JSON validated against a contract.
* **Read-only tools.** Tracker, wiki and SQL. There is no write tool at all.
* **Sources everywhere.** Each tool call becomes `S1, S2, ...`; every claim cites them.
* **Gates in code, not in the prompt.** After the LLM stages, deterministic checks decide
  whether the run is `ok`, `partial` or `failed`.
* **One writer.** Only the publisher touches the vault and the agent's memory — atomically,
  with backups, secret redaction and managed blocks that leave your own notes alone.

Details: [docs/architecture.md](docs/architecture.md) · decisions: [docs/decisions](docs/decisions)

### Guardrails

| Risk | Control | Test |
|---|---|---|
| Model writes or deletes data | no write tools; SQL validator + `read_only` DB connection | `test_sqlguard.py` |
| Model reads arbitrary files via SQL | `read_*`, `glob`, `COPY`, `ATTACH`… blocked | `test_sqlguard.py` |
| Invented / miscalculated numbers | every `value` must occur in a cited source | `test_gates.py` |
| Synthesis adds unsupported facts | synthesis may only cite sources from earlier stages | `test_gates.py` |
| Runaway cost or loop | token / tool-call / time budget checked before every call; max turns | `test_agent.py` |
| Flaky endpoint | retry 429/5xx with 2/4/8 s backoff; never retry other 4xx | `test_llm_http.py` |
| Bad run corrupts memory | backlog updated only when all gates pass | `test_pipeline.py` |
| Nobody notices a failed night | preflight failure still publishes a "failed" note | `test_pipeline.py` |
| Two runs on one day overwrite each other | unique `run_id`, never date-keyed | `test_pipeline.py` |
| Human notes overwritten | managed block markers, atomic write + backup | `test_publisher.py` |

### Evaluation

The demo warehouse is generated from a fixed seed with **planted defects** (duplicate
responses, treatment/control leakage, responses before contact) plus one false hypothesis.
That gives free ground truth:

| Hypothesis | Truth | Offline policy | LLM (`--llm http`) |
|---|---|---|---|
| H1 duplicate responses | yes, 15 rows | confirmed | confirmed, 15 |
| H2 control leakage | yes, 25 customers | confirmed | confirmed, 25 |
| H3 response before contact | yes, 12 rows | confirmed | confirmed, 12 |
| H4 campaign ends before start | no | rejected | rejected, 0 |
| H5 treatment beats control everywhere | yes (4/4 campaigns) | skipped (no SQL given) | confirmed, wrote its own SQL |

LLM column — `qwen3.8-27b-noreason`. Evaluated with `overnight eval --runs 3`, every run in
a fresh folder:

| Eval (3 runs) | Correct | Status | Tokens per run | Time per run |
|---|---|---|---|---|
| 2026-10-30, before the fix | 0/15 | 3× `partial` | 55–57k | 187–297 s |
| 2026-10-30, after | **15/15** | 3× `ok` | 49–65k | 218–384 s |

Before, analyze failed the same way every time: the repair of a broken JSON answer landed on
the last turn and was lost. After, one run again got corrupted JSON from the model
(`"sources": ["S": [], ...`) — the repair kicked in and the run finished `ok`.
Details: [first eval postmortem](docs/postmortems/2026-10-30-first-eval.md) and
[first runs postmortem](docs/postmortems/2026-10-28-collect-retry-loop.md).

Time is dominated by the provider generating each stage's final JSON, not by tools. Three
runs on one model and one dataset are not a benchmark yet: the next step is a regression
check in CI, see [ROADMAP.md](ROADMAP.md).

The offline policy is a deterministic stand-in (not an LLM) so CI exercises the whole
pipeline.

### Development

```bash
uv run ruff check . && uv run mypy && uv run pytest -q
```

How this was built with AI assistance, and what was decided or reviewed by hand:
[AI_WORKFLOW.md](AI_WORKFLOW.md).

### Known limits

* The SQL guard is lexical; the read-only connection is the real backstop. It is not an
  OS-level sandbox.
* Wall-clock limits are checked between calls, so one slow HTTP call is bounded only by
  the client timeout (120 s).
* Wiki search is plain substring search; no embeddings yet.

### License

MIT
