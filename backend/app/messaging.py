"""Azure Service Bus job dispatch.

The API enqueues a small message (just the analysis id) onto a queue; one or more
worker processes (:mod:`app.worker`) consume messages and run the heavy agent
pipeline asynchronously. This decouples the request/response path from the
long-running analysis and lets the system scale horizontally and survive
restarts — an in-flight message is redelivered if a worker crashes.

Authentication prefers **managed identity** (``SERVICEBUS_NAMESPACE`` +
``DefaultAzureCredential``); a connection string is supported for local dev.
When neither is configured, :func:`servicebus_enabled` returns ``False`` and the
caller falls back to running the job in-process.
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Iterator

from .config import get_settings

logger = logging.getLogger("githubiq.messaging")


def servicebus_enabled() -> bool:
    return get_settings().servicebus_configured


@contextmanager
def _client() -> Iterator[object]:
    """Yield a ServiceBusClient built from MI or a connection string."""
    from azure.servicebus import ServiceBusClient

    settings = get_settings()
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
    try:
        yield client
    finally:
        client.close()


def enqueue_analysis(analysis_id: str) -> bool:
    """Publish a job message. Returns ``True`` on success, ``False`` on failure.

    Failure is non-fatal: the caller can fall back to in-process execution so a
    transient Service Bus problem never blocks a user's request.
    """
    if not servicebus_enabled():
        return False
    settings = get_settings()
    try:
        from azure.servicebus import ServiceBusMessage

        with _client() as client:
            sender = client.get_queue_sender(queue_name=settings.servicebus_queue)
            with sender:
                msg = ServiceBusMessage(
                    json.dumps({"analysis_id": analysis_id}),
                    content_type="application/json",
                    message_id=analysis_id,          # dedup key
                    session_id=None,
                )
                sender.send_messages(msg)
        logger.info("Enqueued analysis job %s", analysis_id)
        return True
    except Exception as exc:  # noqa: BLE001 - degrade to in-process execution
        logger.error("Failed to enqueue job %s: %s", analysis_id, exc)
        return False
