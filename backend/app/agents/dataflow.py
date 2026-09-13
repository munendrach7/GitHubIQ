"""Data-Flow agent — traces every API endpoint / entry operation end to end."""
from __future__ import annotations

from ..llm import invoke_json
from ..compaction import compact_files
from ..models import DataFlow, EndpointFlow, FlowStep
from ..prompts import render
from ..scale import compute_scale
from .state import GraphState

SYSTEM = (
    "You are the Data-Flow agent. You enumerate the application's API endpoints / "
    "entry operations and trace each one's logic flow through the codebase hop by "
    "hop. Respond ONLY with strict JSON."
)


def _heuristic(ctx, arch) -> DataFlow:
    actors = [n.label for n in arch.nodes[:5]] or ["Client", "App"]
    steps = [
        FlowStep(index=i + 1, actor=actor, label="handles the request", kind="sync")
        for i, actor in enumerate(actors)
    ]
    primary = EndpointFlow(
        id="main",
        title=f"A request through {ctx.meta.name}",
        trigger="A user action",
        summary="High-level path across the main components.",
        steps=steps,
        rationale="Generated from the component graph.",
    )
    return DataFlow(
        title=primary.title,
        trigger=primary.trigger,
        summary=primary.summary,
        steps=primary.steps,
        rationale=primary.rationale,
        endpoints=[primary],
    )


def run(state: GraphState) -> dict:
    ctx = state["ctx"]
    reporter = state["reporter"]
    arch = state["architecture"]
    brief = state["research"]
    schema = state.get("schema")
    reporter.update("Data-Flow", "running", "Tracing every endpoint end to end")

    scale = compute_scale(ctx.meta.file_count, getattr(state.get("preferences"), "depth", None))
    fallback = _heuristic(ctx, arch)
    node_summary = "\n".join(
        f"- {n.id}: {n.label} ({n.role}, layer={n.layer})" for n in arch.nodes
    )
    tables = ", ".join(t.name for t in schema.tables) if schema and schema.tables else "(none)"
    sources = compact_files(
        ctx,
        brief.file_assignments.get("dataflow", []),
        budget=240_000,
        focus="every API endpoint / route / controller / resolver / consumer / CLI "
        "command and the end-to-end path each one takes (handler -> service -> data)",
    ) or ctx.sampled_sources(12)
    # How many distinct endpoints to trace scales with repo size / depth.
    endpoint_max = min(16, max(4, scale.steps[1]))
    prompt = render(
        "dataflow_user",
        owner=ctx.meta.owner,
        repo=ctx.meta.name,
        what=brief.what,
        nodes=node_summary,
        tables=tables,
        sources=sources,
        endpoint_max=endpoint_max,
        step_min=scale.steps[0],
        step_max=scale.steps[1],
    )
    data = invoke_json(render("dataflow_system"), prompt, default=None)

    endpoints: list[EndpointFlow] = []
    if isinstance(data, dict) and isinstance(data.get("endpoints"), list):
        for i, ep in enumerate(data["endpoints"][:endpoint_max]):
            if not isinstance(ep, dict) or not ep.get("steps"):
                continue
            try:
                endpoints.append(
                    EndpointFlow.model_validate(
                        {
                            "id": ep.get("id") or f"ep{i + 1}",
                            "method": (ep.get("method") or "").upper(),
                            "route": ep.get("route", ""),
                            "title": ep.get("title") or ep.get("route") or f"Flow {i + 1}",
                            "trigger": ep.get("trigger", ""),
                            "summary": ep.get("summary", ""),
                            "steps": ep.get("steps", []),
                            "rationale": ep.get("rationale", ""),
                        }
                    )
                )
            except Exception:  # noqa: BLE001
                continue

    if endpoints:
        primary = endpoints[0]
        flow = DataFlow(
            title=primary.title or fallback.title,
            trigger=primary.trigger,
            summary=primary.summary or fallback.summary,
            steps=primary.steps,
            rationale=primary.rationale,
            endpoints=endpoints,
        )
    else:
        flow = fallback

    reporter.update(
        "Data-Flow", "done", f"{len(flow.endpoints)} endpoint flow(s) traced"
    )
    return {"dataflow": flow}
