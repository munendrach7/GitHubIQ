"""Async analysis worker — consumes jobs from Azure Service Bus.

Run one or more of these alongside the API:

    python -m app.worker

Each worker pulls a job message (an analysis id), fetches the repository and runs
the full multi-agent pipeline, then completes the message. It is built to be
**fault tolerant**:

* **Managed identity** auth (no secrets) via the shared credential.
* **Lock renewal** — long analyses keep their message lock alive with
  ``AutoLockRenewer`` so the broker doesn't redeliver a job that's still running.
* **Idempotency** — a job already in a terminal state (done/error/cancelled) is
  acknowledged and skipped, so a redelivery never double-processes.
* **Poison handling** — after ``job_max_attempts`` deliveries the message is
  dead-lettered instead of looping forever.
* **Cancellation** — the pipeline polls the persisted ``cancel_requested`` flag.
* **Graceful degradation** — transient repo/pipeline errors mark the analysis as
  errored and complete the message (the failure is captured in the document).
"""
from __future__ import annotations

import json
import logging
import signal
import sys
import threading
import time

from .agents.orchestrator import run_pipeline
from .config import get_settings
from .github_client import GitHubClient, parse_repo_url
from .models import AnalysisResult, AnalysisStatus
from .storage import get_store

logging.basicConfig(level=logging.INFO)
# Azure SDKs log every HTTP request/response at INFO; the 1s cancel-intent poll
# alone floods the log with 404s. Keep only warnings+ from the SDK loggers.
logging.getLogger("azure").setLevel(logging.WARNING)
logger = logging.getLogger("githubiq.worker")

_TERMINAL = {AnalysisStatus.done, AnalysisStatus.error, AnalysisStatus.cancelled}
_shutdown = False
_stop_event = threading.Event()


def _run_janitor() -> None:
    """Periodically delete terminal analyses and cancel intents older than the
    configured age (default 2 days) so the store doesn't grow without bound."""
    settings = get_settings()
    interval = max(60.0, settings.janitor_interval_minutes * 60.0)
    max_age = settings.cleanup_after_hours * 3600.0
    store = get_store()
    logger.info(
        "Janitor started; purging terminal jobs + cancel intents older than %.0fh every %.0fm",
        settings.cleanup_after_hours, settings.janitor_interval_minutes,
    )
    while not _stop_event.wait(interval):
        try:
            removed = store.cleanup(time.time() - max_age)
            if removed:
                logger.info("Janitor removed %d old record(s)", removed)
        except Exception as exc:  # noqa: BLE001 - never let cleanup kill the worker
            logger.error("Janitor cleanup failed: %s", exc)


def _process(analysis_id: str) -> None:
    """Run one analysis job to completion (idempotent, cancellation-aware)."""
    store = get_store()
    result = store.get(analysis_id)
    if result is None:
        logger.warning("Job %s: analysis document not found; skipping", analysis_id)
        return
    if result.status in _TERMINAL:
        logger.info("Job %s already %s; skipping", analysis_id, result.status)
        return
    if store.is_cancel_requested(analysis_id) or result.cancel_requested:
        logger.info("Job %s cancelled before start", analysis_id)
        result.status = AnalysisStatus.cancelled
        result.error = "Cancelled by user."
        store.upsert(result)
        return

    result.attempts = (result.attempts or 0) + 1
    store.upsert(result)

    try:
        owner, repo = parse_repo_url(result.repo_url)
        with GitHubClient() as gh:
            ctx = gh.fetch_context(owner, repo, result.scope_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Job %s: failed to fetch repository", analysis_id)
        result.status = AnalysisStatus.error
        result.error = f"Could not read repository: {exc}"
        store.upsert(result)
        return

    run_pipeline(result, ctx, store)
    logger.info("Job %s finished with status=%s", analysis_id, store.get(analysis_id).status)


def _handle_message(msg) -> str:
    """Return the analysis id from a message body (JSON or raw id)."""
    body = b"".join(msg.body) if not isinstance(msg.body, (bytes, str)) else msg.body
    text = body.decode() if isinstance(body, bytes) else str(body)
    text = text.strip()
    try:
        return json.loads(text).get("analysis_id", "")
    except (json.JSONDecodeError, AttributeError):
        return text


def run_worker() -> None:
    settings = get_settings()
    if not settings.servicebus_configured:
        logger.error(
            "Service Bus is not configured (set SERVICEBUS_NAMESPACE or "
            "SERVICEBUS_CONNECTION_STRING). Nothing to consume."
        )
        sys.exit(1)

    from azure.servicebus import ServiceBusClient
    from azure.servicebus.exceptions import ServiceBusError

    if settings.servicebus_connection_string:
        client = ServiceBusClient.from_connection_string(
            settings.servicebus_connection_string
        )
    else:
        from .azure_ident import get_credential

        client = ServiceBusClient(
            fully_qualified_namespace=settings.servicebus_namespace,
            credential=get_credential(),
        )

    from azure.servicebus import AutoLockRenewer

    renewer = AutoLockRenewer(max_lock_renewal_duration=settings.servicebus_max_lock_renewal)
    logger.info(
        "Worker started; consuming queue '%s' (max_attempts=%d)",
        settings.servicebus_queue, settings.job_max_attempts,
    )

    # Background cleanup of old completed runs and stale cancel intents.
    threading.Thread(target=_run_janitor, name="janitor", daemon=True).start()

    with client:
        receiver = client.get_queue_receiver(
            queue_name=settings.servicebus_queue, max_wait_time=30
        )
        with receiver:
            while not _shutdown:
                try:
                    batch = receiver.receive_messages(max_message_count=1, max_wait_time=20)
                except ServiceBusError as exc:
                    logger.error("Receive failed (will retry): %s", exc)
                    continue
                for msg in batch:
                    renewer.register(receiver, msg)
                    analysis_id = _handle_message(msg)
                    try:
                        if (msg.delivery_count or 0) >= settings.job_max_attempts:
                            logger.error(
                                "Job %s exceeded %d attempts; dead-lettering",
                                analysis_id, settings.job_max_attempts,
                            )
                            _mark_error(analysis_id, "Exceeded max processing attempts.")
                            receiver.dead_letter_message(
                                msg, reason="max_attempts_exceeded"
                            )
                            continue
                        _process(analysis_id)
                        receiver.complete_message(msg)
                    except Exception as exc:  # noqa: BLE001
                        # Abandon → the broker redelivers (up to max_attempts).
                        logger.exception("Job %s failed; abandoning for retry", analysis_id)
                        try:
                            receiver.abandon_message(msg)
                        except ServiceBusError:
                            logger.error("Could not abandon message for %s", analysis_id)
    renewer.close()
    logger.info("Worker stopped.")


def _mark_error(analysis_id: str, message: str) -> None:
    if not analysis_id:
        return
    store = get_store()
    result = store.get(analysis_id)
    if result and result.status not in _TERMINAL:
        result.status = AnalysisStatus.error
        result.error = message
        store.upsert(result)


def _install_signal_handlers() -> None:
    def _stop(signum, _frame):  # noqa: ANN001
        global _shutdown
        logger.info("Received signal %s; shutting down after current message.", signum)
        _shutdown = True
        _stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _stop)
        except (ValueError, OSError):  # not on the main thread / unsupported
            pass


if __name__ == "__main__":
    _install_signal_handlers()
    run_worker()
