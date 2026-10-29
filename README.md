# overnight-analyst

[![ci](https://github.com/mmm0bucks/overnight-analyst/actions/workflows/ci.yml/badge.svg)](https://github.com/mmm0bucks/overnight-analyst/actions/workflows/ci.yml)

An LLM agent that does a data analyst's morning homework **overnight**: it reads the task
tracker and the team wiki, checks data-quality hypotheses against the warehouse with
**read-only** SQL, and publishes a short report — where every claim cites its source — into
an Obsidian vault.

The interesting part is not the LLM. It is the harness around it: what the model is
**not** allowed to do, and what plain code checks after it.

> Clean-room project on synthetic data. It reuses design ideas from an internal tool I
> built at work; no code, prompts, data or names from that project are included.

## Quickstart (no API key needed)

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

## How it works

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

## Guardrails

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

## Evaluation

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

## Development

```bash
uv run ruff check . && uv run mypy && uv run pytest -q
```

How this was built with AI assistance, and what was decided or reviewed by hand:
[AI_WORKFLOW.md](AI_WORKFLOW.md).

## Known limits

* The SQL guard is lexical; the read-only connection is the real backstop. It is not an
  OS-level sandbox.
* Wall-clock limits are checked between calls, so one slow HTTP call is bounded only by
  the client timeout (120 s).
* Wiki search is plain substring search; no embeddings yet.

## License

MIT
