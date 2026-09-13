"""Schema agent — reverse-engineers database models and relationships."""
from __future__ import annotations

from ..llm import invoke_json
from ..compaction import compact_files
from ..models import Schema
from ..prompts import render
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
        kind="none",
        plain_english=(
            "This project does not appear to persist data to a database, so there "
            "is no schema to show."
        ),
    )


def run(state: GraphState) -> dict:
    ctx = state["ctx"]
    reporter = state["reporter"]
    brief = state["research"]
    reporter.update("Schema", "running", "Reverse-engineering the persistence model")

    assigned = brief.file_assignments.get("schema", [])
    if not brief.has_database and not brief.database and not assigned:
        reporter.update("Schema", "done", "no database")
        return {"schema": _empty("No persistence layer detected in this repository.")}

    sources = compact_files(
        ctx,
        assigned,
        budget=200_000,
        focus="database tables/collections/entities, columns/fields, primary/foreign "
        "keys, relationships, migrations, ORM & EF Core DbContext/entity definitions, "
        "NoSQL/vector schemas and DB connection config",
    ) or ctx.sampled_sources(8)
    prompt = render(
        "schema_user",
        owner=ctx.meta.owner,
        repo=ctx.meta.name,
        what=brief.what,
        db_hint=(brief.database or ("a database appears to be present" if brief.has_database else "none stated")),
        notes=brief.notes or "(none)",
        sources=sources,
    )
    data = invoke_json(render("schema_system"), prompt, default=None)

    schema = _empty("No persistence layer detected.")
    if isinstance(data, dict) and data.get("tables") is not None:
        try:
            schema = Schema.model_validate(
                {
                    "summary": data.get("summary", "Data model reverse-engineered."),
                    "database": data.get("database", "") or brief.database,
                    "kind": data.get("kind", ""),
                    "tables": data.get("tables", []),
                    "relationships": data.get("relationships", []),
                    "plain_english": data.get("plain_english", ""),
                }
            )
        except Exception:  # noqa: BLE001
            schema = _empty("Schema files present but could not be parsed.")

    reporter.update(
        "Schema", "done", f"{len(schema.tables)} tables · {schema.database or 'no db'}"
    )
    return {"schema": schema}
