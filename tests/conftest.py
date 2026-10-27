from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from overnight import demo_data

TODAY = date(2026, 10, 27)


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    """A fresh demo workspace (tasks, wiki, hypotheses, warehouse) under tmp_path/demo."""
    ws = tmp_path / "demo"
    shutil.copytree(Path(__file__).parents[1] / "demo", ws,
                    ignore=shutil.ignore_patterns("*.duckdb*"))
    demo_data.build(ws / "warehouse.duckdb")
    return ws
