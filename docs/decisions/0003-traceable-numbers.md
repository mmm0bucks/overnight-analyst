# 0003 — Every number must be traceable to tool output

**Status:** accepted

**Context.** LLMs are unreliable at arithmetic and happily produce plausible numbers.

**Decision.** Every tool call is registered as a source `S<n>`. Claims carry `sources`
and an optional numeric `value`. A gate checks that the value literally occurs in the
cited sources' raw results; prompts tell the model to compute with SQL, not in its head.

**Consequences.** Invented or miscalculated numbers fail the run's gates. Derived
numbers must come from a query, which also leaves an audit trail.
