"""Architect agent — maps components, layers and how they interact in depth."""
from __future__ import annotations

from ..llm import invoke_json
from ..compaction import compact_files
from ..models import Architecture, ServiceEdge, ServiceNode
from ..prompts import render
from ..scale import compute_scale
from .state import GraphState

SYSTEM = (
    "You are the Architect agent. Using the researcher's component breakdown and "
    "the assigned source files, you produce an in-depth architecture map: every "
    "significant node (with its tech stack, layer, and what calls it / what it "
    "calls) and the directed interactions between them (sync requests, async "
    "events, data access, supporting calls). Respond ONLY with strict JSON."
)


def _heuristic(ctx, brief) -> Architecture:
    nodes: list[ServiceNode] = []
    for c in (brief.components or [])[:8]:
        nodes.append(
            ServiceNode(
                id=c.id,
                label=c.name,
                path=c.path,
                language=(c.tech or [ctx.meta.primary_language])[0] if c.tech else "",
                role=c.kind,
                component=c.name,
                tech=c.tech,
                summary=c.responsibility,
                layer="service",
            )
        )
    if not nodes:
        nodes.append(ServiceNode(id="app", label=ctx.meta.name, role="application",
                                 summary=ctx.meta.description, layer="service"))
    edges = [
        ServiceEdge(source=nodes[i].id, target=nodes[i + 1].id, label="uses",
                    kind="support")
        for i in range(len(nodes) - 1)
    ]
    return Architecture(summary=brief.how or f"{ctx.meta.name} architecture.",
                        nodes=nodes, edges=edges, layers=["entry", "service", "data"])


def run(state: GraphState) -> dict:
    ctx = state["ctx"]
    reporter = state["reporter"]
    brief = state["research"]
    reporter.update("Architect", "running", "Mapping components, layers & edges")

    scale = compute_scale(ctx.meta.file_count, getattr(state.get("preferences"), "depth", None))
    fallback = _heuristic(ctx, brief)
    comp_desc = "\n".join(
        f"- {c.id}: {c.name} [{c.kind}] path={c.path} tech={', '.join(c.tech)} — {c.responsibility}"
        for c in brief.components
    )
    sources = compact_files(
        ctx,
        brief.file_assignments.get("architect", []),
        budget=240_000,
        focus="how services/modules wire together: entry points, app/server setup, "
        "routers, dependency injection, inter-component calls and configuration",
    ) or ctx.sampled_sources(12)
    prompt = render(
        "architect_user",
        owner=ctx.meta.owner,
        repo=ctx.meta.name,
        what=brief.what,
        how=brief.how,
        notes=brief.notes or "(none)",
        components=comp_desc,
        sources=sources,
        size_label=scale.size_label,
        node_min=scale.nodes[0],
        node_max=scale.nodes[1],
    )
    data = invoke_json(render("architect_system"), prompt, default=None)

    arch = fallback
    if isinstance(data, dict) and data.get("nodes"):
        try:
            arch = Architecture.model_validate(
                {
                    "summary": data.get("summary", fallback.summary),
                    "layers": data.get("layers", ["entry", "service", "data"]),
                    "nodes": data["nodes"],
                    "edges": data.get("edges", []),
                }
            )
        except Exception:  # noqa: BLE001
            arch = fallback

    reporter.update("Architect", "done", f"{len(arch.nodes)} nodes, {len(arch.edges)} edges")
    return {"architecture": arch}
