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
