"""The HTTP API on the offline policy: start, poll, read, approve, reject, auth."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from overnight.api import create_app


@pytest.fixture
def client(ws: Path) -> TestClient:  # ws is tmp/demo, so tmp is the root
    return TestClient(create_app(ws.parent, "offline"))


def _wait(client: TestClient, run_id: str, until: str = "running") -> dict[str, Any]:
    for _ in range(300):
        body: dict[str, Any] = client.get(f"/runs/{run_id}").json()
        if body["status"] != until:
            return body
        time.sleep(0.1)
    raise AssertionError(f"{run_id} still {until}")


def test_start_poll_and_read_the_report(client: TestClient) -> None:
    started = client.post("/runs")
    assert started.status_code == 202 and started.json()["status"] == "running"
    run_id = started.json()["run_id"]
    done = _wait(client, run_id)
    assert done["status"] == "ok" and done["failed_gates"] == []
    report = client.get(f"/runs/{run_id}/report")
    assert report.status_code == 200 and report.text.startswith("---")


@pytest.mark.parametrize(("action", "status", "gate_failed"),
                         [("approve", "ok", False), ("reject", "partial", True)])
def test_a_night_waits_for_approval(client: TestClient, action: str, status: str,
                                    gate_failed: bool) -> None:
    run_id = client.post("/runs", json={"approve": True}).json()["run_id"]
    assert _wait(client, run_id)["status"] == "waiting"
    assert client.get(f"/runs/{run_id}/report").status_code == 409  # nothing published yet
    assert client.post(f"/runs/{run_id}/{action}").status_code == 202
    done = _wait(client, run_id)
    assert done["status"] == status
    assert ("human_approved" in done["failed_gates"]) is gate_failed
    assert client.post(f"/runs/{run_id}/approve").status_code == 409  # only once


def test_unknown_run_is_404(client: TestClient) -> None:
    assert client.get("/runs/nope").status_code == 404


def test_token_is_required_when_set(ws: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OVERNIGHT_API_TOKEN", "s3cret")
    client = TestClient(create_app(ws.parent, "offline"))
    assert client.get("/health").status_code == 200  # health stays open
    assert client.post("/runs").status_code == 401
    assert client.get("/runs/x", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/runs/x", headers={"X-API-Key": "s3cret"}).status_code == 404
