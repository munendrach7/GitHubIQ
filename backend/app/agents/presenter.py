"""Presenter agent — scripts a short persona-narrated video explainer.

Produces a VideoExplainer: an ordered set of scenes with narration (spoken by a
male presenter), on-screen bullets and a visual type. The frontend renders each
scene as an animated slide with graphics drawn from the analysis, plays the
narration via Azure Speech (text-to-speech), and advances automatically.
"""
from __future__ import annotations

from ..llm import invoke_json
from ..models import VideoExplainer, VideoScene
from ..prompts import render
from .state import GraphState

PERSONA = "Alex"

SYSTEM = (
    "You are the Presenter agent. You write the script for a short (about 60-90 "
    "second) explainer video in which a friendly male engineer named Alex gives a "
    "newcomer a quick, high-level overview of a software project. Alex speaks in "
    "first person, warm and conversational, in plain language. Each scene has "
    "spoken narration (2-4 sentences, no markdown, no emoji) plus a few short "
    "on-screen bullet points. Respond ONLY with strict JSON."
)


def _heuristic(ctx, brief, arch, flow, schema) -> VideoExplainer:
    scenes = [
        VideoScene(
            id="intro", title=ctx.meta.name, visual="intro", accent="blue",
            narration=f"Hi, I'm Alex. Let me give you a quick tour of {ctx.meta.name}. {brief.what}",
            bullets=[brief.does or ctx.meta.description][:1],
        ),
        VideoScene(
            id="components", title="The moving parts", visual="components", accent="purple",
            narration="Here are the main components that make up the project and what each one is responsible for.",
            bullets=[f"{c.name} — {c.kind}" for c in brief.components[:5]],
        ),
        VideoScene(
            id="architecture", title="How it fits together", visual="architecture", accent="green",
            narration=arch.summary or "This is how those components connect and talk to each other.",
            bullets=[f"{n.label}" for n in arch.nodes[:5]],
        ),
        VideoScene(
            id="dataflow", title=flow.title or "A typical request", visual="dataflow", accent="orange",
            narration=flow.summary or "Let's follow one typical operation from start to finish.",
            bullets=[f"{s.actor}: {s.label}" for s in flow.steps[:5]],
        ),
    ]
    if schema.tables:
        scenes.append(
            VideoScene(
                id="schema", title="The data model", visual="schema", accent="pink",
                narration=schema.plain_english or "And here's the data model behind it all.",
                bullets=[t.name for t in schema.tables[:6]],
            )
        )
    scenes.append(
        VideoScene(
            id="outro", title="You're ready", visual="outro", accent="blue",
            narration="That's the big picture. Dive into the guide to explore each part in depth. Happy coding!",
            bullets=["Open the guide", "Explore the architecture", "Trace the data flow"],
        )
    )
    return VideoExplainer(
        title=f"{ctx.meta.name} — a 60-second tour",
        persona=PERSONA,
        tagline=brief.what,
        scenes=scenes,
    )


def run(state: GraphState) -> dict:
    ctx = state["ctx"]
    reporter = state["reporter"]
    brief = state["research"]
    arch = state["architecture"]
    flow = state["dataflow"]
    schema = state["schema"]
    reporter.update("Presenter", "running", "Scripting the video explainer")

    fallback = _heuristic(ctx, brief, arch, flow, schema)
    comp = "; ".join(f"{c.name} ({c.kind})" for c in brief.components)
    flow_desc = " -> ".join(f"{s.actor}: {s.label}" for s in flow.steps[:6])
    has_schema = bool(schema.tables)
    prompt = render(
        "presenter_user",
        owner=ctx.meta.owner,
        repo=ctx.meta.name,
        what=brief.what,
        does=brief.does,
        how=brief.how,
        components=comp,
        architecture=arch.summary,
        flow_title=flow.title,
        flow_desc=flow_desc,
        has_database=has_schema,
        schema_tables=(f"; tables: {', '.join(t.name for t in schema.tables)}" if has_schema else ""),
        schema_scene=(", schema" if has_schema else ""),
    )
    data = invoke_json(render("presenter_system"), prompt, default=None)

    video = fallback
    if isinstance(data, dict) and data.get("scenes"):
        try:
            candidate = VideoExplainer(
                title=data.get("title", fallback.title),
                persona=PERSONA,
                tagline=data.get("tagline", fallback.tagline),
                scenes=[VideoScene.model_validate(s) for s in data["scenes"]],
            )
            if candidate.scenes:
                video = candidate
        except Exception:  # noqa: BLE001
            video = fallback

    reporter.update("Presenter", "done", f"{len(video.scenes)}-scene script")
    return {"video": video}
