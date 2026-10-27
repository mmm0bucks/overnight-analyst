"""Quality gates run by plain code after the LLM stages. Code decides, not the model."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from overnight.stages import AnalyzeOut, Claim, CollectOut, CritiqueOut, SynthesizeOut
from overnight.tools import Source


@dataclass
class Gate:
    name: str
    passed: bool
    detail: str = ""


def claims(art: BaseModel) -> list[Claim]:
    if isinstance(art, CollectOut):
        return art.facts
    if isinstance(art, AnalyzeOut):
        return [c for h in art.hypotheses for c in h.evidence]
    if isinstance(art, SynthesizeOut):
        return [c for s in art.sections for c in s.bullets]
    return []


def numbers_in(obj: Any) -> set[float]:
    if isinstance(obj, bool):
        return set()
    if isinstance(obj, (int, float)):
        return {float(obj)}
    if isinstance(obj, str):
        return {float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", obj)}
    if isinstance(obj, dict):
        obj = list(obj.values())
    if isinstance(obj, list):
        return set().union(*map(numbers_in, obj))
    return set()


def run_gates(arts: dict[str, BaseModel], stage_errors: dict[str, str],
              sources: dict[str, Source]) -> list[Gate]:
    by_stage = {name: claims(a) for name, a in arts.items()}
    every = [c for cs in by_stage.values() for c in cs]

    def cited(c: Claim) -> set[float]:
        return set().union(*(numbers_in(sources[s].result) for s in c.sources if s in sources))

    unsourced = [c.text for c in every if not c.sources]
    unknown = sorted({s for c in every for s in c.sources} - sources.keys())
    untraceable = [f"{c.text} ({c.value})" for c in every if c.value is not None
                   and not any(math.isclose(c.value, n) for n in cited(c))]
    upstream = {s for st in ("collect", "analyze")
                for c in by_stage.get(st, []) for s in c.sources}
    new = sorted({s for c in by_stage.get("synthesize", []) for s in c.sources} - upstream)
    crit = arts.get("critique")
    verdict = crit.verdict if isinstance(crit, CritiqueOut) else "missing"
    return [
        Gate("all_stages_ok", not stage_errors, "; ".join(f"{k}: {v}" for k, v in
                                                          stage_errors.items())),
        Gate("every_claim_sourced", not unsourced, "; ".join(unsourced[:5])),
        Gate("sources_exist", not unknown, ", ".join(unknown)),
        Gate("numbers_traceable", not untraceable, "; ".join(untraceable[:5])),
        Gate("synthesis_adds_no_sources", not new, ", ".join(new)),
        Gate("critique_not_rejected", verdict in ("accept", "revise"), verdict),
    ]


def status(gates: list[Gate], arts: dict[str, BaseModel]) -> str:
    if "synthesize" not in arts:
        return "failed"
    return "ok" if all(g.passed for g in gates) else "partial"
