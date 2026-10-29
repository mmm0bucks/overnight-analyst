# 0001 — A deterministic orchestrator around LLM stages

**English** · [Русский](0001-deterministic-orchestrator.ru.md)

**Status:** accepted

**Context.** An unattended overnight job fails in boring ways: network down at start,
a stage hangs, tokens run away, the model returns malformed JSON or says "done" when it
is not. A free-running agent loop has no reliable place to handle any of that.

**Decision.** Plain Python owns the run: preflight, stage order, budgets, timeouts,
artifacts, gates and publishing. The LLM is called inside narrow stages with a fixed
contract and returns data, not control flow.

**Consequences.** Less "autonomy" per call, much more predictable runs. A failed stage
degrades the run to `partial` instead of killing the night. Every stage leaves an
artifact, so a failure can be debugged from files alone.
