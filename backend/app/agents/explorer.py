"""Explorer agent — maps repository structure, entry points and modules."""
from __future__ import annotations

import re

from ..llm import invoke_json
from ..models import ExplorerFindings
from .state import GraphState

SYSTEM = (
    "You are the Explorer agent in a code-onboarding tool. You map a repository's "
    "structure: entry points (where execution starts), top-level modules, and the "
    "languages used. Respond ONLY with JSON matching the requested schema."
)

ENTRY_HINTS = re.compile(
    r"(main\.(py|go|js|ts)|manage\.py|app\.(py|js|ts)|index\.(js|ts)|server\.(js|ts|py)|"
    r"cmd/|wsgi\.py|asgi\.py|__main__\.py)",
    re.IGNORECASE,
)


def _heuristic(ctx) -> ExplorerFindings:
    entry_points = [p for p in ctx.tree if ENTRY_HINTS.search(p)][:8]
    modules = sorted(
        {p.split("/")[0] for p in ctx.tree if "/" in p and not p.startswith(".")}
    )[:12]
    return ExplorerFindings(
        summary=(
            f"{ctx.meta.name} is a {ctx.meta.primary_language or 'multi-language'} "
            f"project with {ctx.meta.file_count} files across {len(modules)} top-level modules."
        ),
        entry_points=entry_points,
        modules=modules,
        languages=ctx.meta.languages,
    )


def run(state: GraphState) -> dict:
    ctx = state["ctx"]
    reporter = state["reporter"]
    reporter.update("Explorer", "running", "Mapping repo tree & entry points")

    fallback = _heuristic(ctx)
    prompt = (
        f"Repository: {ctx.meta.owner}/{ctx.meta.name}\n"
        f"Description: {ctx.meta.description}\n"
        f"Languages: {', '.join(ctx.meta.languages) or 'unknown'}\n\n"
        f"File tree (sample):\n{ctx.file_listing(160)}\n\n"
        "Return JSON: {\"summary\": str, \"entry_points\": [str], "
        "\"modules\": [str], \"languages\": [str]}. "
        "entry_points are file paths where execution begins. modules are the key "
        "top-level directories a newcomer should understand."
    )
    data = invoke_json(SYSTEM, prompt, default=None)

    if isinstance(data, dict):
        findings = ExplorerFindings(
            summary=data.get("summary") or fallback.summary,
            entry_points=data.get("entry_points") or fallback.entry_points,
            modules=data.get("modules") or fallback.modules,
            languages=data.get("languages") or fallback.languages,
        )
    else:
        findings = fallback

    detail = findings.entry_points[0] if findings.entry_points else "structure mapped"
    reporter.update("Explorer", "done", f"entry point {detail}")
    return {"explorer": findings}
