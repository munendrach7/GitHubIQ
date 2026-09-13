"""Tutor agent — explains languages, frameworks and idioms for the learner."""
from __future__ import annotations

from ..llm import invoke_json
from ..models import Lesson, Preferences
from .state import GraphState

SYSTEM = (
    "You are the Tutor agent. You explain the languages, frameworks and idioms a "
    "newcomer will meet in a repository, tailored to their role and experience. "
    "Respond ONLY with JSON."
)


def _heuristic(ctx, prefs: Preferences) -> list[Lesson]:
    langs = ctx.meta.languages or [ctx.meta.primary_language or "the stack"]
    lessons = []
    for i, lang in enumerate(langs[:3]):
        lessons.append(
            Lesson(
                id=f"lang-{i}",
                title=f"{lang} fundamentals for this repo",
                section="Go hands-on",
                summary=f"Key {lang} idioms you'll meet in {ctx.meta.name}.",
                body=(
                    f"{ctx.meta.name} uses {lang}. Focus on the patterns that appear "
                    f"in the entry points and core modules as you read the code."
                ),
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

    fallback = _heuristic(ctx, prefs)
    sources = ctx.read_files(
        brief.file_assignments.get("tutor", []), total_budget=55_000
    ) or ctx.sampled_sources(8)
    prompt = (
        f"Repository: {ctx.meta.owner}/{ctx.meta.name}\n"
        f"What it is: {brief.what}\n"
        f"Languages: {', '.join(ctx.meta.languages)}\n"
        f"Learner role: {prefs.role.value}; familiarity: {prefs.familiarity.value}; "
        f"depth: {prefs.depth.value}; goals: {', '.join(prefs.goals) or 'general'}\n\n"
        f"ASSIGNED SOURCE (idioms to explain):\n{sources}\n\n"
        "Return JSON: {\"lessons\": [{\"id\": str, \"title\": str, "
        "\"summary\": str, \"body\": str, \"tags\": [str]}]}. "
        "Produce 3-5 concise, concrete lessons on the specific language/framework "
        "idioms and patterns used in THIS repo (reference real constructs you see), "
        "matched to the learner's experience level. Prefer showing over telling. "
        "Format each 'body' in GitHub-flavoured MARKDOWN: use short paragraphs, "
        "**bold** for key terms, bullet lists with '-', and fenced ```code``` "
        "blocks or `inline code` for real snippets and identifiers."
    )
    data = invoke_json(SYSTEM, prompt, default=None)

    lessons = fallback
    if isinstance(data, dict) and data.get("lessons"):
        try:
            lessons = [
                Lesson.model_validate({**l, "section": "Go hands-on"})
                for l in data["lessons"]
            ]
        except Exception:  # noqa: BLE001
            lessons = fallback

    reporter.update("Tutor", "done", f"{len(lessons)} language lessons")
    return {"tutor_lessons": lessons}
