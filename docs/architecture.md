# Architecture

```
overnight run
  │
  ├─ preflight            workspace complete? LLM endpoint reachable? → else publish a "failed" note
  │
  ├─ stage: collect       tools: tracker, wiki, read-only SQL      → runs/<id>/collect.json
  ├─ stage: analyze       tools: wiki, read-only SQL               → runs/<id>/analyze.json
  ├─ stage: synthesize    no tools, may only reuse claims          → runs/<id>/synthesize.json
  ├─ stage: critique      no tools, reviews the report             → runs/<id>/critique.json
  │      (each stage: fresh context, hard budget check before every LLM/tool call)
  │
  ├─ finalize             deterministic gates                       → runs/<id>/finalize.json
  │
  └─ publisher            the ONLY writer of vault/ and state/  (atomic, backed up, redacted)
         ├─ vault/Overnight/Reports/<date> <run_id>.md
         ├─ vault/Overnight/Hypotheses.md   (managed block, your text around it is kept)
         └─ state/hypotheses.json, state/runs.json
```

## Components

| Module | Responsibility |
|---|---|
| `orchestrator.py` | ordering, failure isolation, artifacts, events log |
| `agent.py` | bounded tool-calling loop for one stage; one repair attempt for bad JSON |
| `stages.py` | role prompts, allowed tools, output contracts |
| `tools.py` | read-only tools; every call becomes a numbered source `S1, S2, ...` |
| `sqlguard.py` | lexical SQL validator (layer 1); DuckDB `read_only=True` is layer 2 |
| `gates.py` | quality gates: sourcing, number traceability, no new facts in synthesis, critique, budget |
| `publisher.py` | single writer: atomic writes, backups, managed blocks, secret redaction |
| `llm.py` | OpenAI-compatible HTTP client with retry policy; scripted client for tests |
| `offline.py` | deterministic rule-based policy for CI and zero-cost demo (not an LLM) |

## Trust boundaries

* The model can only **read**: there is no write tool. Writing is done by the publisher,
  after the gates, by plain code.
* SQL is single-statement, read-only, row-capped and quota-limited per stage; file-reading
  table functions are blocked; the connection itself is read-only.
* A run that fails its gates is still published (so the human sees it), but it is marked
  `partial` and **does not update** the hypothesis backlog.
