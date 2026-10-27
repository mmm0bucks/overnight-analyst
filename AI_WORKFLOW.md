# How this project was built with AI

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
| | _next entries: my own review of each module_ | | |

## Rules I follow when working with AI here

* No change lands without passing `ruff`, `mypy --strict` and `pytest`.
* Any guardrail must have a test that tries to break it.
* Commits generated with AI carry a `Co-Authored-By` trailer.
