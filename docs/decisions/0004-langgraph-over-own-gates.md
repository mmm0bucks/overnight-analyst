# 0004 — LangGraph for routing, our own gates for truth

**English** · [Русский](0004-langgraph-over-own-gates.ru.md)

**Status:** accepted (2026-11-05). Extends [0001](0001-deterministic-orchestrator.md): code still
fixes the stage order, now as a graph.

**Context.** The plain orchestrator (0001) was simple and predictable but lacked three things:
a review-and-rewrite loop, a pause for human approval, and resuming a night after a crash.
Writing them ourselves means rebuilding state persistence and routing. The market points the
same way: on hh.ru (2026-11-03) LangGraph appears in 159 of 1,233 postings that mention LLM
(13%), LangChain in 189 (15%). Other agent frameworks are rare: LlamaIndex 68, CrewAI 24,
OpenAI Agents SDK 10, AutoGen 9, PydanticAI 1.

**Options considered.**

| Option | Why not |
|---|---|
| Keep the plain orchestrator | loop, pause and resume would be ours to write; not named in RU postings |
| LangChain `create_agent` | a ready model→tools loop hides the steps; stage contracts would live inside someone else's loop |
| CrewAI | role-based crews are not our problem; no token cap, opaque debugging |
| OpenAI Agents SDK, PydanticAI | no state persistence; rare in RU postings |
| LlamaIndex Workflows | stronger at document retrieval than at orchestration |

**Decision.** LangGraph owns the route only: stages are `StateGraph` nodes, and conditional
edges end the night early, send the report back for one rewrite, and pause before
publishing. Everything that decides whether the report is true stays plain code outside the
graph: stage contracts, gates (every number from a source, every claim cited), the budget,
read-only tools and the publisher. The model is called by our `HttpLLM`, without
`langchain-openai`. Graph state is plain JSON, saved to SQLite after every step.

**Consequences.**

* We got the rewrite loop (final "accept" in 2 of 3 runs, 1 of 3 before), the `--approve`
  pause, and `resume` after a crash without paying again for finished stages.
* Behaviour did not change: on the graph, 27/27 hypothesis checks at the same 66–71k tokens;
  an offline run takes 0.097 s with the graph and 0.098 s without it.
* Cost: `langgraph`, `langchain-core`, `langsmith` and the SQLite checkpointer as
  dependencies (`uv.lock` grew by about a thousand lines); a node restarts from the top on
  resume, so nothing with side effects runs before `interrupt()`.
* Checkpoints are save points, not guaranteed completion: a crashed run does not restart
  itself, `overnight resume` continues it.
* To drop LangGraph later, the nodes are plain functions with our contracts and can be called
  in a loop again, as in 0001.
