"""Deterministic rule-based stand-in for an LLM. NOT an LLM: a fixed policy speaking the
same protocol (tool calls -> final JSON), so CI and the free demo exercise the whole
pipeline, its guards and its gates. Real runs use ``HttpLLM``."""

from __future__ import annotations

import json
import re
from typing import Any

from overnight.llm import LLMResponse, ToolCall

VOLUME_SQL = "SELECT campaign_id, count(*) AS contacts FROM contacts GROUP BY 1 ORDER BY 1"


def _claim(text: str, source: str, value: Any = None) -> dict[str, Any]:
    return {"text": text, "sources": [source], "value": value}


def _final(obj: dict[str, Any]) -> LLMResponse:
    return LLMResponse(content=json.dumps(obj))


class OfflinePolicy:
    def complete(self, messages: list[dict[str, Any]],
                 tools: list[dict[str, Any]]) -> LLMResponse:
        stage = re.search(r"STAGE: (\w+)", messages[0]["content"])
        inputs = json.loads(messages[1]["content"].split("<input>")[1].split("</input>")[0])
        results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
        return getattr(self, stage.group(1) if stage else "")(inputs, results)  # type: ignore[no-any-return]

    def collect(self, inputs: dict[str, Any], results: list[dict[str, Any]]) -> LLMResponse:
        if not results:
            return LLMResponse(tool_calls=[
                ToolCall("c1", "list_tasks", {}), ToolCall("c2", "list_wiki_pages", {}),
                ToolCall("c3", "run_sql", {"query": VOLUME_SQL, "purpose": "volumes"})])
        tasks, pages, volumes = results
        overdue = [t for t in tasks["result"] if t["overdue"]]
        facts = [_claim(f"{len(overdue)} task(s) overdue", tasks["source"])]
        facts += [_claim(f"Overdue: {t['id']} {t['title']} (due {t['due']})", tasks["source"])
                  for t in overdue]
        facts += [_claim(f"Wiki has {len(pages['result'])} pages", pages["source"])]
        facts += [_claim(f"Campaign {cid}: {n} contacts", volumes["source"], n)
                  for cid, n in volumes["result"]["rows"]]
        return _final({"facts": facts})

    def analyze(self, inputs: dict[str, Any], results: list[dict[str, Any]]) -> LLMResponse:
        hyps = [h for h in inputs["hypotheses"] if h.get("suggested_sql")]
        if not results:
            return LLMResponse(tool_calls=[
                ToolCall(f"a{i}", "run_sql", {"query": h["suggested_sql"],
                                               "purpose": h["statement"]})
                for i, h in enumerate(hyps)])
        out = []
        for h, r in zip(hyps, results, strict=True):
            n = r["result"]["rows"][0][0] if "result" in r else None
            out.append({"id": h["id"], "statement": h["statement"],
                        "status": "inconclusive" if n is None else
                        "confirmed" if n > 0 else "rejected",
                        "evidence": [] if n is None else
                        [_claim(f"{h['id']}: {n} offending rows", r["source"], n)]})
        return _final({"hypotheses": out})

    def synthesize(self, inputs: dict[str, Any], results: list[dict[str, Any]]) -> LLMResponse:
        facts = inputs["collect"]["facts"]
        issues = [{**h["evidence"][0], "text": f"{h['statement']}: {h['evidence'][0]['value']:g}"
                   " rows"} for h in inputs.get("analyze", {}).get("hypotheses", [])
                  if h["status"] == "confirmed"]
        return _final({"headline": f"{len(issues)} data issue(s) confirmed overnight",
                       "sections": [
                           {"title": "Data issues", "bullets": issues},
                           {"title": "Tasks", "bullets": [f for f in facts if "task" in
                                                          f["text"] or "Overdue" in f["text"]]},
                           {"title": "Warehouse volumes", "bullets": [
                               f for f in facts if f["text"].startswith("Campaign")]}]})

    def critique(self, inputs: dict[str, Any], results: list[dict[str, Any]]) -> LLMResponse:
        issues = [f"unsourced: {b['text']}" for s in inputs["synthesize"]["sections"]
                  for b in s["bullets"] if not b["sources"]]
        return _final({"verdict": "revise" if issues else "accept", "issues": issues})
