from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from overnight.judge import calibrate, kappa, variants
from overnight.llm import LLMResponse

BASE = Path(__file__).parents[1] / "demo" / "judge"


def _read(name: str) -> Any:
    return json.loads((BASE / name).read_text(encoding="utf-8"))


class Oracle:
    """A perfect judge: it recognises each variant and answers its label."""

    def __init__(self) -> None:
        cases = variants(_read("synthesize.json"), _read("analyze.json"))
        self.label_of = {json.dumps(r, ensure_ascii=False): lbl for _, r, lbl in cases}

    def complete(self, messages: list[dict[str, Any]],
                 tools: list[dict[str, Any]]) -> LLMResponse:
        verdict = next(lbl for r, lbl in self.label_of.items() if r in messages[1]["content"])
        return LLMResponse(content=json.dumps({"verdict": verdict}), tokens=10)


class Always:
    def __init__(self, content: str) -> None:
        self.content = content

    def complete(self, messages: list[dict[str, Any]],
                 tools: list[dict[str, Any]]) -> LLMResponse:
        return LLMResponse(content=self.content, tokens=10)


def test_variants_are_labelled_and_really_changed() -> None:
    report, analyze = _read("synthesize.json"), _read("analyze.json")
    cases = {name: (r, label) for name, r, label in variants(report, analyze)}
    assert [lbl for _, lbl in cases.values()].count("bad") == 4
    assert all(r != report for name, (r, _) in cases.items() if name != "original")
    assert "duplicate" not in json.dumps(cases["dropped finding"][0]).lower()
    assert report == _read("synthesize.json")  # the base report is not mutated


def test_kappa() -> None:
    assert kappa(["good", "bad"], ["good", "bad"]) == 1.0
    assert kappa(["good", "bad", "bad"], ["good"] * 3) == 0.0  # always one answer = chance
    assert kappa(["good", "bad"], ["bad", "good"]) == pytest.approx(-1.0)


def test_calibration_scores_a_perfect_and_a_lazy_judge() -> None:
    text, tokens = calibrate(Oracle(), BASE, runs=2)
    assert "agreement with the labels: 14/14" in text and "Cohen's kappa: 1.00" in text
    assert tokens == 140
    lazy, _ = calibrate(Always('{"verdict": "good"}'), BASE, runs=1)
    assert "Cohen's kappa: 0.00" in lazy  # always "good" is no better than chance
    broken, _ = calibrate(Always("not json"), BASE, runs=1)
    assert "invalid" in broken and "agreement with the labels: 0/7" in broken
