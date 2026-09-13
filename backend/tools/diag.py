"""Local diagnostic: run the exploration agents against a repo and dump the output.

Usage: python tools/diag.py <github_url>
"""
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO)
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents import architect, dataflow, researcher, schema
from app.agents.state import ProgressReporter
from app.github_client import GitHubClient, parse_repo_url
from app.models import AnalysisResult, Preferences
from app.storage import MemoryStore

url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/Munendra7/Ai-Agent"
store = MemoryStore()
result = AnalysisResult(id="diag", repo_url=url)
store.upsert(result)
reporter = ProgressReporter(result, store)

owner, repo = parse_repo_url(url)
with GitHubClient() as gh:
    ctx = gh.fetch_context(owner, repo, "")
print(f"== {owner}/{repo}: files={ctx.meta.file_count} langs={ctx.meta.languages}", flush=True)

state = {"ctx": ctx, "reporter": reporter, "preferences": Preferences(depth="deep")}
state.update(researcher.run(state))
state.update(architect.run(state))
state.update(schema.run(state))
state.update(dataflow.run(state))

brief = state["research"]
arch = state["architecture"]
sch = state["schema"]
flow = state["dataflow"]

out = {
    "research": {
        "what": brief.what,
        "has_database": brief.has_database,
        "database": brief.database,
        "components": [
            {"name": c.name, "kind": c.kind, "path": c.path, "tech": c.tech}
            for c in brief.components
        ],
        "schema_files": brief.file_assignments.get("schema", []),
        "dataflow_files": brief.file_assignments.get("dataflow", []),
    },
    "architecture": {
        "nodes": len(arch.nodes),
        "edges": len(arch.edges),
        "layers": arch.layers,
        "node_sample": [
            {"label": n.label, "layer": n.layer, "in": len(n.inbound), "out": len(n.outbound)}
            for n in arch.nodes
        ],
    },
    "schema": {
        "database": sch.database,
        "kind": sch.kind,
        "tables": [
            {"name": t.name, "cols": [c.name for c in t.columns]} for t in sch.tables
        ],
        "relationships": len(sch.relationships),
    },
    "dataflow": {
        "endpoints": [
            {"method": e.method, "route": e.route, "title": e.title, "steps": len(e.steps)}
            for e in flow.endpoints
        ],
    },
}
with open("diag_out.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
print(json.dumps(out, indent=2), flush=True)
