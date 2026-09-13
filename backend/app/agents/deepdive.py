"""Deep-Dive agent — one in-depth, code-grounded section per component.

This is what makes the guide scale with the repository. The Researcher identifies
the real components (their count grows with repo size via ``app/scale.py``); here
we generate a thorough, per-component section from that component's actual source
files. A 6-file utility gets a short section; a large service gets a long one — so
a big repo yields a big, comprehensive guide instead of a fixed-size summary.

Each component is processed concurrently (bounded thread pool) because the calls
are independent; results are merged into the guide by the orchestrator's compose
step. Falls back to a structured heuristic body when no LLM is configured.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from ..compaction import compact_files
from ..llm import invoke_json
from ..prompts import render
from ..scale import compute_scale
from .state import GraphState, check_cancelled

logger = logging.getLogger("githubiq.deepdive")

_MAX_WORKERS = 5


def _connections(arch, name: str) -> tuple[list[str], list[str]]:
    """Return (calls, called_by) component names for a component, from the arch."""
    id_to_comp = {n.id: (n.component or "") for n in arch.nodes}
    calls: list[str] = []
    called_by: list[str] = []
    for n in arch.nodes:
        if (n.component or "").lower() != name.lower():
            continue
        for t in n.outbound:
            c = id_to_comp.get(t, "")
            if c and c.lower() != name.lower() and c not in calls:
                calls.append(c)
        for s in n.inbound:
            c = id_to_comp.get(s, "")
            if c and c.lower() != name.lower() and c not in called_by:
                called_by.append(c)
    return calls, called_by


def _component_paths(ctx, comp) -> list[str]:
    """Every source file that belongs to a component: its key files + its folder."""
    paths = list(comp.key_files or [])
    root = (comp.path or "").rstrip("/")
    if root:
        paths += [p for p in ctx.contents if p == root or p.startswith(root + "/")]
    # de-dup preserving order
    return list(dict.fromkeys(p for p in paths if p))


def _heuristic_body(comp, calls: list[str], called_by: list[str]) -> str:
    parts = [comp.responsibility or f"The {comp.name} component."]
    if comp.tech:
        parts.append("**Tech:** " + ", ".join(f"`{t}`" for t in comp.tech))
    if called_by:
        parts.append("**Called by:** " + ", ".join(called_by))
    if calls:
        parts.append("**Calls / depends on:** " + ", ".join(calls))
    if comp.key_files:
        parts.append(
            "**Key files**\n" + "\n".join(f"- `{f}`" for f in comp.key_files[:12])
        )
    return "\n\n".join(parts)


def run(state: GraphState) -> dict:
    ctx = state["ctx"]
    reporter = state["reporter"]
    brief = state["research"]
    arch = state["architecture"]
    prefs = state["preferences"]
    reporter.update("Deep-Dive", "running", "Writing an in-depth section per component")
    check_cancelled(reporter)

    scale = compute_scale(ctx.meta.file_count, getattr(prefs, "depth", None))
    components = list(brief.components or [])[: max(1, scale.max_deepdives)]

    def work(comp) -> tuple[str, str]:
        calls, called_by = _connections(arch, comp.name)
        conn = "; ".join(
            filter(
                None,
                [
                    ("called by: " + ", ".join(called_by)) if called_by else "",
                    ("calls: " + ", ".join(calls)) if calls else "",
                ],
            )
        ) or "(no cross-component edges detected)"
        sources = compact_files(
            ctx,
            _component_paths(ctx, comp),
            budget=scale.deep_budget,
            focus=f"everything a contributor must know to work on the {comp.name} "
            f"component: its files, key symbols, internal flow and connections",
        ) or ctx.sampled_sources(6)
        prompt = render(
            "deepdive_user",
            owner=ctx.meta.owner,
            repo=ctx.meta.name,
            size_label=scale.size_label,
            what=brief.what,
            role=getattr(prefs.role, "value", "new_to_team"),
            familiarity=getattr(prefs.familiarity, "value", "some_exposure"),
            reader_depth=getattr(prefs.depth, "value", "guided"),
            goals=", ".join(prefs.goals) or "general onboarding",
            component_name=comp.name,
            kind=comp.kind or "component",
            path=comp.path or "(various)",
            tech=", ".join(comp.tech) or ctx.meta.primary_language,
            responsibility=comp.responsibility or "(not specified)",
            connections=conn,
            sources=sources,
        )
        data = invoke_json(render("deepdive_system"), prompt, default=None)
        body = None
        if isinstance(data, dict):
            body = data.get("body")
            extra = data.get("key_files") or []
            if body and extra:
                lines = [
                    f"- `{kf.get('path')}` — {kf.get('role', '')}".rstrip(" —")
                    for kf in extra
                    if isinstance(kf, dict) and kf.get("path")
                ]
                if lines and "key file" not in body.lower():
                    body += "\n\n**Key files**\n" + "\n".join(lines)
        return comp.name, (body or _heuristic_body(comp, calls, called_by))

    deepdives: dict[str, str] = {}
    if components:
        # Pre-compute the heuristic bodies so any component that times out, errors,
        # or gets cancelled still ends up with a real (if shorter) section.
        fallbacks = {
            c.name: _heuristic_body(c, *_connections(arch, c.name)) for c in components
        }
        workers = min(_MAX_WORKERS, len(components))
        phase_end = time.monotonic() + max(30, scale.deepdive_deadline)
        ex = ThreadPoolExecutor(max_workers=workers)
        futures = {ex.submit(work, c): c for c in components}
        pending = set(futures)
        try:
            # Poll in short slices with wait() rather than blocking on a single
            # future: this both (a) stops the phase hanging if every call stalls
            # (what pinned runs at 75%) and (b) honours a user cancel within ~2s
            # even while calls are still in flight, so a worker stops promptly.
            while pending:
                if reporter.cancelled():
                    break
                if time.monotonic() >= phase_end:
                    logger.warning(
                        "Deep-Dive deadline reached; filling remainder heuristically"
                    )
                    break
                done, pending = wait(pending, timeout=2, return_when=FIRST_COMPLETED)
                for fut in done:
                    comp = futures[fut]
                    try:
                        name, body = fut.result()
                    except Exception as exc:  # noqa: BLE001 - degrade to heuristic body
                        logger.error("Deep-Dive failed for %s: %s", comp.name, exc)
                        name, body = comp.name, fallbacks[comp.name]
                    deepdives[name] = body
                    reporter.update(
                        "Deep-Dive", "running", f"deep dive: {name} ({len(deepdives)})"
                    )
        finally:
            # Never block the pipeline on stragglers — abandon them and move on.
            ex.shutdown(wait=False, cancel_futures=True)

        # Guarantee coverage: any component we didn't finish gets its heuristic body.
        for c in components:
            deepdives.setdefault(c.name, fallbacks[c.name])

    reporter.update("Deep-Dive", "done", f"{len(deepdives)} component deep dives")
    return {"component_deepdives": deepdives}
