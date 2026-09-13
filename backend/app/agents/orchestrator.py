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
from . import architect, dataflow, deepdive, presenter, researcher, schema, tutor
from .state import GraphState, PipelineCancelled, ProgressReporter, check_cancelled

logger = logging.getLogger("githubiq.orchestrator")

AGENT_NAMES = [
    "Researcher",
    "Architect",
    "Schema",
    "Data-Flow",
    "Deep-Dive",
    "Tutor",
    "Presenter",
]


def _compose(state: GraphState) -> dict:
    """Merge every agent's findings into a component-wise, Learn-style guide."""
    reporter = state["reporter"]
    ctx = state["ctx"]
    brief = state["research"]
    arch = state["architecture"]
    flow = state["dataflow"]
    sch = state["schema"]
    tutor_lessons = state.get("tutor_lessons", [])
    deepdives = state.get("component_deepdives", {})

    # 1. Plain-language orientation: a rich summary first, then what/does/how.
    langs = brief.languages or ctx.meta.languages
    facts: list[str] = []
    if ctx.meta.primary_language or langs:
        facts.append(f"- **Primary language:** {ctx.meta.primary_language or langs[0]}")
    if langs:
        facts.append("- **Stack / languages:** " + ", ".join(langs[:6]))
    if brief.components:
        facts.append(
            f"- **Components ({len(brief.components)}):** "
            + ", ".join(c.name for c in brief.components[:8])
        )
    if brief.entry_points:
        facts.append("- **Entry points:** " + ", ".join(f"`{e}`" for e in brief.entry_points[:6]))
    facts.append(f"- **Database:** {'yes' if brief.has_database else 'none detected'}")
    if ctx.meta.file_count:
        facts.append(f"- **Files analysed:** {ctx.meta.file_count}")

    overview_body = brief.what or ctx.meta.description or f"{ctx.meta.name} repository."
    if brief.does:
        overview_body += "\n\n" + brief.does
    if facts:
        overview_body += "\n\n**At a glance**\n" + "\n".join(facts)
    if brief.notes:
        overview_body += "\n\n**Good to know:** " + brief.notes

    lessons: list[Lesson] = [
        Lesson(
            id="overview",
            title="Project overview",
            section="Start here",
            icon="🧭",
            summary=brief.what or ctx.meta.description or "A quick map of the whole project.",
            body=overview_body,
            tags=["overview", "summary"],
        ),
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

    # 2. Component-wise breakdown: description, high-level flow, and key files.
    id_to_comp = {n.id: (n.component or "") for n in arch.nodes}
    for c in brief.components:
        nodes_in = [n for n in arch.nodes if (n.component or "").lower() == c.name.lower()]
        calls: list[str] = []
        called_by: list[str] = []
        for n in nodes_in:
            for t in n.outbound:
                comp = id_to_comp.get(t, "")
                if comp and comp.lower() != c.name.lower() and comp not in calls:
                    calls.append(comp)
            for s in n.inbound:
                comp = id_to_comp.get(s, "")
                if comp and comp.lower() != c.name.lower() and comp not in called_by:
                    called_by.append(comp)

        parts = "\n".join(f"- **{n.label}** — {n.summary}" for n in nodes_in)
        files = "\n".join(f"- `{f}`" for f in c.key_files)

        body = c.responsibility or f"The {c.name} component of {ctx.meta.name}."
        if c.tech:
            body += "\n\n**Tech:** " + ", ".join(f"`{t}`" for t in c.tech)
        deep = deepdives.get(c.name)
        if deep:
            body += "\n\n" + deep.strip()
        flow_lines = []
        if called_by:
            flow_lines.append("- **Called by:** " + ", ".join(called_by))
        if calls:
            flow_lines.append("- **Calls / depends on:** " + ", ".join(calls))
        if flow_lines:
            body += "\n\n**How it connects**\n" + "\n".join(flow_lines)
        if parts:
            body += "\n\n**Key parts**\n" + parts
        if files:
            body += "\n\n**Key files to read first**\n" + files
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


def _guard(fn):
    """Wrap a graph node so cancellation is checked before it runs.

    Gives us a cancellation checkpoint at every node boundary; combined with the
    in-loop checks inside the Deep-Dive agent, a cancelled run stops promptly
    instead of grinding through the remaining agents.
    """
    def wrapped(state: GraphState) -> dict:
        check_cancelled(state["reporter"])
        return fn(state)

    wrapped.__name__ = getattr(fn, "__name__", "node")
    return wrapped


def build_graph():
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(GraphState)
    g.add_node("agent_researcher", _guard(researcher.run))
    g.add_node("agent_architect", _guard(architect.run))
    g.add_node("agent_schema", _guard(schema.run))
    g.add_node("agent_dataflow", _guard(dataflow.run))
    g.add_node("agent_deepdive", _guard(deepdive.run))
    g.add_node("agent_tutor", _guard(tutor.run))
    g.add_node("agent_presenter", _guard(presenter.run))
    g.add_node("compose", _guard(_compose))

    g.add_edge(START, "agent_researcher")
    # fan-out from the researcher: architect, schema and tutor run in parallel
    g.add_edge("agent_researcher", "agent_architect")
    g.add_edge("agent_researcher", "agent_schema")
    g.add_edge("agent_researcher", "agent_tutor")
    # deepest chain: architect -> dataflow -> deepdive -> presenter -> compose
    # LangGraph triggers a node per firing edge (not a barrier), so compose is
    # triggered ONLY by the deepest node. The earlier parallel results (schema,
    # tutor) have already been written to the shared channels by then. Deep-Dive
    # sits on the critical path so its per-component sections are ready to merge.
    g.add_edge("agent_architect", "agent_dataflow")
    g.add_edge("agent_dataflow", "agent_deepdive")
    g.add_edge("agent_deepdive", "agent_presenter")
    g.add_edge("agent_presenter", "compose")
    g.add_edge("compose", END)
    return g.compile()


def run_pipeline(
    result: AnalysisResult, ctx, store: Store, cancel_event=None
) -> AnalysisResult:
    """Execute the multi-agent graph, mutating and persisting ``result``.

    ``cancel_event`` is an optional in-process :class:`threading.Event` for the
    background-task path. Regardless, a store-backed check re-reads the persisted
    ``cancel_requested`` flag so a cancel issued from the API reaches a worker
    running in a different process.
    """
    def _flag_check() -> bool:
        fresh = store.get(result.id)
        return bool(fresh and fresh.cancel_requested)

    reporter = ProgressReporter(
        result, store, cancel_event=cancel_event, cancel_check=_flag_check
    )

    # Respect a cancel that arrived before we even started.
    if reporter.cancelled():
        reporter.cancel()
        return reporter.result

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
    except PipelineCancelled:
        logger.info("Pipeline cancelled for %s", result.id)
        reporter.cancel()
        return reporter.result
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
