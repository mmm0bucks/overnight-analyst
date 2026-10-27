"""Deterministic quality gates, run after the LLM stages. Code decides, not the model."""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from overnight.schemas import AnalyzeOut, Claim, CollectOut, CritiqueOut, SynthesizeOut
from overnight.tools import SourceLog

NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass
class Gate:
    name: str
    passed: bool
    detail: str = ""


def claims_of(artifact: Any) -> Iterator[Claim]:
    if isinstance(artifact, CollectOut):
        yield from artifact.facts
    elif isinstance(artifact, AnalyzeOut):
        for h in artifact.hypotheses:
            yield from h.evidence
        yield from artifact.notes
    elif isinstance(artifact, SynthesizeOut):
        for s in artifact.sections:
            yield from s.bullets


def numbers_in(obj: Any) -> set[float]:
    out: set[float] = set()
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        out.update(float(x) for x in NUM_RE.findall(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            out |= numbers_in(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= numbers_in(v)
    return out


def run_gates(artifacts: dict[str, Any], stage_status: dict[str, str],
              sources: SourceLog, budget_error: str | None) -> list[Gate]:
    gates: list[Gate] = []
    failed = [s for s, st in stage_status.items() if st != "ok"]
    gates.append(Gate("all_stages_ok", not failed, ", ".join(failed)))

    all_claims = [(s, c) for s, a in artifacts.items() for c in claims_of(a)]
    unsourced = [c.text for _, c in all_claims if not c.sources]
    gates.append(Gate("every_claim_sourced", not unsourced, "; ".join(unsourced[:5])))

    unknown = sorted({sid for _, c in all_claims for sid in c.sources} - set(sources.sources))
    gates.append(Gate("sources_exist", not unknown, ", ".join(unknown)))

    untraceable = []
    for _, c in all_claims:
        if c.value is None:
            continue
        nums: set[float] = set()
        for sid in c.sources:
            if sid in sources.sources:
                nums |= numbers_in(sources.sources[sid].result)
        if not any(math.isclose(c.value, n, rel_tol=1e-9, abs_tol=1e-9) for n in nums):
            untraceable.append(f"{c.text} (value={c.value})")
    gates.append(Gate("numbers_traceable", not untraceable, "; ".join(untraceable[:5])))

    upstream = {sid for s, c in all_claims if s in ("collect", "analyze") for sid in c.sources}
    new = sorted({sid for s, c in all_claims if s == "synthesize" for sid in c.sources}
                 - upstream)
    gates.append(Gate("synthesis_adds_no_sources", not new, ", ".join(new)))

    crit = artifacts.get("critique")
    ok = isinstance(crit, CritiqueOut) and crit.verdict != "reject"
    detail = crit.verdict if isinstance(crit, CritiqueOut) else "missing"
    gates.append(Gate("critique_not_rejected", ok, detail))

    gates.append(Gate("within_budget", budget_error is None, budget_error or ""))
    return gates


def overall_status(gates: list[Gate], artifacts: dict[str, Any]) -> str:
    if "synthesize" not in artifacts:
        return "failed"
    return "ok" if all(g.passed for g in gates) else "partial"
