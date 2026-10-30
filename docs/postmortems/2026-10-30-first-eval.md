# 2026-10-30 — first eval: the JSON repair turn was lost

**English** · [Русский](2026-10-30-first-eval.ru.md)

**Impact.** In the first `overnight eval --runs 3` analyze failed in runs 1 and 2 the same
way, so those runs ended `partial` with no hypothesis results.

**What happened.** Analyze used its 5 SQL queries on the first two turns (4 planted checks
+ its own query for H5), then asked for `run_sql` several more times although it was no
longer offered. On the last turn it answered with broken JSON. The repair message was sent,
but the loop had no turn left, so the stage failed. Reproduced in 2 of 2 runs.

**Root causes.** A repair that lands on the last turn had no turn to happen in. A quota of
5 queries is too tight for 5 hypotheses plus one check.

**Fixes.**
* A repair always gets its own turn (`agent.run_stage`).
  Test: `test_bad_json_on_last_turn_still_gets_a_repair`.
* SQL quota per stage 5 → 8.

**Found while investigating, fixed too.** The key's spend counter was written once, at the
end of a run, so a run killed half-way would not be counted. (It did not happen here: I
first misread the still-running eval as an interrupted one.) `Metered` now saves spend
after **every** model call. Test: `test_spend_is_saved_after_every_call`.

## Re-run after the fix

3 runs, 3× `ok`, **15/15** hypotheses right, 49–65k tokens per run. In one run collect
got corrupted JSON from the model (`"sources": ["S": [], "sources": ["S7"] ...`) — the repair
turn caught it and the run finished `ok`. The `near` field in the `repair` event (added
after the first eval) is what made this visible.
