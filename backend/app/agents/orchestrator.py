"""Orchestrator — builds the LangGraph pipeline and composes the final guide.

Flow:  Researcher → (Architect ∥ Schema ∥ Tutor)
       Architect → Data-Flow → Walkthrough
       Walkthrough → Compose (merge into a component-wise Learn-style guide)
"""
from __future__ import annotations

import logging

from ..llm import llm_available
from ..models import (
    AnalysisResult,
    AnalysisStatus,
    ExplorerFindings,
    Guide,
    Lesson,
)
from ..storage import Store
from . import architect, dataflow, presenter, researcher, schema, tutor
from .state import GraphState, ProgressReporter

logger = logging.getLogger("githubiq.orchestrator")

AGENT_NAMES = ["Researcher", "Architect", "Schema", "Data-Flow", "Tutor", "Presenter"]


def _compose(state: GraphState) -> dict:
    """Merge every agent's findings into a component-wise, Learn-style guide."""
    reporter = state["reporter"]
    ctx = state["ctx"]
    brief = state["research"]
    arch = state["architecture"]
    flow = state["dataflow"]
    sch = state["schema"]
    tutor_lessons = state.get("tutor_lessons", [])

    # 1. Simple, plain-language orientation first.
    lessons: list[Lesson] = [
        Lesson(
            id="what",
            title="What is this project?",
            section="Start here",
            icon="📘",
            summary=brief.what or ctx.meta.description,
            body=brief.what or ctx.meta.description,
            tags=["overview"],
        ),
        Lesson(
            id="does",
            title="What does it do?",
            section="Start here",
            icon="🎯",
            summary="The value it delivers to its users.",
            body=brief.does or ctx.meta.description,
            tags=["overview"],
        ),
        Lesson(
            id="how",
            title="How does it work?",
            section="Start here",
            icon="⚙️",
            summary="The high-level approach, in plain language.",
            body=brief.how,
            tags=["overview"],
        ),
    ]

    # 2. Component-wise breakdown when the repo has multiple components.
    for c in brief.components:
        nodes_in = [n for n in arch.nodes if (n.component or "").lower() == c.name.lower()]
        parts = "\n".join(f"- **{n.label}** — {n.summary}" for n in nodes_in)
        files = "\n".join(f"- `{f}`" for f in c.key_files)
        body = c.responsibility
        if c.tech:
            body += "\n\n**Tech:** " + ", ".join(f"`{t}`" for t in c.tech)
        if parts:
            body += "\n\n**Key parts**\n" + parts
        if files:
            body += "\n\n**Key files**\n" + files
        lessons.append(
            Lesson(
                id=f"cmp-{c.id}",
                title=c.name,
                section="The components",
                icon="🧩",
                component=c.name,
                summary=f"{c.kind} · {', '.join(c.tech) or ctx.meta.primary_language}",
                body=body,
                tags=[c.kind] + c.tech[:2],
            )
        )

    # 3. Follow the data.
    lessons.append(
        Lesson(
            id="request",
            title="Follow one request end-to-end",
            section="Follow the data",
            icon="🐬",
            summary=flow.summary or flow.title,
            body=(flow.trigger + "\n\n" if flow.trigger else "") + flow.rationale,
            tags=["data-flow", "interactive"],
        )
    )
    if sch.tables:
        lessons.append(
            Lesson(
                id="schema",
                title="Database & schema tour",
                section="Follow the data",
                icon="🗄️",
                summary=sch.summary,
                body=sch.plain_english,
                tags=["schema"],
            )
        )

    # 4. Hands-on: language idioms + visual walkthrough.
    for l in tutor_lessons:
        l.section = "Go deeper"
        l.icon = l.icon or "📚"
        lessons.append(l)
    lessons.append(
        Lesson(
            id="video",
            title="Watch the 60-second tour",
            section="Go deeper",
            icon="\ud83c\udfa5",
            summary=state["video"].tagline or "A narrated video overview of the project.",
            body="Head to the Video tab for a quick narrated walkthrough by Alex.",
            tags=["video", "overview"],
        )
    )

    role = state["preferences"].role.value.replace("_", " ")
    guide = Guide(
        title=f"Your onboarding guide to {ctx.meta.name}",
        intro=(
            f"{brief.what} "
            f"This guide is tailored to a {role} learner and walks you from a plain-"
            f"language overview through each component, the data flow, the schema and "
            f"a visual tour of the app."
        ),
        lessons=lessons,
    )
    reporter.update("Presenter", "done", "guide composed")
    return {"guide": guide}


def build_graph():
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(GraphState)
    g.add_node("agent_researcher", researcher.run)
    g.add_node("agent_architect", architect.run)
    g.add_node("agent_schema", schema.run)
    g.add_node("agent_dataflow", dataflow.run)
    g.add_node("agent_tutor", tutor.run)
    g.add_node("agent_presenter", presenter.run)
    g.add_node("compose", _compose)

    g.add_edge(START, "agent_researcher")
    # fan-out from the researcher: architect, schema and tutor run in parallel
    g.add_edge("agent_researcher", "agent_architect")
    g.add_edge("agent_researcher", "agent_schema")
    g.add_edge("agent_researcher", "agent_tutor")
    # deepest chain: architect -> dataflow -> walkthrough -> compose
    # LangGraph triggers a node per firing edge (not a barrier), so compose is
    # triggered ONLY by the deepest node. The earlier parallel results (schema,
    # tutor) have already been written to the shared channels by then.
    g.add_edge("agent_architect", "agent_dataflow")
    g.add_edge("agent_dataflow", "agent_presenter")
    g.add_edge("agent_presenter", "compose")
    g.add_edge("compose", END)
    return g.compile()


def run_pipeline(result: AnalysisResult, ctx, store: Store) -> AnalysisResult:
    """Execute the multi-agent graph, mutating and persisting ``result``."""
    reporter = ProgressReporter(result, store)
    result.status = AnalysisStatus.running
    result.llm_powered = llm_available()
    result.repo = ctx.meta
    store.upsert(result)

    graph = build_graph()
    initial: GraphState = {
        "ctx": ctx,
        "reporter": reporter,
        "preferences": result.preferences,
    }
    try:
        final = graph.invoke(initial)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline failed")
        reporter.fail(str(exc))
        return reporter.result

    brief = final["research"]
    result.research = brief
    # Keep the legacy explorer field populated for backward compatibility.
    result.explorer = ExplorerFindings(
        summary=brief.what,
        entry_points=brief.entry_points,
        modules=brief.modules,
        languages=brief.languages,
    )
    result.architecture = final["architecture"]
    result.schema_ = final["schema"]
    result.dataflow = final["dataflow"]
    result.video = final["video"]
    result.guide = final["guide"]
    reporter.finish()
    return result
