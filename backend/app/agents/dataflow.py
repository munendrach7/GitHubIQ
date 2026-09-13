"""Data-Flow agent — traces the main request/operation end to end, in depth."""
from __future__ import annotations

from ..llm import invoke_json
from ..models import DataFlow, FlowStep
from .state import GraphState

SYSTEM = (
    "You are the Data-Flow agent. Using the architecture and the assigned source "
    "files, you trace the single most important operation through the codebase "
    "hop by hop. For each hop you show: which component/file handles it, the data "
    "entering and leaving, a short real code snippet, whether it is sync or async, "
    "and a deeper explanation a newcomer can click to expand. Respond ONLY with "
    "strict JSON."
)


def _heuristic(ctx, arch) -> DataFlow:
    actors = [n.label for n in arch.nodes[:5]] or ["Client", "App"]
    steps = [
        FlowStep(index=i + 1, actor=actor, label="handles the request", kind="sync")
        for i, actor in enumerate(actors)
    ]
    return DataFlow(
        title=f"A request through {ctx.meta.name}",
        trigger="A user action",
        summary="High-level path across the main components.",
        steps=steps,
        rationale="Generated from the component graph.",
    )


def run(state: GraphState) -> dict:
    ctx = state["ctx"]
    reporter = state["reporter"]
    arch = state["architecture"]
    brief = state["research"]
    reporter.update("Data-Flow", "running", "Tracing the main operation end to end")

    fallback = _heuristic(ctx, arch)
    node_summary = "\n".join(
        f"- {n.id}: {n.label} ({n.role}, layer={n.layer})" for n in arch.nodes
    )
    sources = ctx.read_files(
        brief.file_assignments.get("dataflow", []), total_budget=75_000
    ) or ctx.sampled_sources(12)
    prompt = (
        f"Repository: {ctx.meta.owner}/{ctx.meta.name}\n"
        f"What it is: {brief.what}\n\n"
        f"COMPONENTS:\n{node_summary}\n\n"
        f"ASSIGNED SOURCE FILES (the real implementation of the flow):\n{sources}\n\n"
        "Pick the single most illustrative operation (e.g. create/fetch a core "
        "resource, or the main CLI/library call). Return JSON: "
        "{\"title\": str, \"trigger\": str, \"summary\": str, "
        "\"steps\": [{\"index\": int, \"actor\": str, \"label\": str, "
        "\"kind\": \"sync\"|\"async\", \"files\": [\"real/path\"], "
        "\"data_in\": \"payload/state entering\", \"data_out\": \"payload/state leaving\", "
        "\"code\": \"short real snippet with example values\", "
        "\"detail\": \"2-4 sentence deeper explanation of what happens here\"}], "
        "\"rationale\": str, \"alternatives\": [\"other notable flows\"]}. "
        "Use 5-8 steps grounded in the actual files. 'files' must be real paths."
    )
    data = invoke_json(SYSTEM, prompt, default=None)

    flow = fallback
    if isinstance(data, dict) and data.get("steps"):
        try:
            flow = DataFlow.model_validate(
                {
                    "title": data.get("title", fallback.title),
                    "trigger": data.get("trigger", ""),
                    "summary": data.get("summary", fallback.summary),
                    "steps": data["steps"],
                    "rationale": data.get("rationale", fallback.rationale),
                    "alternatives": data.get("alternatives", []),
                }
            )
        except Exception:  # noqa: BLE001
            flow = fallback

    reporter.update("Data-Flow", "done", f"{len(flow.steps)} hops traced")
    return {"dataflow": flow}
