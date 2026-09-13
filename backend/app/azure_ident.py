"""Shared Microsoft Entra (Azure AD) credential for managed-identity auth.

All Azure data-plane clients (Cosmos DB, Service Bus, Azure OpenAI) authenticate
with the same credential so the app can run without any secrets in production:

* In Azure, ``DefaultAzureCredential`` resolves the container/app's **managed
  identity** (system-assigned, or a user-assigned one when ``AZURE_CLIENT_ID`` is
  set). No keys or connection strings are needed.
* Locally, ``DefaultAzureCredential`` falls back to the Azure CLI / VS Code /
  environment credentials, so developers can use their own identity.

The credential is cached (it manages token refresh internally and is
thread-safe), and imports are lazy so the package stays importable when the
``azure-identity`` dependency isn't installed (pure heuristic/local mode).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from .config import get_settings

logger = logging.getLogger("githubiq.identity")

# Entra scope for Azure OpenAI / Cognitive Services data plane.
COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"


@lru_cache
def get_credential() -> Any:
    """Return a cached credential for managed-identity / developer auth."""
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

    settings = get_settings()
    if settings.azure_client_id:
        logger.info("Using user-assigned managed identity (client id set).")
        return ManagedIdentityCredential(client_id=settings.azure_client_id)
    logger.info("Using DefaultAzureCredential for Entra auth.")
    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


def get_token_provider(scope: str = COGNITIVE_SCOPE):
    """Return a bearer-token provider callable for the given Entra scope."""
    from azure.identity import get_bearer_token_provider

    return get_bearer_token_provider(get_credential(), scope)
