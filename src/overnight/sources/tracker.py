"""Task tracker adapter. The demo uses a local JSON file; a GitHub Issues adapter
implements the same read-only interface."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class Task(BaseModel):
    id: str
    title: str
    status: str  # open | in_progress | done
    due: date | None = None
    body: str = ""
    labels: list[str] = []

    def overdue(self, today: date) -> bool:
        return self.status != "done" and self.due is not None and self.due < today


class Tracker(Protocol):
    def list_tasks(self) -> list[Task]: ...
    def get_task(self, task_id: str) -> Task: ...


class LocalTracker:
    def __init__(self, path: Path) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._tasks = {t["id"]: Task.model_validate(t) for t in raw}

    def list_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> Task:
        if task_id not in self._tasks:
            raise KeyError(f"unknown task: {task_id}")
        return self._tasks[task_id]
