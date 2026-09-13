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
# Characters of each file included when reducing a group (keeps group calls small).
_GROUP_FILE_SLICE = 8_000
# Target size of one group digest during the reduce phase.
_GROUP_TARGET = 1_500


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


def _summarize_file(path: str, body: str, focus: str, target_chars: int) -> str:
    """Map phase: condense one (possibly large) file into a faithful digest."""
    if len(body) <= _CHUNK_CHARS:
        chunks = [body]
    else:
        chunks = [body[i : i + _CHUNK_CHARS] for i in range(0, len(body), _CHUNK_CHARS)]

    per_chunk = max(400, target_chars // len(chunks))
    partials: list[str] = []
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
        if out:
            partials.append(out.strip())

    digest = " ".join(partials).strip()
    if not digest:  # LLM unavailable / failed → structural head+tail fallback
        head = body[: max(1, target_chars * 2 // 3)]
        tail = body[-(target_chars // 3):] if len(body) > target_chars else ""
        digest = head + ("\n...\n" + tail if tail else "")
    digest = digest[: int(target_chars * 1.2)]
    return f"### FILE (digest): {path} ({len(body):,} chars condensed)\n{digest}"


def _grouped_reduce(
    ctx, resolved: list[tuple[str, str]], missing: list[str], *, budget: int, focus: str
) -> str:
    """Reduce phase: too many files to summarise individually — group them."""
    max_groups = max(1, budget // (_GROUP_TARGET + 120))
    n_groups = min(max_groups, len(resolved))
    groups: list[list[tuple[str, str]]] = [[] for _ in range(n_groups)]
    for i, item in enumerate(resolved):
        groups[i % n_groups].append(item)

    blocks: list[str] = []
    for group in groups:
        names = ", ".join(p for p, _ in group)
        combined = "\n\n".join(
            f"FILE: {p}\n{b[:_GROUP_FILE_SLICE]}" for p, b in group
        )
        user = (
            f"Summarise the following {len(group)} source files together into "
            f"<= {_GROUP_TARGET} characters. "
            + (f"FOCUS: {focus} " if focus else "")
            + "Name EACH file and give its role plus key symbols and connections. "
            f"Files: {names}\n\n{combined}"
        )
        out = invoke_text(SUMMARY_SYSTEM, user, default="", max_tokens=1200, cheap=True)
        if not out:  # fallback still names every file so coverage is preserved
            out = " | ".join(f"{p}: {b[:180].strip()}" for p, b in group)
        blocks.append(
            f"### GROUP DIGEST ({len(group)} files: {names})\n"
            + out.strip()[: int(_GROUP_TARGET * 1.3)]
        )
    if missing:
        blocks.append(_missing_note(missing))
    return "\n\n".join(blocks)


def compact_files(
    ctx, paths: list[str], *, budget: int, focus: str = "", per_file_raw: int = 26_000
) -> str:
    """Return context covering EVERY resolvable path in ``paths`` within ``budget``.

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
    # Fair per-file share, leaving ~20% headroom for headers/digest overshoot.
    per = max(1_200, int(budget * 0.8) // n)

    # Too many files to give each a usable share → group & reduce.
    if per <= 1_200 and n * per > budget:
        logger.info("Compaction: grouped-reduce over %d files (budget=%d)", n, budget)
        return _grouped_reduce(ctx, resolved, missing, budget=budget, focus=focus)

    logger.info("Compaction: per-file map over %d files (budget=%d)", n, budget)
    blocks: list[str] = []
    for p, b in resolved:
        if len(b) <= min(per, per_file_raw):
            blocks.append(_raw_block(p, b, per))
        else:
            blocks.append(_summarize_file(p, b, focus, per))
    if missing:
        blocks.append(_missing_note(missing))
    return "\n\n".join(blocks)
