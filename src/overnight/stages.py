"""Stage contracts and roles. Collect does not analyze, synthesize adds no facts,
critique only checks. Each stage runs in a fresh context."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel


class Claim(BaseModel):
    text: str
    sources: list[str] = []  # tool-call ids like "S3"
    value: float | None = None  # the key number, if any; must appear in a cited source


class CollectOut(BaseModel):
    facts: list[Claim]


class HypothesisResult(BaseModel):
    id: str
    statement: str
    status: Literal["confirmed", "rejected", "inconclusive"]
    evidence: list[Claim]


class AnalyzeOut(BaseModel):
    hypotheses: list[HypothesisResult]


class Section(BaseModel):
    title: str
    bullets: list[Claim]


class SynthesizeOut(BaseModel):
    headline: str
    sections: list[Section]


class CritiqueOut(BaseModel):
    verdict: Literal["accept", "revise", "reject"]
    issues: list[str] = []


RULES = """Rules:
- Every claim cites the source ids (S1, S2, ...) returned by the tools it relies on.
- A number in a claim goes into "value" and must appear in a cited source.
- Never invent numbers and never do arithmetic in your head: compute with SQL.
- Final answer: ONE JSON object matching the contract, nothing else."""


@dataclass(frozen=True)
class Stage:
    name: str
    role: str
    tools: list[str]
    schema: type[BaseModel]
    needs: list[str]

    def system(self) -> str:
        contract = json.dumps(self.schema.model_json_schema())
        return f"STAGE: {self.name}\n{self.role}\n{RULES}\nContract: {contract}"

    def user(self, today: str, inputs: dict[str, Any]) -> str:
        return f"Today is {today}.\n<input>\n{json.dumps(inputs, ensure_ascii=False)}\n</input>"


STAGES = [
    Stage("collect", "You are the collector. Gather the morning context: tasks (especially "
          "overdue), wiki pages, warehouse volumes. Do NOT analyze or judge.",
          ["list_tasks", "list_wiki_pages", "search_wiki", "read_wiki", "run_sql"], CollectOut, []),
    Stage("analyze", "You are the analyst. Check each hypothesis in the input with read-only "
          "SQL and mark it confirmed, rejected or inconclusive. Use the wiki for definitions.",
          ["list_wiki_pages", "search_wiki", "read_wiki", "run_sql"], AnalyzeOut,
          ["collect", "hypotheses"]),
    Stage("synthesize", "You are the editor. Turn the input into a short morning report. "
          "Reuse claims only: rephrase, group, prioritize. Add NO new facts or sources.",
          [], SynthesizeOut, ["collect", "analyze"]),
    Stage("critique", "You are the reviewer. Check the report against its inputs: unsupported "
          "claims, wrong numbers, guesses stated as facts. Verdict: accept, revise or reject.",
          [], CritiqueOut, ["collect", "analyze", "synthesize"]),
]
