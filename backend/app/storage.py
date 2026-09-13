"""Persistence layer: Azure Cosmos DB with an in-memory fallback.

Analysis results are semi-structured JSON documents, which map naturally to a
document database. Cosmos DB is used in the cloud; when it is not configured
(local dev / demos) an in-memory store keeps the app fully functional.
"""
from __future__ import annotations

import logging
import threading
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


class MemoryStore(Store):
    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        self._users: dict[str, dict] = {}
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


class CosmosStore(Store):
    def __init__(self) -> None:
        from azure.cosmos import CosmosClient, PartitionKey

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
        db = client.create_database_if_not_exists(settings.cosmos_database)
        self._container = db.create_container_if_not_exists(
            id=settings.cosmos_container,
            partition_key=PartitionKey(path="/id"),
        )
        self._users = db.create_container_if_not_exists(
            id="users",
            partition_key=PartitionKey(path="/id"),
        )

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
        query = "SELECT * FROM c ORDER BY c.created_at DESC"
        items = self._container.query_items(
            query=query, enable_cross_partition_query=True
        )
        return [AnalysisResult.model_validate(d) for d in items]


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
