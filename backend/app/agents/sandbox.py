"""Walkthrough agent — a high-level visual tour of what the app looks like."""
from __future__ import annotations

from ..llm import invoke_json
from ..compaction import compact_files
from ..models import Sandbox, ScreenElement, WalkthroughScreen
from .state import GraphState

SYSTEM = (
    "You are the Walkthrough agent. Your job is to help a newcomer VISUALISE the "
    "application: what its main screens/surfaces look like, what is on each, what "
    "the user does there, and how they move between them. For a web/mobile app "
    "these are pages/screens; for an API they are key endpoints; for a CLI they are "
    "commands; for a library they are the main usage surfaces. Infer this from the "
    "UI/route/entry files. Respond ONLY with strict JSON — no code needed."
)


def _heuristic(ctx, brief, arch) -> Sandbox:
    screens = []
    for i, c in enumerate((brief.components or [])[:4]):
        screens.append(
            WalkthroughScreen(
                id=f"s{i}",
                title=c.name,
                kind="page",
                description=c.responsibility,
                elements=[ScreenElement(label=c.kind, kind="text")],
                user_actions=["Explore this surface"],
            )
        )
    if not screens:
        screens.append(
            WalkthroughScreen(id="s0", title=ctx.meta.name, kind="page",
                              description=ctx.meta.description or brief.what)
        )
    return Sandbox(
        title=f"How {ctx.meta.name} looks",
        summary="A high-level tour of the app's main surfaces.",
        app_type="application",
        screens=screens,
        challenge="Map each screen back to the component that renders it.",
    )


def run(state: GraphState) -> dict:
    ctx = state["ctx"]
    reporter = state["reporter"]
    flow = state["dataflow"]
    brief = state["research"]
    arch = state["architecture"]
    reporter.update("Walkthrough", "running", "Visualising the app's main screens")

    fallback = _heuristic(ctx, brief, arch)
    sources = compact_files(
        ctx,
        brief.file_assignments.get("walkthrough", []),
        budget=140_000,
        focus="the app's user-facing surfaces: UI screens, routes/endpoints, "
        "commands and what the user does on each",
    ) or ctx.sampled_sources(10)
    flow_desc = "\n".join(f"{s.index}. {s.actor}: {s.label}" for s in flow.steps)
    prompt = (
        f"Repository: {ctx.meta.owner}/{ctx.meta.name}\n"
        f"What it is: {brief.what}\nWhat it does: {brief.does}\n"
        f"Components: {', '.join(c.name for c in brief.components)}\n"
        f"Main flow: {flow.title}\n{flow_desc}\n\n"
        f"UI / ROUTE / ENTRY FILES:\n{sources}\n\n"
        "Return JSON: {\"title\": str, \"summary\": str, "
        "\"app_type\": \"web app\"|\"api\"|\"cli\"|\"library\"|\"mobile\"|\"service\", "
        "\"screens\": [{\"id\": slug, \"title\": str, \"route\": \"URL/route or command\", "
        "\"kind\": \"page\"|\"modal\"|\"cli\"|\"state\"|\"dashboard\", "
        "\"description\": \"what the user sees & why it matters\", "
        "\"elements\": [{\"label\": str, \"kind\": "
        "\"button\"|\"input\"|\"list\"|\"nav\"|\"card\"|\"text\"|\"chart\", \"note\": str}], "
        "\"user_actions\": [\"what the user can do here\"], "
        "\"leads_to\": \"id of the next screen\"}], "
        "\"challenge\": str}. "
        "Produce 3-6 screens that capture the real primary surfaces of THIS app, "
        "grounded in the route/UI files. Order them as a natural user journey."
    )
    data = invoke_json(SYSTEM, prompt, default=None)

    sandbox = fallback
    if isinstance(data, dict) and data.get("screens"):
        try:
            candidate = Sandbox.model_validate(
                {
                    "title": data.get("title", fallback.title),
                    "summary": data.get("summary", fallback.summary),
                    "app_type": data.get("app_type", ""),
                    "screens": data["screens"],
                    "challenge": data.get("challenge", fallback.challenge),
                }
            )
            if candidate.screens:
                sandbox = candidate
        except Exception:  # noqa: BLE001
            sandbox = fallback

    reporter.update("Walkthrough", "done", f"{len(sandbox.screens)} screens")
    return {"sandbox": sandbox}
