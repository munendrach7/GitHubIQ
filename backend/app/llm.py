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
def _llm_configured() -> bool:
    return get_settings().llm_configured


def get_llm():
    """Return a fresh AzureChatOpenAI client, or ``None`` when unconfigured.

    A new client per call avoids any shared-state races when the specialist
    agents invoke the model concurrently (LangGraph fan-out).
    """
    return _build_llm(json_mode=True, max_tokens=32000, temperature=0.2)


def _build_llm(
    *,
    deployment: Optional[str] = None,
    json_mode: bool = True,
    max_tokens: int = 32000,
    temperature: float = 0.2,
):
    """Construct an AzureChatOpenAI client for a given deployment, or ``None``.

    ``deployment`` defaults to the main reasoning model. Pass the mini deployment
    (see :func:`get_compaction_llm`) for cheap, low-reasoning work. ``json_mode``
    forces a JSON object response; disable it for free-form text (summaries).
    """
    settings = get_settings()
    if not settings.llm_configured:
        logger.warning("Azure OpenAI not configured — agents run in heuristic mode.")
        return None

    from langchain_openai import AzureChatOpenAI

    kwargs: dict[str, Any] = dict(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        azure_deployment=deployment or settings.azure_openai_deployment,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=180,
        max_retries=3,
    )
    if json_mode:
        # Force valid JSON so richer prompts never break parsing.
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return AzureChatOpenAI(**kwargs)


def get_compaction_llm(max_tokens: int = 2000):
    """Cheap/fast model client for compaction & other low-reasoning adhoc tasks."""
    return _build_llm(
        deployment=get_settings().mini_deployment,
        json_mode=False,
        max_tokens=max_tokens,
        temperature=0.1,
    )


def llm_available() -> bool:
    return _llm_configured()


_VALID_ESCAPES = set('"\\/bfnrtu')


def _fix_invalid_escapes(text: str) -> str:
    """Escape stray backslashes the model leaves inside JSON string values.

    Models frequently emit code fragments containing sequences like ``\\d`` (a
    regex), ``\\U`` (a Windows path) or ``\\ `` that are not valid JSON escapes,
    so even ``strict=False`` parsing rejects them. Replace any backslash that
    does not begin a valid escape with an escaped backslash.
    """

    def repl(match: "re.Match[str]") -> str:
        nxt = match.group(1)
        return match.group(0) if nxt in _VALID_ESCAPES else "\\\\" + nxt

    return re.sub(r"\\(.)", repl, text, flags=re.DOTALL)


def _repair_truncated_json(text: str) -> Any:
    """Recover a JSON value from a response truncated mid-generation.

    Runs a small state machine that tracks the container stack and, for each
    open object/array, whether the parser has just finished a complete element.
    The last position where every open container sits at an element boundary is
    a safe place to cut; we truncate there and append the matching closing
    brackets so the payload parses. Best-effort — raises ``ValueError`` when
    nothing usable remains.
    """
    # Per-frame state: "obj" frames track expect in {key, colon, value, sep};
    # "arr" frames track expect in {value, sep}. A frame is at an element
    # boundary when expect == "sep" (a value just completed) or, for a fresh
    # empty container, when expect is key/value (nothing partial yet).
    stack: list[dict[str, str]] = []
    in_string = False
    escape = False
    i = 0
    n = len(text)
    last_safe = -1

    def at_boundary() -> bool:
        return all(f["expect"] in ("sep", "key", "value") for f in stack)

    while i < n:
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
                # A string just closed: advance the owning frame's state.
                if stack:
                    top = stack[-1]
                    if top["container"] == "obj":
                        if top["expect"] == "key":
                            top["expect"] = "colon"
                        elif top["expect"] == "value":
                            top["expect"] = "sep"
                    else:  # arr
                        if top["expect"] == "value":
                            top["expect"] = "sep"
                if at_boundary():
                    last_safe = i + 1
            i += 1
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append({"container": "obj", "expect": "key"})
        elif ch == "[":
            stack.append({"container": "arr", "expect": "value"})
        elif ch in "}]":
            if stack:
                stack.pop()
            if stack:
                top = stack[-1]
                top["expect"] = "sep"
            if at_boundary():
                last_safe = i + 1
        elif ch == ":":
            if stack and stack[-1]["container"] == "obj":
                stack[-1]["expect"] = "value"
        elif ch == ",":
            if stack:
                top = stack[-1]
                top["expect"] = "key" if top["container"] == "obj" else "value"
        elif ch not in " \t\r\n":
            # scalar token (number / true / false / null) — consume to its end
            j = i
            while j < n and text[j] not in ",}] \t\r\n":
                j += 1
            if stack:
                top = stack[-1]
                if top["expect"] == "value":
                    top["expect"] = "sep"
            if at_boundary():
                last_safe = j
            i = j
            continue
        i += 1

    if not stack:  # nothing was ever opened
        raise ValueError("Model response did not contain recoverable JSON")
    if last_safe <= 0:
        raise ValueError("Model response did not contain recoverable JSON")

    candidate = text[:last_safe].rstrip().rstrip(",").rstrip()
    # Re-derive the open containers for the trimmed candidate to close them.
    closers: list[str] = []
    in_string = False
    escape = False
    for ch in candidate:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            closers.append("}")
        elif ch == "[":
            closers.append("]")
        elif ch in "}]":
            if closers:
                closers.pop()
    repaired = candidate + "".join(reversed(closers))
    return json.loads(repaired, strict=False)


def _extract_json(text: str) -> Any:
    """Best-effort extraction of a JSON object/array from a model response."""
    text = text.strip()
    # Parse the raw text FIRST. Lesson bodies frequently embed fenced ```code```
    # blocks, so stripping fences up front would wrongly grab an inner block and
    # corrupt otherwise-valid JSON. strict=False tolerates the literal
    # newlines/tabs the model emits inside those code blocks.
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        pass
    # Only if the raw parse failed, treat the response as fenced (```json ...```).
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        inner = fenced.group(1).strip()
        try:
            return json.loads(inner, strict=False)
        except json.JSONDecodeError:
            text = inner
    # Repair invalid backslash escapes (regexes, Windows paths, etc.) that the
    # model leaves inside string values, then retry.
    sanitized = _fix_invalid_escapes(text)
    if sanitized != text:
        try:
            return json.loads(sanitized, strict=False)
        except json.JSONDecodeError:
            pass
    # Fall back to the first balanced { ... } or [ ... ] block.
    for candidate in (text, sanitized):
        for opener, closer in (("{", "}"), ("[", "]")):
            start = candidate.find(opener)
            end = candidate.rfind(closer)
            if start != -1 and end > start:
                try:
                    return json.loads(candidate[start : end + 1], strict=False)
                except json.JSONDecodeError:
                    continue
    # Last resort: the response was likely truncated at the token limit.
    for candidate in (sanitized, text):
        try:
            return _repair_truncated_json(candidate)
        except (ValueError, json.JSONDecodeError):
            continue
    raise ValueError("Model response did not contain valid JSON")


def invoke_json(
    system_prompt: str, user_prompt: str, *, default: Optional[Any] = None
) -> Any:
    """Invoke the LLM and parse a JSON response, retrying once on failure.

    Returns ``default`` if the LLM is unconfigured or both attempts fail.
    """
    llm = get_llm()
    if llm is None:
        return default

    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    for attempt in range(2):
        try:
            response = llm.invoke(messages)
            content = response.content
            if isinstance(content, list):  # some providers return content parts
                content = "".join(
                    p.get("text", "") if isinstance(p, dict) else str(p) for p in content
                )
            if content and content.strip():
                return _extract_json(content)
            logger.warning("LLM returned empty content (attempt %d)", attempt + 1)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully for the MVP
            logger.error("LLM invocation failed (attempt %d): %s", attempt + 1, exc)
    return default


def invoke_text(
    system_prompt: str,
    user_prompt: str,
    *,
    default: str = "",
    max_tokens: int = 2000,
    cheap: bool = True,
) -> str:
    """Invoke a model and return its plain-text response (no JSON parsing).

    Used for low-reasoning adhoc work such as chunk summarisation / compaction.
    Defaults to the cheap ``mini`` deployment. Returns ``default`` when the LLM
    is unconfigured or every attempt fails, so callers can fall back gracefully.
    """
    llm = (
        get_compaction_llm(max_tokens=max_tokens)
        if cheap
        else _build_llm(json_mode=False, max_tokens=max_tokens, temperature=0.2)
    )
    if llm is None:
        return default

    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    for attempt in range(2):
        try:
            response = llm.invoke(messages)
            content = response.content
            if isinstance(content, list):
                content = "".join(
                    p.get("text", "") if isinstance(p, dict) else str(p) for p in content
                )
            if content and content.strip():
                return content.strip()
        except Exception as exc:  # noqa: BLE001
            logger.error("Text LLM invocation failed (attempt %d): %s", attempt + 1, exc)
    return default
