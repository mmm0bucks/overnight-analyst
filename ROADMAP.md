# Roadmap

Each item is planned as a separate pull request.

- [x] Walking skeleton: 4 stages, read-only tools, gates, publisher, offline policy, CI
- [ ] Real LLM run on the demo; fill the evaluation table with results, tokens, cost, latency
- [ ] Eval harness: N runs per model, per-hypothesis accuracy, regression check in CI (recorded)
- [ ] GitHub Issues adapter for the tracker (read-only)
- [ ] Per-stage wall-clock timeout (run stages in a subprocess, kill on timeout)
- [ ] Code sandbox for analysis scripts: plan → hash-confirmed execution → AST/runtime guards
- [ ] Hybrid retrieval (BM25 + embeddings) over the wiki and past reports
- [ ] Obsidian skill for Claude: write notes that follow the vault's conventions
- [ ] Dockerfile and scheduled run (cron / Task Scheduler) docs
- [ ] Morning delivery to Telegram (direct API call, exit code = result)
