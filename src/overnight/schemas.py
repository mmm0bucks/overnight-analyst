"""Stage contracts. Every stage must return JSON that validates against one of these."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Claim(BaseModel):
    text: str
    sources: list[str] = Field(default_factory=list, description="source ids, e.g. ['S3']")
    value: float | None = Field(
        default=None, description="the key number in the claim, if any; must appear in a source"
    )


class CollectOut(BaseModel):
    facts: list[Claim]
    open_questions: list[str] = Field(default_factory=list)


class HypothesisResult(BaseModel):
    id: str
    statement: str
    status: Literal["confirmed", "rejected", "inconclusive"]
    evidence: list[Claim]


class AnalyzeOut(BaseModel):
    hypotheses: list[HypothesisResult]
    notes: list[Claim] = Field(default_factory=list)


class Section(BaseModel):
    title: str
    bullets: list[Claim]


class SynthesizeOut(BaseModel):
    headline: str
    sections: list[Section]


class CritiqueOut(BaseModel):
    verdict: Literal["accept", "revise", "reject"]
    issues: list[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    """A hypothesis in the persistent backlog (state)."""

    id: str
    statement: str
    suggested_sql: str | None = None
    status: Literal["open", "confirmed", "rejected", "inconclusive"] = "open"
    last_checked: str | None = None
