from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from overnight import demo_data
from overnight.config import Limits, Paths

REPO = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 27)


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    ws = tmp_path / "demo"
    shutil.copytree(REPO / "demo", ws, ignore=shutil.ignore_patterns("*.duckdb*"))
    demo_data.build(ws / "warehouse.duckdb")
    return Paths.under(tmp_path, ws)


@pytest.fixture
def limits() -> Limits:
    return Limits()
