"""Persistence layer: Azure Cosmos DB with an in-memory fallback.

Analysis results are semi-structured JSON documents, which map naturally to a
document database. Cosmos DB is used in the cloud; when it is not configured
(local dev / demos) an in-memory store keeps the app fully functional.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from .config import get_settings
from .models import AnalysisResult, User

logger = logging.getLogger("githubiq.storage")


class Store:
    def upsert(self, result: AnalysisResult) -> None:  # pragma: no cover
        raise NotImplementedError

    def get(self, analysis_id: str) -> Optional[AnalysisResult]:  # pragma: no cover
        raise NotImplementedError

    def get_user(self, username: str) -> Optional[User]:  # pragma: no cover
        raise NotImplementedError

    def save_user(self, user: User) -> None:  # pragma: no cover
        raise NotImplementedError

    def list_analyses(self, owner: str) -> list[AnalysisResult]:  # pragma: no cover
        raise NotImplementedError

    def list_all_analyses(self) -> list[AnalysisResult]:  # pragma: no cover
        raise NotImplementedError

    def list_users(self) -> list[User]:  # pragma: no cover
        raise NotImplementedError

    # --- Cancellation intents (separate from the analysis doc so a worker's
    # progress writes can never clobber a user's cancel request) ---
    def request_cancel(self, analysis_id: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def is_cancel_requested(self, analysis_id: str) -> bool:  # pragma: no cover
        raise NotImplementedError

    def cleanup(self, older_than_ts: float) -> int:  # pragma: no cover
        """Delete terminal analyses and cancel intents created before ``older_than_ts``."""
        raise NotImplementedError


class MemoryStore(Store):
    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        self._users: dict[str, dict] = {}
        self._cancels: dict[str, float] = {}
        self._lock = threading.Lock()

    def upsert(self, result: AnalysisResult) -> None:
        with self._lock:
            self._data[result.id] = result.as_document()

    def get(self, analysis_id: str) -> Optional[AnalysisResult]:
        with self._lock:
            doc = self._data.get(analysis_id)
        return AnalysisResult.model_validate(doc) if doc else None

    def get_user(self, username: str) -> Optional[User]:
        with self._lock:
            doc = self._users.get(username.lower())
        return User.model_validate(doc) if doc else None

    def save_user(self, user: User) -> None:
        with self._lock:
            self._users[user.username.lower()] = user.as_document()

    def list_analyses(self, owner: str) -> list[AnalysisResult]:
        with self._lock:
            docs = [d for d in self._data.values() if d.get("owner") == owner]
        results = [AnalysisResult.model_validate(d) for d in docs]
        return sorted(results, key=lambda r: r.created_at, reverse=True)

    def list_all_analyses(self) -> list[AnalysisResult]:
        with self._lock:
            docs = list(self._data.values())
        results = [AnalysisResult.model_validate(d) for d in docs]
        return sorted(results, key=lambda r: r.created_at, reverse=True)

    def list_users(self) -> list[User]:
        with self._lock:
            docs = list(self._users.values())
        return [User.model_validate(d) for d in docs]

    def request_cancel(self, analysis_id: str) -> None:
        with self._lock:
            self._cancels[analysis_id] = time.time()

    def is_cancel_requested(self, analysis_id: str) -> bool:
        with self._lock:
            return analysis_id in self._cancels

    def cleanup(self, older_than_ts: float) -> int:
        removed = 0
        with self._lock:
            for aid, doc in list(self._data.items()):
                if doc.get("status") in ("done", "error", "cancelled") and (
                    doc.get("created_at") or 0
                ) < older_than_ts:
                    del self._data[aid]
                    self._cancels.pop(aid, None)
                    removed += 1
            for aid, ts in list(self._cancels.items()):
                if ts < older_than_ts:
                    del self._cancels[aid]
                    removed += 1
        return removed


class CosmosStore(Store):
    def __init__(self) -> None:
        from azure.cosmos import CosmosClient

        settings = get_settings()
        if settings.cosmos_key:
            client = CosmosClient(
                settings.cosmos_endpoint, credential=settings.cosmos_key
            )
        else:
            # Keyless: authenticate with the managed identity (Entra RBAC).
            from .azure_ident import get_credential

            client = CosmosClient(
                settings.cosmos_endpoint, credential=get_credential()
            )
        # The database and containers are provisioned by Terraform; only
        # *reference* them here so the app needs just data-plane RBAC (creating
        # them would require control-plane rights the managed identity lacks).
        db = client.get_database_client(settings.cosmos_database)
        self._container = db.get_container_client(settings.cosmos_container)
        self._users = db.get_container_client("users")

    def upsert(self, result: AnalysisResult) -> None:
        self._container.upsert_item(result.as_document())

    def get(self, analysis_id: str) -> Optional[AnalysisResult]:
        from azure.cosmos import exceptions

        try:
            doc = self._container.read_item(analysis_id, partition_key=analysis_id)
        except exceptions.CosmosHttpResponseError:
            return None
        return AnalysisResult.model_validate(doc)

    def get_user(self, username: str) -> Optional[User]:
        from azure.cosmos import exceptions

        uid = username.lower()
        try:
            doc = self._users.read_item(uid, partition_key=uid)
        except exceptions.CosmosHttpResponseError:
            return None
        return User.model_validate(doc)

    def save_user(self, user: User) -> None:
        doc = user.as_document()
        doc["id"] = user.username.lower()
        self._users.upsert_item(doc)

    def list_analyses(self, owner: str) -> list[AnalysisResult]:
        query = (
            "SELECT * FROM c WHERE c.owner = @owner ORDER BY c.created_at DESC"
        )
        items = self._container.query_items(
            query=query,
            parameters=[{"name": "@owner", "value": owner}],
            enable_cross_partition_query=True,
        )
        return [AnalysisResult.model_validate(d) for d in items]

    def list_all_analyses(self) -> list[AnalysisResult]:
        # Exclude cancel-intent docs; tolerate any malformed doc rather than 500.
        query = "SELECT * FROM c WHERE NOT STARTSWITH(c.id, 'cancel:')"
        items = self._container.query_items(
            query=query, enable_cross_partition_query=True
        )
        results: list[AnalysisResult] = []
        for d in items:
            try:
                results.append(AnalysisResult.model_validate(d))
            except Exception:  # noqa: BLE001
                continue
        return sorted(results, key=lambda r: r.created_at, reverse=True)

    def list_users(self) -> list[User]:
        items = self._users.query_items(
            query="SELECT * FROM c", enable_cross_partition_query=True
        )
        out: list[User] = []
        for d in items:
            try:
                out.append(User.model_validate(d))
            except Exception:  # noqa: BLE001
                continue
        return out

    def request_cancel(self, analysis_id: str) -> None:
        self._container.upsert_item(
            {
                "id": f"cancel:{analysis_id}",
                "kind": "cancel",
                "analysis_id": analysis_id,
                "created_at": time.time(),
            }
        )

    def is_cancel_requested(self, analysis_id: str) -> bool:
        from azure.cosmos import exceptions

        cid = f"cancel:{analysis_id}"
        try:
            self._container.read_item(cid, partition_key=cid)
            return True
        except exceptions.CosmosHttpResponseError:
            return False

    def cleanup(self, older_than_ts: float) -> int:
        query = (
            "SELECT c.id FROM c WHERE c.created_at < @cutoff AND "
            "(STARTSWITH(c.id, 'cancel:') OR c.status IN ('done', 'error', 'cancelled'))"
        )
        items = list(
            self._container.query_items(
                query=query,
                parameters=[{"name": "@cutoff", "value": older_than_ts}],
                enable_cross_partition_query=True,
            )
        )
        removed = 0
        for it in items:
            try:
                self._container.delete_item(it["id"], partition_key=it["id"])
                removed += 1
            except Exception:  # noqa: BLE001
                continue
        return removed


_store: Optional[Store] = None


def get_store() -> Store:
    global _store
    if _store is not None:
        return _store
    settings = get_settings()
    if settings.cosmos_configured:
        try:
            _store = CosmosStore()
            logger.info("Using Cosmos DB store.")
        except Exception as exc:  # noqa: BLE001
            logger.error("Cosmos init failed (%s); using memory store.", exc)
            _store = MemoryStore()
    else:
        logger.info("Cosmos not configured; using in-memory store.")
        _store = MemoryStore()
    return _store
