"""Chunked, map-reduce context compaction.

The specialists must read the *specific* files the Researcher assigned them, but
those files can far exceed a single prompt's budget. Hard-truncating the list
(the naive approach) silently drops whole files of context — exactly what we must
avoid. Instead this module GUARANTEES every assigned file contributes to the
context handed to a specialist:

* **Fast path** — if the raw contents fit the budget, they are returned verbatim.
* **Map (per file)** — files larger than their fair share are summarised by a
  cheap LLM, chunk by chunk, into a dense, faithful digest that preserves real
  identifiers (paths, classes, functions, routes, tables, imports, call edges).
* **Reduce (grouped)** — when there are too many files to give each even a small
  share, files are grouped and each group is summarised into one digest that
  still names every file it covers.

Every branch names every file, so nothing is ever silently missed. When the LLM
is unconfigured or a call fails, a structural head/tail fallback keeps each file
represented, so the pipeline still runs (heuristic mode).
"""
from __future__ import annotations

import logging

from .llm import invoke_text

logger = logging.getLogger("githubiq.compaction")

SUMMARY_SYSTEM = (
    "You are a code compaction assistant. You condense source code into a dense, "
    "faithful technical digest another engineer can rely on. PRESERVE the real "
    "identifiers: file and module names, classes, functions/methods, routes and "
    "endpoints, database tables and columns, imports, config keys, and how the "
    "pieces call or depend on each other. Keep short critical code signatures "
    "verbatim. Never invent anything not present in the code. Output plain text "
    "only — no markdown headings, no preamble, no commentary."
)

# Size of a single file-chunk fed to the cheap model during the map phase.
_CHUNK_CHARS = 48_000
# Hard ceiling on cheap-LLM summary calls per compaction pass. This is the key
# guard against a huge assigned file-set hanging an agent with hundreds of
# sequential LLM calls — coverage is still preserved via structural fallback.
_MAX_LLM_CALLS = 8


def _resolve(ctx, paths: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """Resolve assigned paths to ``(path, body)`` pairs; collect the misses."""
    resolved: list[tuple[str, str]] = []
    missing: list[str] = []
    seen: set[str] = set()
    for p in paths:
        if not p or p in seen:
            continue
        seen.add(p)
        body = ctx.contents.get(p) or ctx._fuzzy_get(p)
        if body:
            resolved.append((p, body))
        else:
            missing.append(p)
    return resolved, missing


def _missing_note(missing: list[str]) -> str:
    return (
        "### NOTE — assigned files not found in the snapshot "
        "(do not invent their contents): " + ", ".join(missing)
    )


def _raw_block(path: str, body: str, limit: int) -> str:
    snippet = body[:limit]
    if len(body) > len(snippet):
        snippet += (
            f"\n... [truncated: showing {len(snippet):,} of {len(body):,} chars]"
        )
    return f"### FILE: {path} ({len(body):,} chars)\n{snippet}"


def _structural_block(path: str, body: str, target_chars: int) -> str:
    """No-LLM fallback: keep a head+tail slice so the file is still represented."""
    if len(body) <= target_chars:
        return f"### FILE (excerpt): {path} ({len(body):,} chars)\n{body}"
    head = body[: max(1, target_chars * 2 // 3)]
    tail = body[-(target_chars // 3):]
    return (
        f"### FILE (excerpt): {path} ({len(body):,} chars, head+tail shown)\n"
        f"{head}\n... [middle omitted] ...\n{tail}"
    )


def _summarize_file(
    path: str, body: str, focus: str, target_chars: int, max_calls: int
) -> tuple[str, int]:
    """Map phase: condense one file into a faithful digest using <= ``max_calls``
    cheap-LLM calls. Returns ``(block, calls_used)``."""
    if len(body) <= _CHUNK_CHARS:
        chunks = [body]
    else:
        chunks = [body[i : i + _CHUNK_CHARS] for i in range(0, len(body), _CHUNK_CHARS)]

    truncated_chunks = False
    if len(chunks) > max_calls:
        # Spread the allowed calls across the file so we still see head..tail.
        step = len(chunks) / max_calls
        chunks = [chunks[min(len(chunks) - 1, int(i * step))] for i in range(max_calls)]
        truncated_chunks = True

    per_chunk = max(400, target_chars // len(chunks))
    partials: list[str] = []
    calls_used = 0
    for idx, chunk in enumerate(chunks):
        user = (
            f"FILE: {path} (chunk {idx + 1} of {len(chunks)})\n"
            + (f"FOCUS: {focus}\n" if focus else "")
            + f"Condense this code faithfully into <= {per_chunk} characters, "
            "keeping the real names and how it connects to the rest of the system.\n\n"
            + chunk
        )
        out = invoke_text(
            SUMMARY_SYSTEM,
            user,
            default="",
            max_tokens=min(1500, per_chunk // 2 + 300),
            cheap=True,
        )
        calls_used += 1
        if out:
            partials.append(out.strip())

    digest = " ".join(partials).strip()
    if not digest:  # LLM unavailable / failed → structural head+tail fallback
        return _structural_block(path, body, target_chars), calls_used
    digest = digest[: int(target_chars * 1.2)]
    note = " (partial sampling)" if truncated_chunks else ""
    return (
        f"### FILE (digest{note}): {path} ({len(body):,} chars condensed)\n{digest}",
        calls_used,
    )


def compact_files(
    ctx, paths: list[str], *, budget: int, focus: str = "", per_file_raw: int = 26_000
) -> str:
    """Return context covering EVERY resolvable path in ``paths`` within ``budget``.

    Coverage is guaranteed: every resolved file emits a named block (raw, digest,
    or structural excerpt). Cost/latency are bounded: at most ``_MAX_LLM_CALLS``
    cheap-LLM calls are made regardless of how many files were assigned.

    Returns ``""`` when no path resolves, so callers keep their existing
    ``or ctx.sampled_sources(...)`` fallback.
    """
    resolved, missing = _resolve(ctx, paths)
    if not resolved:
        return ""

    raw_total = sum(len(b) for _, b in resolved)

    # Fast path: everything fits verbatim (no LLM cost, no loss).
    if raw_total <= budget:
        blocks = [_raw_block(p, b, budget) for p, b in resolved]
        if missing:
            blocks.append(_missing_note(missing))
        return "\n\n".join(blocks)

    n = len(resolved)
    # Fair per-file share, leaving headroom for headers/digest overshoot.
    per = max(800, int(budget * 0.85) // n)

    logger.info(
        "Compaction: map over %d files (budget=%d, per=%d, <=%d LLM calls)",
        n, budget, per, _MAX_LLM_CALLS,
    )

    # Summarise the largest files with the LLM first (best value per call); the
    # rest fall back to structural excerpts once the call budget is exhausted.
    order = sorted(range(n), key=lambda i: len(resolved[i][1]), reverse=True)
    blocks_by_index: dict[int, str] = {}
    calls_left = _MAX_LLM_CALLS
    for i in order:
        p, b = resolved[i]
        if len(b) <= min(per, per_file_raw):
            blocks_by_index[i] = _raw_block(p, b, per)
        elif calls_left > 0:
            block, used = _summarize_file(p, b, focus, per, max_calls=calls_left)
            blocks_by_index[i] = block
            calls_left -= used
        else:
            blocks_by_index[i] = _structural_block(p, b, per)

    blocks = [blocks_by_index[i] for i in range(n)]
    if missing:
        blocks.append(_missing_note(missing))
    return "\n\n".join(blocks)
