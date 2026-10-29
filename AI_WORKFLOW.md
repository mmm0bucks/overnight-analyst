# How this project was built with AI

**English** · [Русский](AI_WORKFLOW.ru.md)

I build with an AI pair. This file says, honestly, what the AI did and what I did,
so the repository can be judged for what it is.

## Tools

* **Claude (Cowork / Claude Code)** — wrote most of the code, tests and docs from my
  design brief, ran the test suite, fixed failures.

## What I decided

* The problem and the scope: an overnight analyst agent, read-only, publishing to Obsidian.
* The architecture, carried over as *ideas* from an agent I built and operate at work:
  staged pipeline with narrow roles, deterministic orchestrator, single-writer publisher,
  traceable sources, gates in code, budgets. (Clean room: nothing copied from that project.)
* Public stand-ins: local JSON tracker / markdown wiki / DuckDB with synthetic data.
* Hard constraints: no write tools, cheap model + strict budgets, offline mode for CI.

## What the AI generated

* Initial implementation of all modules in `src/overnight/`, the tests, CI and docs.
* The synthetic data generator and the planted defects.

## Review log

What was checked, found and changed by hand. Each entry: what, where, why.

| Date | Finding | Where | Action |
|---|---|---|---|
| 2026-10-27 | uv picked a pre-release Python 3.15 interpreter | `.python-version` | pinned 3.12 |
| 2026-10-27 | virtualenv created inside a synced/mounted folder was very slow | dev setup | venv moved outside the repo (`UV_PROJECT_ENVIRONMENT`) |
| 2026-10-27 | first version over-structured: 18 files, ~1400 lines, single-use classes (config, budget, schemas, tracker protocol) | `src/` | asked for a simplification pass: merged into 12 files, ~900 lines, same 48 tests green |
| 2026-10-28 | first real run failed: model kept retrying `run_sql` after its quota was used up, collect never answered | `agent.py` | root cause + fix in [postmortem](docs/postmortems/2026-10-28-collect-retry-loop.md) |
| 2026-10-29 | run 2 correct but wasteful: stages re-read the same pages until the turn limit | `tools.py`, `agent.py` | dedupe identical calls per stage, `max_turns` 12 → 8 |
| 2026-10-29 | run 3 `partial`: gate rejected true counts that were list lengths | `gates.py` | list length counts as a traceable number |
| 2026-10-29 | lifetime token counter lived under `--root`: a fresh `--root` bypassed the key cap | `cli.py` | counter moved to `./state/spend.json`, test updated |
| | _next entries: my own review of each module_ | | |

## Rules I follow when working with AI here

* No change lands without passing `ruff`, `mypy --strict` and `pytest`.
* Any guardrail must have a test that tries to break it.
* I write the commit messages; commits made together with AI are signed `Max + Agent`.
