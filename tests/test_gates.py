from __future__ import annotations

from pydantic import BaseModel

from overnight.gates import numbers_in, run_gates, status
from overnight.stages import Claim, CollectOut, CritiqueOut, Section, SynthesizeOut
from overnight.tools import Source

SOURCES = {"S1": Source("S1", "run_sql", {}, {"rows": [[101, 1000]]}),
           "S2": Source("S2", "run_sql", {}, {"rows": [[5]]})}


def _arts(fact: Claim, bullet: Claim, verdict: str = "accept") -> dict[str, BaseModel]:
    return {"collect": CollectOut(facts=[fact]),
            "synthesize": SynthesizeOut(headline="h", sections=[Section(title="t",
                                                                        bullets=[bullet])]),
            "critique": CritiqueOut(verdict=verdict)}  # type: ignore[arg-type]


def _failed(fact: Claim, bullet: Claim, verdict: str = "accept") -> set[str]:
    return {g.name for g in run_gates(_arts(fact, bullet, verdict), {}, SOURCES)
            if not g.passed}


def test_all_green() -> None:
    c = Claim(text="1000 contacts", sources=["S1"], value=1000)
    assert status(run_gates(_arts(c, c), {}, SOURCES), _arts(c, c)) == "ok"


def test_invented_number_is_caught() -> None:
    c = Claim(text="1200 contacts", sources=["S1"], value=1200)
    assert _failed(c, c) == {"numbers_traceable"}


def test_unsourced_and_unknown_sources() -> None:
    assert {"every_claim_sourced", "sources_exist"} <= _failed(
        Claim(text="x"), Claim(text="y", sources=["S9"]))


def test_synthesis_cannot_introduce_sources() -> None:
    assert _failed(Claim(text="a", sources=["S1"]), Claim(text="b", sources=["S2"])) == {
        "synthesis_adds_no_sources"}


def test_rejected_critique_fails_gate() -> None:
    c = Claim(text="a", sources=["S1"])
    assert _failed(c, c, "reject") == {"critique_not_rejected"}


def test_numbers_in_ignores_booleans() -> None:
    assert numbers_in({"a": True, "b": [1, "x 2.5"]}) == {1.0, 2.5}
