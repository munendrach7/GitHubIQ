"""LLM client factory and a resilient JSON-invocation helper.

Wraps Azure OpenAI (provisioned via Azure AI Foundry). When no credentials are
configured the helper returns ``None`` so agents can fall back to heuristics,
keeping local development and demos runnable without a cloud dependency.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any, Optional

from .config import get_settings

logger = logging.getLogger("githubiq.llm")


@lru_cache
def get_llm():
    """Return a cached AzureChatOpenAI client, or ``None`` when unconfigured."""
    settings = get_settings()
    if not settings.llm_configured:
        logger.warning("Azure OpenAI not configured — agents run in heuristic mode.")
        return None

    from langchain_openai import AzureChatOpenAI

    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        azure_deployment=settings.azure_openai_deployment,
        temperature=0.25,
        max_tokens=8000,
        timeout=120,
        max_retries=2,
    )


def llm_available() -> bool:
    return get_llm() is not None


def _extract_json(text: str) -> Any:
    """Best-effort extraction of a JSON object/array from a model response."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to the first balanced { ... } or [ ... ] block.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("Model response did not contain valid JSON")


def invoke_json(
    system_prompt: str, user_prompt: str, *, default: Optional[Any] = None
) -> Any:
    """Invoke the LLM and parse a JSON response.

    Returns ``default`` if the LLM is unconfigured or the call/parse fails.
    """
    llm = get_llm()
    if llm is None:
        return default

    from langchain_core.messages import HumanMessage, SystemMessage

    try:
        response = llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        )
        return _extract_json(response.content)
    except Exception as exc:  # noqa: BLE001 - degrade gracefully for the MVP
        logger.error("LLM invocation failed: %s", exc)
        return default
