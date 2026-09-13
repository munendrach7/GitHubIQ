"""Schema agent — reverse-engineers database models and relationships."""
from __future__ import annotations

from ..llm import invoke_json
from ..models import Schema
from .state import GraphState

SYSTEM = (
    "You are the Schema agent. You reverse-engineer a project's data model from "
    "migrations, ORM models and SQL. You output every table with its columns "
    "(marking primary/foreign keys and referenced tables), the relationships "
    "between tables with cardinality, and a plain-English explanation. Respond "
    "ONLY with strict JSON."
)


def _empty(reason: str) -> Schema:
    return Schema(
        summary=reason,
        plain_english=(
            "This project does not define a relational/ORM data model, so there is "
            "no schema to show."
        ),
    )


def run(state: GraphState) -> dict:
    ctx = state["ctx"]
    reporter = state["reporter"]
    brief = state["research"]
    reporter.update("Schema", "running", "Reverse-engineering DB models")

    assigned = brief.file_assignments.get("schema", [])
    if not brief.has_database and not assigned:
        reporter.update("Schema", "done", "no database")
        return {"schema": _empty("No database in this repository.")}

    sources = ctx.read_files(assigned, total_budget=70_000) or ctx.sampled_sources(8)
    prompt = (
        f"Repository: {ctx.meta.owner}/{ctx.meta.name}\n"
        f"What it is: {brief.what}\n\n"
        f"SCHEMA / MODEL / MIGRATION FILES:\n{sources}\n\n"
        "Return JSON: {\"summary\": str, "
        "\"tables\": [{\"name\": str, \"columns\": [{\"name\": str, \"type\": str, "
        "\"key\": \"pk\"|\"fk\"|\"\", \"ref\": \"table.column\"}]}], "
        "\"relationships\": [{\"source\": table, \"target\": table, "
        "\"cardinality\": \"1:N\"|\"N:1\"|\"1:1\"|\"N:N\"}], "
        "\"plain_english\": str}. "
        "Include EVERY table you find with all columns and correct key markers. "
        "If there is genuinely no database, return {\"tables\": [], "
        "\"relationships\": [], \"summary\": \"No database\"}."
    )
    data = invoke_json(SYSTEM, prompt, default=None)

    schema = _empty("No relational schema detected.")
    if isinstance(data, dict) and data.get("tables") is not None:
        try:
            schema = Schema.model_validate(
                {
                    "summary": data.get("summary", "Data model reverse-engineered."),
                    "tables": data.get("tables", []),
                    "relationships": data.get("relationships", []),
                    "plain_english": data.get("plain_english", ""),
                }
            )
        except Exception:  # noqa: BLE001
            schema = _empty("Schema files present but could not be parsed.")

    reporter.update("Schema", "done", f"{len(schema.tables)} tables mapped")
    return {"schema": schema}
