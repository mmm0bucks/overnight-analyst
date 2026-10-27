from __future__ import annotations

from overnight.gates import numbers_in, overall_status, run_gates
from overnight.schemas import Claim, CollectOut, CritiqueOut, Section, SynthesizeOut
from overnight.tools import SourceLog


def _log() -> SourceLog:
    log = SourceLog()
    log.add("run_sql", {}, {"rows": [[101, 1000]]}, "collect")
    return log


def _arts(fact: Claim, bullet: Claim, verdict: str = "accept") -> dict[str, object]:
    return {"collect": CollectOut(facts=[fact]),
            "synthesize": SynthesizeOut(headline="h", sections=[Section(title="t",
                                                                        bullets=[bullet])]),
            "critique": CritiqueOut(verdict=verdict)}  # type: ignore[arg-type]


def _failed(arts: dict[str, object], log: SourceLog) -> set[str]:
    ok = dict.fromkeys(arts, "ok")
    return {g.name for g in run_gates(arts, ok, log, None) if not g.passed}


def test_all_green() -> None:
    c = Claim(text="1000 contacts", sources=["S1"], value=1000)
    arts = _arts(c, c)
    gates = run_gates(arts, dict.fromkeys(arts, "ok"), _log(), None)
    assert overall_status(gates, arts) == "ok"


def test_invented_number_is_caught() -> None:
    c = Claim(text="1200 contacts", sources=["S1"], value=1200)
    assert "numbers_traceable" in _failed(_arts(c, c), _log())


def test_unsourced_and_unknown_sources() -> None:
    f = Claim(text="x", sources=[])
    b = Claim(text="y", sources=["S9"])
    assert {"every_claim_sourced", "sources_exist"} <= _failed(_arts(f, b), _log())


def test_synthesis_cannot_introduce_sources() -> None:
    log = _log()
    log.add("run_sql", {}, {"rows": [[5]]}, "synthesize")
    f = Claim(text="a", sources=["S1"])
    b = Claim(text="b", sources=["S2"])
    assert "synthesis_adds_no_sources" in _failed(_arts(f, b), log)


def test_rejected_critique_makes_run_partial() -> None:
    c = Claim(text="a", sources=["S1"])
    arts = _arts(c, c, verdict="reject")
    gates = run_gates(arts, dict.fromkeys(arts, "ok"), _log(), None)
    assert overall_status(gates, arts) == "partial"


def test_numbers_in_ignores_booleans() -> None:
    assert numbers_in({"a": True, "b": [1, "x 2.5"]}) == {1.0, 2.5}
