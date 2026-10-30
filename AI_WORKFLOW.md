# How this project was built with AI

**English** · [Русский](AI_WORKFLOW.ru.md)

I build with an AI pair (Claude). This file says what the AI did and what I did, so the
repository can be judged for what it is.

## Who did what

| | Me | AI |
|---|---|---|
| Problem, scope, architecture | ✅ | |
| Data sources and the agent's workflow | ✅ | |
| Guardrails to have: budgets, read-only, single writer | ✅ | |
| Writing code, tests, docs | review, accept or reject | ✅ most of it |
| Real model runs, Docker build | ✅ on my machine | reads the artifacts, finds root causes |
| Commits, branches, PRs, merges | ✅ every one | drafts commit text |

## What I decided

* **Architecture — carried over from an agent I built and run in production at work.**
  Narrow stages instead of one big prompt, a deterministic orchestrator that owns the run,
  read-only tools, one writer for notes and memory, gates in code instead of trust in the
  model. These are lessons from operating that agent, not suggestions taken from the AI.
  Clean room: no code, prompts, data or names from that project are here.
* **Data sources and workflow.** The same set an analyst really works with: task tracker,
  team wiki, warehouse, Obsidian. The workflow is the analyst's morning: collect context →
  check hypotheses about the data → short report with sources.
* **Hard spend limits before the first real run.** From the work agent I know an
  unattended agent can burn a whole key overnight. So: tokens per run, per call, and a
  lifetime cap for the key — in code, not in a prompt.
* **Simplicity over structure.** The first AI version had 18 files and ~1400 lines of
  single-use abstractions. AI tends to over-engineer, and a reviewer should be able to
  read the repo in one sitting, so I asked for a simplification pass: 12 files, ~900 lines,
  same tests green.
* **Process.** I run every real model run and the Docker build myself; the AI analyses the
  artifacts. I write every commit message, every change goes through a branch and a PR with
  green CI. Docs are bilingual (Russian first, then English).
* **Safety of the public repo.** After publishing I had the whole git history
  audited for keys, personal data and anything from work.

## What the AI generated

The implementation of all modules, the tests, CI, the Dockerfile, the synthetic data
generator with planted defects, the docs and postmortems, and the root-cause analysis of
each failed run.

## Where my review changed the outcome

* **Over-engineered first version** → simplified (see above).
* **A wrong diagnosis by the AI.** During the first eval the AI looked at the run folder
  mid-run, decided the run had been killed and wrote "uncounted tokens" into the
  postmortem. I saw the terminal was still running. The postmortem was corrected; the
  spend-per-call fix stayed, as a real gap that simply did not trigger
  ([postmortem](docs/postmortems/2026-10-30-first-eval.md)).
* **Budget first.** The lifetime token cap existed before any real run, so every failure
  later cost cents, not the key.

The parts I know best and can walk through line by line: the quality gates (`gates.py`)
and the spend limits (`cli.py`, `Metered`, `Budget`).

## Review log

Who found it: **me**, **AI**, or a **real run** I executed.

| Date | Finding | Found by | Where | Action |
|---|---|---|---|---|
| 2026-10-27 | first version over-structured: 18 files, ~1400 lines, single-use classes | me | `src/` | simplification pass: 12 files, ~900 lines, same tests green |
| 2026-10-27 | uv picked a pre-release Python 3.15 | AI | `.python-version` | pinned 3.12 |
| 2026-10-28 | model kept retrying `run_sql` after its quota was used up, collect never answered | real run | `agent.py` | tools removed once their quota is gone — [postmortem](docs/postmortems/2026-10-28-collect-retry-loop.md) |
| 2026-10-29 | stages re-read the same pages until the turn limit | real run | `tools.py`, `agent.py` | identical calls not re-run, `max_turns` 12 → 8 |
| 2026-10-29 | gate rejected true counts that were list lengths | real run | `gates.py` | list length counts as a traceable number |
| 2026-10-29 | lifetime token counter lived under `--root`: a fresh `--root` bypassed the key cap | AI | `cli.py` | one counter in `./state/spend.json` |
| 2026-10-29 | audit of the whole git history for keys, personal and work data | me | repo | nothing found |
| 2026-10-30 | analyze's JSON repair landed on the last turn and was lost (3/3 runs) | real run | `agent.py` | repair always gets its own turn; SQL quota 5 → 8 — [postmortem](docs/postmortems/2026-10-30-first-eval.md) |
| 2026-10-30 | AI misread a running eval as killed and wrote a wrong postmortem | me | postmortem | corrected; spend now saved after every call anyway |

## Rules I follow when working with AI here

* No change reaches `main` without green `ruff`, `mypy --strict`, `pytest` and Docker build.
* Any guardrail has a test that tries to break it.
* I write the commit messages; commits made together with AI are signed `Max + Agent`.
* AI conclusions about real runs are checked against what actually happened.
