"""In-process cancellation registry for the local (background-task) run path.

When jobs run inside the API process (no Service Bus configured), cancellation
is delivered through a per-run :class:`threading.Event` so a running pipeline can
abort promptly. When jobs run in a separate worker process, the API process
can't reach that worker's memory, so cancellation is *also* persisted as a flag
on the analysis document (see ``AnalysisResult.cancel_requested``) which the
worker polls. Both mechanisms are honoured by ``ProgressReporter.cancelled()``.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_events: dict[str, threading.Event] = {}


def register(analysis_id: str) -> threading.Event:
    """Return (creating if needed) the cancel event for a run."""
    with _lock:
        ev = _events.get(analysis_id)
        if ev is None:
            ev = threading.Event()
            _events[analysis_id] = ev
        return ev


def request_cancel(analysis_id: str) -> None:
    """Signal cancellation for a run in this process (no-op if not running here)."""
    with _lock:
        ev = _events.get(analysis_id)
        if ev is None:
            ev = threading.Event()
            _events[analysis_id] = ev
        ev.set()


def is_cancelled(analysis_id: str) -> bool:
    with _lock:
        ev = _events.get(analysis_id)
    return bool(ev and ev.is_set())


def clear(analysis_id: str) -> None:
    with _lock:
        _events.pop(analysis_id, None)
