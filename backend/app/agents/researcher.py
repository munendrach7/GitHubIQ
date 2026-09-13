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
from ..scale import compute_scale
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
    r"(migration|schema[\._]|models?[\._/]|entit(y|ies)|repositor(y|ies)|\.sql\b|"
    r"prisma|alembic|sequelize|typeorm|mikro-?orm|sqlmodel|sqlalchemy|gorm|ecto|"
    r"activerecord|dapper|hibernate|\bjpa\b|mongoose|beanie|peewee|\bpony\b|knex|"
    r"drizzle|dbcontext|dbset|efcore|entityframework|appsettings|connectionstring|"
    r"mongo|cosmos|dynamo|firestore|firebase|\bredis\b|cassandra|couch|neo4j|"
    r"sqlite|litedb|realm|\.db\b|\.sqlite\b|duckdb|"
    r"chroma|pinecone|qdrant|weaviate|milvus|faiss|vector[\s_-]?store|embeddings?|"
    r"\bdao\b|persistence|datastore|data[-_]?context)",
    re.IGNORECASE,
)

# Files most relevant to tracing the main request/data-flow.
FLOW_HINTS = re.compile(
    r"(route|router|controller|handler|service|view|endpoint|api|resolver|"
    r"consumer|worker|task|middleware|use[_-]?case)",
    re.IGNORECASE,
)

# Files that best convey what the app is / does (for the presenter/UI).
PRESENT_HINTS = re.compile(
    r"(readme|index\.(js|ts|jsx|tsx)|app\.(js|ts|jsx|tsx)|page|screen|component|"
    r"ui/|frontend/|views?/|templates?/)",
    re.IGNORECASE,
)

# Specialists that actually READ assigned files in the active pipeline.
FILE_READING_SPECIALISTS = ["architect", "schema", "dataflow", "tutor"]

SPECIALISTS = ["architect", "schema", "dataflow", "tutor", "walkthrough"]


def _top_dirs(tree: list[str]) -> list[str]:
    dirs: dict[str, int] = {}
    for p in tree:
        if "/" in p:
            dirs[p.split("/")[0]] = dirs.get(p.split("/")[0], 0) + 1
    return [d for d, _ in sorted(dirs.items(), key=lambda kv: kv[1], reverse=True)][:36]


def _heuristic(ctx) -> ResearchBrief:
    scale = compute_scale(ctx.meta.file_count, None)
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
        for m in modules[: scale.components[1]]
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
        database="",
        file_assignments={s: interesting for s in SPECIALISTS},
    )


def _route_specialist(path: str) -> str:
    """Pick the most relevant file-reading specialist for a captured file."""
    low = path.lower()
    if DB_HINTS.search(low):
        return "schema"
    if FLOW_HINTS.search(low):
        return "dataflow"
    return "architect"


def _ensure_full_coverage(ctx, brief: ResearchBrief) -> None:
    """Guarantee EVERY captured source file is assigned to ≥1 specialist.

    ``ctx.contents`` holds only the files that scored as significant source at
    fetch time. We union the Researcher's curated picks with a routed assignment
    for any captured file it missed, so no significant file is left unread. The
    compaction layer keeps these larger lists within each specialist's budget.
    """
    assignments = brief.file_assignments or {}
    for key in SPECIALISTS:
        assignments.setdefault(key, list(assignments.get(key, [])))

    assigned_all = {
        p for key in FILE_READING_SPECIALISTS for p in assignments.get(key, [])
    }
    # Normalise for membership tests (basename match tolerates path variants).
    assigned_bases = {a.lower().rsplit("/", 1)[-1] for a in assigned_all}

    for path in ctx.contents:
        if path in assigned_all or path.lower().rsplit("/", 1)[-1] in assigned_bases:
            continue
        assignments[_route_specialist(path)].append(path)

    brief.file_assignments = assignments


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
    scale = compute_scale(ctx.meta.file_count, getattr(prefs, "depth", None))
    prompt = render(
        "researcher_user",
        owner=ctx.meta.owner,
        repo=ctx.meta.name,
        description=ctx.meta.description or "(none)",
        languages=", ".join(ctx.meta.languages) or "unknown",
        filecount=ctx.meta.file_count,
        custom_instructions=custom_block,
        tree=ctx.file_listing(max(1400, ctx.meta.file_count or 0)),
        anchors=ctx.anchor_sources(total_budget=260_000),
        size_label=scale.size_label,
        component_min=scale.components[0],
        component_max=scale.components[1],
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
                database=data.get("database", "") or fallback.database,
                notes=data.get("notes", ""),
                file_assignments=data.get("file_assignments") or fallback.file_assignments,
            )
        except Exception:  # noqa: BLE001
            brief = fallback
    else:
        brief = fallback

    # Coverage safety net: make sure no captured source file is left unassigned.
    _ensure_full_coverage(ctx, brief)

    reporter.update(
        "Researcher", "done", f"{len(brief.components)} components, {len(brief.entry_points)} entry points"
    )
    return {"research": brief}
