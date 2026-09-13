"""Tutor agent — explains languages, frameworks and idioms for the learner."""
from __future__ import annotations

from ..llm import invoke_json
from ..compaction import compact_files
from ..models import Lesson, Preferences
from ..prompts import render
from ..scale import compute_scale
from .state import GraphState

SYSTEM = (
    "You are the Tutor agent. You explain the languages, frameworks and idioms a "
    "newcomer will meet in a repository, tailored to their role and experience. "
    "Respond ONLY with JSON."
)


def _heuristic(ctx, prefs: Preferences, brief=None) -> list[Lesson]:
    langs = ctx.meta.languages or [ctx.meta.primary_language or "the stack"]
    entries = ", ".join((brief.entry_points if brief else [])[:4]) or "the entry points"
    mods = ", ".join((brief.modules if brief else [])[:6])
    lessons = []
    for i, lang in enumerate(langs[:3]):
        body = (
            f"**{ctx.meta.name}** is written in **{lang}**. Start from "
            f"`{entries}` and read into the core modules"
            + (f" (`{mods}`)" if mods else "")
            + f". Watch for the {lang} idioms this project leans on — its module "
            "structure, key classes/functions, decorators or types — and how they "
            "wire the pieces together."
        )
        lessons.append(
            Lesson(
                id=f"lang-{i}",
                title=f"{lang} in {ctx.meta.name}",
                section="Go hands-on",
                summary=f"Key {lang} idioms you'll meet in {ctx.meta.name}.",
                body=body,
                tags=[lang, "language"],
            )
        )
    return lessons


def run(state: GraphState) -> dict:
    ctx = state["ctx"]
    reporter = state["reporter"]
    prefs: Preferences = state["preferences"]
    brief = state["research"]
    reporter.update("Tutor", "running", "Explaining language idioms & patterns")

    scale = compute_scale(ctx.meta.file_count, prefs.depth)
    fallback = _heuristic(ctx, prefs, brief)
    sources = compact_files(
        ctx,
        brief.file_assignments.get("tutor", []),
        budget=180_000,
        focus="the language and framework idioms used here: decorators, hooks, "
        "types, macros, module patterns and notable constructs",
    ) or ctx.sampled_sources(8)
    prompt = render(
        "tutor_user",
        owner=ctx.meta.owner,
        repo=ctx.meta.name,
        what=brief.what,
        languages=", ".join(ctx.meta.languages),
        role=prefs.role.value,
        familiarity=prefs.familiarity.value,
        depth=prefs.depth.value,
        goals=", ".join(prefs.goals) or "general",
        sources=sources,
        lesson_min=scale.lessons[0],
        lesson_max=scale.lessons[1],
    )
    data = invoke_json(render("tutor_system"), prompt, default=None)

    lessons: list[Lesson] = []
    if isinstance(data, dict) and data.get("lessons"):
        for i, l in enumerate(data["lessons"]):
            try:
                l = {**l, "section": "Go hands-on"}
                l.setdefault("id", f"tutor-{i}")
                if isinstance(l.get("tags"), str):
                    l["tags"] = [l["tags"]]
                lessons.append(Lesson.model_validate(l))
            except Exception:  # noqa: BLE001 - skip a malformed lesson, keep the rest
                continue
    if not lessons:
        lessons = fallback

    reporter.update("Tutor", "done", f"{len(lessons)} language lessons")
    return {"tutor_lessons": lessons}
