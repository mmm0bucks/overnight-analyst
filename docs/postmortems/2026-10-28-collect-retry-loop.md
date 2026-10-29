# 2026-10-28 — first real run: collect stuck retrying a refused tool

**English** · [Русский](2026-10-28-collect-retry-loop.ru.md)

**Impact.** The first run against a real model (`qwen3.8-27b-noreason`) failed: the collect
stage hit its 12-turn limit with no answer, so the night produced only a `failed` note.
Cost: 36.7k tokens, 61 s, 25 tool calls (15 of them refused).

**What happened.** Collect used its 5 SQL queries in 4 turns (one of them was already
analysis — counting duplicate responses — which is not its job). Every following turn
the model asked for 2 more queries, got `SQL quota ... is used up` back, and asked again.
It never switched to writing the final JSON.

**Root cause.** The loop kept offering `run_sql` after its quota was gone, and never
forced an answer. A refused tool in the context is not enough of a signal for this model.

**Fix.** `agent.run_stage` now offers only tools that can still run (`Toolbox.available`),
tells the model once when the tool set shrinks, and gives no tools at all on the last turn.
Test: `test_stage_finishes_when_sql_quota_is_used_up`.

**What worked.** Budget and turn limits stopped the loop; preflight, the failed-run note
and the spend counter behaved as designed. The SQL guard accepted every query the model
wrote (all read-only).

**Open.** Collect drifting into analysis is a prompt issue; watch it on the next run.

## Follow-up: runs 2 and 3

* **Run 2 — `ok`, 5/5 hypotheses right.** But every stage still used all 12 turns: after
  the SQL quota was gone the model re-read the same wiki pages until the last, tool-less
  turn. 98.7k tokens for work that needs maybe a third of that.
  *Fix:* an identical call within a stage is not run again — the model is pointed to the
  source it already has; `max_turns` 12 → 8.
* **Run 3 — `partial`.** `numbers_traceable` failed on "3 wiki pages" and "15 duplicate
  rows": true numbers, but they are the *length* of a tool result, not a value inside it.
  A false positive of the gate, not a model error.
  *Fix:* the length of every list in a source counts as one of its numbers.
* Run 3 also had nothing to analyze: run 2 had closed every hypothesis in the backlog.
  Correct behaviour; repeated evaluation runs need a fresh `--root`.

## Follow-up: run 4 (fresh `--root`)

* `ok`, 5/5 again, 55.3k tokens (−44% vs run 2), 18 model calls.
* The model still asks for `run_sql` after it is no longer offered; those calls are refused
  and the stage answers on its last turn. Acceptable for now.
* **Bug found while checking spend:** the lifetime token counter lived under `--root`, so a
  fresh `--root` started from zero and bypassed the key's cap. *Fix:* the counter is
  `./state/spend.json` where you run from, shared by every `--root`.
