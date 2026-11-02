# Roadmap

**English** · [Русский](ROADMAP.ru.md)

Each item is planned as a separate pull request.

- [x] Walking skeleton: 4 stages, read-only tools, gates, publisher, offline policy, CI
- [x] Real LLM run on the demo; fill the evaluation table with results, tokens, latency
- [x] Eval harness: N fresh runs, per-hypothesis accuracy against `demo/expected.json`
- [ ] Regression check in CI on recorded model answers
- [ ] GitHub Issues adapter for the tracker (read-only)
- [x] Prompt-injection red-team set: 5 attacks, attempt vs success, spotlighting, link gate
- [x] Eval v2: hard and negative hypotheses, pass^k, constant-answer baselines, null-agent check
- [x] LLM judge calibrated on variants with known labels (Cohen's kappa)
- [ ] More judge variants and a held-out set
- [ ] FastAPI service + ADR "why not LangGraph"
- [ ] MCP server for the read-only tools
- [ ] OpenTelemetry GenAI trace export (view in Phoenix)
- [ ] Per-stage wall-clock timeout (run stages in a subprocess, kill on timeout)
- [ ] Code sandbox for analysis scripts: plan → hash-confirmed execution → AST/runtime guards
- [x] Hybrid wiki search: BM25 + bge-m3 embeddings in Qdrant + RRF, recall@k / MRR eval
- [ ] Reranker and search over past reports
- [ ] Obsidian skill for Claude: write notes that follow the vault's conventions
- [x] Dockerfile, image built and smoke-run in CI
- [ ] Scheduled run (cron / Task Scheduler) docs
- [ ] Morning delivery to Telegram (direct API call, exit code = result)
