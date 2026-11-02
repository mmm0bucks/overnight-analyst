from __future__ import annotations

import json
from pathlib import Path

import pytest

from overnight.cli import main


def test_http_run_refused_when_key_budget_spent(tmp_path: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in {"BASE_URL": "https://llm.test/v1", "API_KEY": "k", "MODEL": "m"}.items():
        monkeypatch.setenv(f"OVERNIGHT_LLM_{k}", v)
    monkeypatch.setenv("OVERNIGHT_TOTAL_TOKENS", "1000")
    monkeypatch.chdir(tmp_path)  # the counter lives where you run from, not under --root
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "spend.json").write_text(json.dumps({"tokens": 1000}))
    with pytest.raises(SystemExit):
        main(["run", "--llm", "http", "--root", str(tmp_path / "eval" / "1")])


def test_eval_scores_runs_against_expected(ws: Path) -> None:
    assert main(["eval", "--runs", "2", "--today", "2026-10-27",
                 "--root", str(ws.parent), "--workspace", str(ws)]) == 0
    summary = next((ws.parent / "eval").glob("*/summary.md")).read_text(encoding="utf-8")
    assert "| H1 | confirmed | 2/2 |" in summary
    assert "| H5 | confirmed | 0/2 |" in summary  # offline policy has no SQL for H5
    assert "| H8 | inconclusive | 2/2 |" in summary
    assert "| H9 | rejected | 0/2 |" in summary  # it trusts the misleading suggested_sql
    assert "pass^2 (hypotheses right in every run): 5/9" in summary


def test_null_agent_scores_zero(ws: Path) -> None:
    assert main(["eval", "--llm", "null", "--runs", "1",
                 "--root", str(ws.parent), "--workspace", str(ws)]) == 0
    summary = next((ws.parent / "eval").glob("*/summary.md")).read_text(encoding="utf-8")
    assert "0/9 hypothesis checks correct" in summary
    assert "| partial |" in summary  # and the gates do not call an empty answer ok
    # a "yes-man" would get 5/9: the set is balanced enough that guessing does not pass
    assert "always confirmed 5/9" in summary


def test_spend_is_saved_after_every_call(tmp_path: Path) -> None:
    from overnight.cli import Metered
    from overnight.llm import LLMResponse, ScriptedLLM

    f = tmp_path / "state" / "spend.json"
    meter = Metered(ScriptedLLM([LLMResponse(tokens=30), LLMResponse(tokens=12)]), f)
    meter.complete([], [])
    assert json.loads(f.read_text(encoding="utf-8")) == {"tokens": 30}  # counted even if killed now
    meter.complete([], [])
    assert json.loads(f.read_text(encoding="utf-8")) == {"tokens": 42}
