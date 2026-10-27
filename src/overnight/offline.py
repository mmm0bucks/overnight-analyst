"""Deterministic rule-based stand-in for an LLM.

NOT an LLM and not "AI": a fixed policy that speaks the same protocol (tool calls ->
final JSON). It exists so the whole pipeline, its guards and its gates run in CI and
in a zero-cost demo. Real runs use ``HttpLLM``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from overnight.llm import LLMResponse, Message, ToolCall

VOLUME_SQL = (
    "SELECT c.campaign_id, count(*) AS contacts FROM contacts c "
    "GROUP BY 1 ORDER BY 1"
)


class OfflinePolicy:
    def __init__(self) -> None:
        self._n = 0

    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse:
        stage = re.search(r"STAGE: (\w+)", messages[0]["content"])
        name = stage.group(1) if stage else ""
        inputs = _inputs(messages[1]["content"])
        results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
        handler = getattr(self, f"_{name}")
        return handler(inputs, results)  # type: ignore[no-any-return]

    def _call(self, name: str, **args: Any) -> ToolCall:
        self._n += 1
        return ToolCall(id=f"off{self._n}", name=name, arguments=args)

    # -- stages ---------------------------------------------------------------
    def _collect(self, inputs: dict[str, Any], results: list[dict[str, Any]]) -> LLMResponse:
        if not results:
            return LLMResponse(tool_calls=[
                self._call("list_tasks"),
                self._call("list_wiki_pages"),
                self._call("run_sql", query=VOLUME_SQL, purpose="contacts per campaign"),
            ])
        tasks, pages, volumes = results
        facts: list[dict[str, Any]] = []
        overdue = [t for t in tasks["result"] if t["overdue"]]
        facts.append({"text": f"{len(overdue)} task(s) overdue",
                      "sources": [tasks["source"]], "value": None})
        facts += [{"text": f"Overdue: {t['id']} '{t['title']}' (due {t['due']})",
                   "sources": [tasks["source"]], "value": None} for t in overdue]
        facts.append({"text": f"Wiki has {len(pages['result'])} pages",
                      "sources": [pages["source"]], "value": None})
        for cid, n in volumes["result"]["rows"]:
            facts.append({"text": f"Campaign {cid}: {n} contacts",
                          "sources": [volumes["source"]], "value": n})
        return _final({"facts": facts, "open_questions": []})

    def _analyze(self, inputs: dict[str, Any], results: list[dict[str, Any]]) -> LLMResponse:
        hyps = inputs.get("hypotheses", [])
        if not results:
            return LLMResponse(tool_calls=[
                self._call("run_sql", query=h["suggested_sql"], purpose=h["statement"])
                for h in hyps if h.get("suggested_sql")
            ])
        out = []
        checkable = [h for h in hyps if h.get("suggested_sql")]
        for h, r in zip(checkable, results, strict=True):
            if "error" in r:
                out.append({"id": h["id"], "statement": h["statement"],
                            "status": "inconclusive", "evidence": []})
                continue
            rows = r["result"]["rows"]
            n = rows[0][0] if rows else 0
            out.append({
                "id": h["id"], "statement": h["statement"],
                "status": "confirmed" if n and n > 0 else "rejected",
                "evidence": [{"text": f"{h['id']}: {n} offending rows",
                              "sources": [r["source"]], "value": n}],
            })
        return _final({"hypotheses": out, "notes": []})

    def _synthesize(self, inputs: dict[str, Any], results: list[dict[str, Any]]) -> LLMResponse:
        analyze = inputs.get("analyze") or {"hypotheses": []}
        collect = inputs.get("collect") or {"facts": []}
        confirmed = [h for h in analyze["hypotheses"] if h["status"] == "confirmed"]
        sections = [
            {"title": "Data issues found overnight",
             "bullets": [{"text": f"{h['statement']}: {h['evidence'][0]['value']:g} rows",
                          "sources": h["evidence"][0]["sources"],
                          "value": h["evidence"][0]["value"]} for h in confirmed]},
            {"title": "Tasks", "bullets": [f for f in collect["facts"] if "task" in f["text"]
                                           or "Overdue" in f["text"]]},
            {"title": "Warehouse volumes",
             "bullets": [f for f in collect["facts"] if f["text"].startswith("Campaign")]},
        ]
        headline = f"{len(confirmed)} data issue(s) confirmed overnight"
        return _final({"headline": headline, "sections": sections})

    def _critique(self, inputs: dict[str, Any], results: list[dict[str, Any]]) -> LLMResponse:
        report = inputs.get("synthesize") or {"sections": []}
        issues = [f"unsourced claim: {b['text']}" for s in report["sections"]
                  for b in s["bullets"] if not b.get("sources")]
        return _final({"verdict": "revise" if issues else "accept", "issues": issues})


def _inputs(user: str) -> dict[str, Any]:
    m = re.search(r"<input>\n(.*)\n</input>", user, re.S)
    return json.loads(m.group(1)) if m else {}


def _final(obj: dict[str, Any]) -> LLMResponse:
    return LLMResponse(content=json.dumps(obj, ensure_ascii=False))
