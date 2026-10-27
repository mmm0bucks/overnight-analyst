"""Stage definitions: role prompt, allowed tools, output contract, input builder.

Roles are deliberately narrow: collect does not analyze, synthesize adds no facts,
critique only checks. Each stage runs in a fresh context.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from overnight.schemas import AnalyzeOut, CollectOut, CritiqueOut, SynthesizeOut

COMMON = """
Rules:
- Every claim must cite the source ids (S1, S2, ...) returned by the tools it relies on.
- If a claim contains a number, put that exact number into "value"; it must appear in a cited source.
- Never invent numbers. Do not do arithmetic in your head: compute it with SQL instead.
- Separate facts from guesses. If you are not sure, say so.
- Final answer: ONE JSON object matching the contract, nothing else.
"""


@dataclass(frozen=True)
class Stage:
    name: str
    role: str
    tools: list[str]
    schema: type[BaseModel]
    contract: str
    needs: list[str]  # artifacts of previous stages this stage reads

    def system(self) -> str:
        return f"STAGE: {self.name}\n{self.role}\n{COMMON}\nContract:\n{self.contract}"

    def user(self, today: str, inputs: dict[str, Any]) -> str:
        return (f"Today is {today}.\n<input>\n"
                f"{json.dumps(inputs, ensure_ascii=False, indent=1, default=str)}\n</input>")


def _contract(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(), ensure_ascii=False)


STAGES: list[Stage] = [
    Stage(
        name="collect",
        role="You are the collector. Gather the morning context: tasks (especially overdue), "
             "relevant wiki pages, and basic warehouse volumes. Do NOT analyze or judge.",
        tools=["list_tasks", "get_task", "list_wiki_pages", "read_wiki", "search_wiki",
               "run_sql"],
        schema=CollectOut, contract=_contract(CollectOut), needs=[],
    ),
    Stage(
        name="analyze",
        role="You are the analyst. For each hypothesis in the input, check it against the "
             "warehouse with read-only SQL and decide: confirmed, rejected or inconclusive. "
             "Use the wiki for definitions. One hypothesis = at least one query.",
        tools=["read_wiki", "search_wiki", "run_sql"],
        schema=AnalyzeOut, contract=_contract(AnalyzeOut), needs=["collect", "hypotheses"],
    ),
    Stage(
        name="synthesize",
        role="You are the editor. Turn the collected facts and analysis into a short morning "
             "report. You may only reuse claims from the input: rephrase, group, prioritize. "
             "Do NOT add new facts, numbers or sources.",
        tools=[], schema=SynthesizeOut, contract=_contract(SynthesizeOut),
        needs=["collect", "analyze"],
    ),
    Stage(
        name="critique",
        role="You are the reviewer. Check the report against the facts it was built from: "
             "unsupported claims, wrong numbers, hypotheses stated as facts, missing caveats. "
             "Verdict: accept, revise (usable with caveats) or reject.",
        tools=[], schema=CritiqueOut, contract=_contract(CritiqueOut),
        needs=["collect", "analyze", "synthesize"],
    ),
]

BY_NAME: dict[str, Stage] = {s.name: s for s in STAGES}
InputBuilder = Callable[[str], dict[str, Any]]
