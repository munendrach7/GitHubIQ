"""Shared LangGraph state and the thread-safe progress reporter."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional, TypedDict

from ..models import (
    AnalysisResult,
    AnalysisStatus,
    Architecture,
    DataFlow,
    Guide,
    Lesson,
    ResearchBrief,
    Schema,
    VideoExplainer,
)
from ..storage import Store


class PipelineCancelled(Exception):
    """Raised to abort the agent pipeline when the user cancels a run."""


def check_cancelled(reporter: "ProgressReporter | None") -> None:
    """Raise :class:`PipelineCancelled` if the run has been cancelled."""
    if reporter is not None and reporter.cancelled():
        raise PipelineCancelled()


class ProgressReporter:
    """Mutates the shared AnalysisResult and persists it as agents progress.

    Safe for the concurrent (fan-out) agent branches LangGraph executes.
    """

    #: weight each agent contributes to the overall percentage
    WEIGHTS = {
        "Researcher": 18,
        "Architect": 15,
        "Schema": 12,
        "Data-Flow": 18,
        "Deep-Dive": 13,
        "Tutor": 12,
        "Presenter": 12,
    }

    def __init__(
        self,
        result: AnalysisResult,
        store: Store,
        cancel_event: "threading.Event | None" = None,
        cancel_check: "Callable[[], bool] | None" = None,
    ) -> None:
        self._result = result
        self._store = store
        self._lock = threading.Lock()
        self._cancel = cancel_event
        # Optional external check (e.g. re-read a persisted cancel flag) so a run
        # executing in a worker process still sees a cancel issued via the API.
        self._cancel_check = cancel_check
        self._cancel_latched = False
        self._last_poll = 0.0
        self._poll_interval = 2.0  # seconds between external cancel-flag reads

    @property
    def result(self) -> AnalysisResult:
        return self._result

    def cancelled(self) -> bool:
        """True once a cancellation has been requested for this run.

        Checks the in-process event first (cheap), then, at most every
        ``_poll_interval`` seconds, an optional external flag (e.g. the persisted
        ``cancel_requested``). The result latches so we never flip back.
        """
        if self._cancel_latched:
            return True
        if self._cancel is not None and self._cancel.is_set():
            self._cancel_latched = True
            return True
        if self._cancel_check is not None:
            now = time.monotonic()
            if now - self._last_poll >= self._poll_interval:
                self._last_poll = now
                try:
                    if self._cancel_check():
                        self._cancel_latched = True
                except Exception:  # noqa: BLE001 - never let a poll break the run
                    pass
        return self._cancel_latched

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

    def cancel(self, message: str = "Cancelled by user.") -> None:
        with self._lock:
            self._result.status = AnalysisStatus.cancelled
            self._result.error = message
            for p in self._result.progress:
                if p.status in ("waiting", "running"):
                    p.status = "error"
                    p.detail = p.detail or "Cancelled"
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
    component_deepdives: dict[str, str]
    video: VideoExplainer
    guide: Guide
