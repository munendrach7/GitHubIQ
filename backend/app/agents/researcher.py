"""Researcher agent — crawls the repo like an engineer and delegates context.

This is the tool's core differentiator. It reads the tree plus anchor files
(README, manifests, entry points), then:
  - explains what the project is / does / how it works, in plain language,
  - breaks the repo into its real software components,
  - locates entry points,
  - decides which specific files each specialist agent should read.

Downstream specialists work from these curated file assignments instead of a
blind heuristic sample, so important context is not missed.
"""
from __future__ import annotations

import re

from ..llm import invoke_json
from ..models import Component, ResearchBrief
from ..prompts import render
from .state import GraphState

SYSTEM = (
    "You are the Researcher agent — a staff engineer onboarding to a new "
    "repository. You read the file tree and key files, trace the entry points, "
    "and build a precise mental model of the project. You break the repo into its "
    "real software components (frontend, backend services, workers, libraries, "
    "CLIs, infra, database) and decide exactly which files each downstream "
    "specialist must read to do deep work. Be concrete and use real paths from the "
    "tree. Respond ONLY with strict JSON."
)

ENTRY_HINTS = re.compile(
    r"(main\.(py|go|js|ts|rs|java)|manage\.py|app\.(py|js|ts)|index\.(js|ts|tsx)|"
    r"server\.(js|ts|py)|cmd/|wsgi\.py|asgi\.py|__main__\.py|program\.cs)",
    re.IGNORECASE,
)

DB_HINTS = re.compile(
    r"(migration|schema\.|models?\.|entity|\.sql|prisma|alembic|sequelize|"
    r"typeorm|sqlmodel|sqlalchemy|gorm|ecto|activerecord)",
    re.IGNORECASE,
)

SPECIALISTS = ["architect", "schema", "dataflow", "tutor", "walkthrough"]


def _top_dirs(tree: list[str]) -> list[str]:
    dirs: dict[str, int] = {}
    for p in tree:
        if "/" in p:
            dirs[p.split("/")[0]] = dirs.get(p.split("/")[0], 0) + 1
    return [d for d, _ in sorted(dirs.items(), key=lambda kv: kv[1], reverse=True)][:14]


def _heuristic(ctx) -> ResearchBrief:
    entry_points = [p for p in ctx.tree if ENTRY_HINTS.search(p)][:8]
    modules = _top_dirs(ctx.tree)
    has_db = any(DB_HINTS.search(p) for p in ctx.tree)
    interesting = [
        p for p in ctx.contents
    ][:14]
    components = [
        Component(
            id=m,
            name=m.replace("_", " ").replace("-", " ").title(),
            kind="module",
            path=m,
            tech=ctx.meta.languages[:2],
            responsibility=f"Top-level module '{m}'.",
            key_files=[p for p in ctx.tree if p.startswith(m + "/")][:5],
        )
        for m in modules[:6]
    ]
    return ResearchBrief(
        what=ctx.meta.description or f"{ctx.meta.name} repository.",
        does=ctx.meta.description or "",
        how=f"Organised into {len(modules)} top-level modules.",
        entry_points=entry_points,
        modules=modules,
        languages=ctx.meta.languages,
        components=components,
        has_database=has_db,
        file_assignments={s: interesting for s in SPECIALISTS},
    )


def run(state: GraphState) -> dict:
    ctx = state["ctx"]
    reporter = state["reporter"]
    reporter.update("Researcher", "running", "Crawling repo from entry points & delegating files")

    prefs = state.get("preferences")
    custom = (getattr(prefs, "custom_instructions", "") or "").strip()
    custom_block = (
        "\nUSER'S CUSTOM INSTRUCTIONS (highest priority — tailor your analysis, "
        "component focus and file assignments to satisfy these):\n"
        f"{custom}\n"
        if custom
        else ""
    )

    fallback = _heuristic(ctx)
    prompt = render(
        "researcher_user",
        owner=ctx.meta.owner,
        repo=ctx.meta.name,
        description=ctx.meta.description or "(none)",
        languages=", ".join(ctx.meta.languages) or "unknown",
        filecount=ctx.meta.file_count,
        custom_instructions=custom_block,
        tree=ctx.file_listing(900),
        anchors=ctx.anchor_sources(total_budget=150_000),
    )
    data = invoke_json(render("researcher_system"), prompt, default=None)

    if isinstance(data, dict) and data.get("components"):
        try:
            brief = ResearchBrief(
                what=data.get("what") or fallback.what,
                does=data.get("does") or fallback.does,
                how=data.get("how") or fallback.how,
                entry_points=data.get("entry_points") or fallback.entry_points,
                modules=data.get("modules") or fallback.modules,
                languages=data.get("languages") or ctx.meta.languages,
                components=[Component.model_validate(c) for c in data["components"]],
                has_database=bool(data.get("has_database", fallback.has_database)),
                notes=data.get("notes", ""),
                file_assignments=data.get("file_assignments") or fallback.file_assignments,
            )
        except Exception:  # noqa: BLE001
            brief = fallback
    else:
        brief = fallback

    reporter.update(
        "Researcher", "done", f"{len(brief.components)} components, {len(brief.entry_points)} entry points"
    )
    return {"research": brief}
