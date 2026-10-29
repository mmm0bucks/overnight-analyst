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

Колонка LLM: `qwen3.8-27b-noreason`, два чистых прогона — оба раза 5 из 5, все числа
совпадают с заложенными ошибками.

| Прогон | Токены | Вызовы модели | Время |
|---|---|---|---|
| 2026-10-28, до исправления циклов | 98,7 тыс. | 26 | 167 с |
| 2026-10-29, после | 55,3 тыс. (−44%) | 18 | 577 с |

Время уходит в основном на то, что провайдер генерирует итоговый JSON этапа (до ~110 с на
вызов), а не на инструменты. Два прогона — это случай, а не оценка; повторные прогоны —
следующий шаг, см. [ROADMAP.ru.md](ROADMAP.ru.md) и
[разбор инцидента](docs/postmortems/2026-10-28-collect-retry-loop.ru.md) о том, что пошло
не так сначала.

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

LLM column: `qwen3.8-27b-noreason`, two clean runs — 5/5 correct both times, every count
matches the planted defects.

| Run | Tokens | Model calls | Time |
|---|---|---|---|
| 2026-10-28, before the loop fixes | 98.7k | 26 | 167 s |
| 2026-10-29, after | 55.3k (−44%) | 18 | 577 s |

Time is dominated by the provider generating the final JSON of each stage (up to ~110 s per
call), not by tools. Two runs are an anecdote, not an evaluation — repeated runs are the next
milestone, see [ROADMAP.md](ROADMAP.md) and the
[postmortem](docs/postmortems/2026-10-28-collect-retry-loop.md) for what went wrong first.

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
