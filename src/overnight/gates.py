"""Quality gates run by plain code after the LLM stages. Code decides, not the model."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from overnight.stages import AnalyzeOut, Claim, CollectOut, CritiqueOut, SynthesizeOut
from overnight.tools import Source

# Links and images in the report: Obsidian renders images, so a URL planted by an injected
# document could leak data to an outside server the moment the note is opened.
EXTERNAL = re.compile(r"https?://|www\.|!\[")


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
        # "1 000" and "1,000" are one number too: the wiki writes thousands that way
        joined = re.sub(r"(?<=\d)[ ,](?=\d{3}(?!\d))", "", obj)
        return {float(x) for s in (obj, joined) for x in re.findall(r"-?\d+(?:\.\d+)?", s)}
    if isinstance(obj, dict):
        obj = list(obj.values())
    if isinstance(obj, list):
        # a list's length is a fact of the source too ("3 wiki pages", "15 duplicate rows")
        return {float(len(obj))}.union(*map(numbers_in, obj))
    return set()


def run_gates(arts: dict[str, BaseModel], stage_errors: dict[str, str],
              sources: dict[str, Source], asked: list[str] | None = None) -> list[Gate]:
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
    report = arts.get("synthesize")
    texts = [c.text for c in by_stage.get("synthesize", [])]
    if isinstance(report, SynthesizeOut):
        texts.append(report.headline)
    links = [t for t in texts if EXTERNAL.search(t)]
    crit = arts.get("critique")
    verdict = crit.verdict if isinstance(crit, CritiqueOut) else "missing"
    analysis = arts.get("analyze")
    answered = {h.id for h in analysis.hypotheses} if isinstance(analysis, AnalyzeOut) else set()
    # an empty answer passes every other gate: found by running the eval with a null agent
    skipped = [h for h in asked or [] if h not in answered]
    return [
        Gate("all_stages_ok", not stage_errors, "; ".join(f"{k}: {v}" for k, v in
                                                          stage_errors.items())),
        Gate("every_claim_sourced", not unsourced, "; ".join(unsourced[:5])),
        Gate("sources_exist", not unknown, ", ".join(unknown)),
        Gate("numbers_traceable", not untraceable, "; ".join(untraceable[:5])),
        Gate("synthesis_adds_no_sources", not new, ", ".join(new)),
        Gate("critique_not_rejected", verdict in ("accept", "revise"), verdict),
        Gate("no_external_links", not links, "; ".join(links[:3])),
        Gate("every_hypothesis_answered", not skipped, ", ".join(skipped)),
    ]


def status(gates: list[Gate], arts: dict[str, BaseModel]) -> str:
    if "synthesize" not in arts:
        return "failed"
    return "ok" if all(g.passed for g in gates) else "partial"
