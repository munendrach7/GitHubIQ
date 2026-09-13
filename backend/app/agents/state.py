"""Shared LangGraph state and the thread-safe progress reporter."""
from __future__ import annotations

import threading
from typing import Any, Optional, TypedDict

from ..models import (
    AnalysisResult,
    AnalysisStatus,
    Architecture,
    DataFlow,
    Guide,
    Lesson,
    ResearchBrief,
    Sandbox,
    Schema,
)
from ..storage import Store


class ProgressReporter:
    """Mutates the shared AnalysisResult and persists it as agents progress.

    Safe for the concurrent (fan-out) agent branches LangGraph executes.
    """

    #: weight each agent contributes to the overall percentage
    WEIGHTS = {
        "Researcher": 20,
        "Architect": 18,
        "Schema": 14,
        "Data-Flow": 20,
        "Tutor": 14,
        "Walkthrough": 14,
    }

    def __init__(self, result: AnalysisResult, store: Store) -> None:
        self._result = result
        self._store = store
        self._lock = threading.Lock()

    @property
    def result(self) -> AnalysisResult:
        return self._result

    def _find(self, name: str):
        for p in self._result.progress:
            if p.name == name:
                return p
        return None

    def update(self, name: str, status: str, detail: str = "") -> None:
        with self._lock:
            entry = self._find(name)
            if entry:
                entry.status = status
                if detail:
                    entry.detail = detail
            done = sum(
                self.WEIGHTS.get(p.name, 0)
                for p in self._result.progress
                if p.status == "done"
            )
            self._result.percent = min(99, done)
            self._store.upsert(self._result)

    def finish(self) -> None:
        with self._lock:
            self._result.status = AnalysisStatus.done
            self._result.percent = 100
            self._store.upsert(self._result)

    def fail(self, message: str) -> None:
        with self._lock:
            self._result.status = AnalysisStatus.error
            self._result.error = message
            self._store.upsert(self._result)


class GraphState(TypedDict, total=False):
    ctx: Any                 # RepoContext (not serialized into the DB)
    reporter: ProgressReporter
    preferences: Any

    research: ResearchBrief
    architecture: Architecture
    schema: Schema
    dataflow: DataFlow
    tutor_lessons: list[Lesson]
    sandbox: Sandbox
    guide: Guide
