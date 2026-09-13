"""Pydantic models shared across the API and the agent pipeline."""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

_SURROGATES = re.compile(r"[\ud800-\udfff]")


def _strip_surrogates(obj: Any) -> Any:
    """Remove lone UTF-16 surrogates that break UTF-8 JSON serialisation.

    LLM output and decoded source files can contain unpaired surrogate code
    points; these must be dropped before the document is JSON-encoded.
    """
    if isinstance(obj, str):
        return _SURROGATES.sub("", obj)
    if isinstance(obj, list):
        return [_strip_surrogates(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _strip_surrogates(v) for k, v in obj.items()}
    return obj


# --------------------------------------------------------------------------- #
# Request / preferences
# --------------------------------------------------------------------------- #
class Role(str, Enum):
    new_to_team = "new_to_team"
    frontend = "frontend"
    backend = "backend"


class Familiarity(str, Enum):
    brand_new = "brand_new"
    some_exposure = "some_exposure"
    comfortable = "comfortable"
    expert = "expert"


class Depth(str, Enum):
    quick = "quick"
    guided = "guided"
    deep = "deep"


class Preferences(BaseModel):
    role: Role = Role.new_to_team
    familiarity: Familiarity = Familiarity.some_exposure
    goals: list[str] = Field(default_factory=list)
    depth: Depth = Depth.guided


class AnalyzeRequest(BaseModel):
    repo_url: str = Field(..., examples=["https://github.com/pallets/flask"])
    preferences: Preferences = Field(default_factory=Preferences)
    # Optional: restrict analysis to a subfolder for a more focused guide.
    scope_path: str = ""


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class Credentials(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    password: str = Field(..., min_length=6, max_length=128)


class User(BaseModel):
    id: str                      # username (partition key)
    username: str
    salt: str = ""
    password_hash: str = ""
    is_admin: bool = False
    created_at: float = 0.0
    generations: list[float] = Field(default_factory=list)  # epoch timestamps

    def as_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RateStatus(BaseModel):
    can_generate: bool = True
    seconds_left: int = 0
    next_allowed_at: float = 0.0
    window_hours: float = 4.0
    max_attempts: int = 1
    used: int = 0


class AuthResponse(BaseModel):
    token: str
    username: str
    is_admin: bool
    rate: RateStatus


# --------------------------------------------------------------------------- #
# Analysis result building blocks
# --------------------------------------------------------------------------- #
class RepoMeta(BaseModel):
    owner: str = ""
    name: str = ""
    default_branch: str = "main"
    description: str = ""
    primary_language: str = ""
    languages: list[str] = Field(default_factory=list)
    file_count: int = 0
    stars: int = 0


class ServiceNode(BaseModel):
    id: str
    label: str
    path: str = ""
    language: str = ""
    role: str = ""
    summary: str = ""
    component: str = ""           # which software component this belongs to
    tech: list[str] = Field(default_factory=list)
    inbound: list[str] = Field(default_factory=list)   # node ids that call this
    outbound: list[str] = Field(default_factory=list)  # node ids this calls
    layer: str = ""               # entry | service | data | external | ui


class ServiceEdge(BaseModel):
    source: str
    target: str
    label: str = ""
    kind: str = "request"  # request | event | support | data
    protocol: str = ""     # http | grpc | queue | sql | fs | internal


class Architecture(BaseModel):
    summary: str = ""
    nodes: list[ServiceNode] = Field(default_factory=list)
    edges: list[ServiceEdge] = Field(default_factory=list)
    layers: list[str] = Field(default_factory=list)  # ordered layer names


class FlowStep(BaseModel):
    index: int
    actor: str
    label: str = ""
    code: str = ""
    note: str = ""
    kind: str = "sync"  # sync | async
    detail: str = ""                 # deeper explanation shown on click
    files: list[str] = Field(default_factory=list)   # source files for this hop
    data_in: str = ""                # payload/state entering this step
    data_out: str = ""               # payload/state leaving this step


class DataFlow(BaseModel):
    title: str = ""
    trigger: str = ""                 # what starts this flow
    summary: str = ""
    steps: list[FlowStep] = Field(default_factory=list)
    rationale: str = ""
    alternatives: list[str] = Field(default_factory=list)  # other notable flows


class Column(BaseModel):
    name: str
    type: str = ""
    key: str = ""  # pk | fk | ""
    ref: str = ""


class Table(BaseModel):
    name: str
    columns: list[Column] = Field(default_factory=list)


class Relationship(BaseModel):
    source: str
    target: str
    cardinality: str = "1:N"


class Schema(BaseModel):
    summary: str = ""
    tables: list[Table] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    plain_english: str = ""


class Lesson(BaseModel):
    id: str
    title: str
    section: str = ""
    summary: str = ""
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    component: str = ""
    icon: str = ""


class Guide(BaseModel):
    title: str = ""
    intro: str = ""
    lessons: list[Lesson] = Field(default_factory=list)


class ScreenElement(BaseModel):
    label: str
    kind: str = "element"   # button | input | list | nav | card | text | chart
    note: str = ""


class WalkthroughScreen(BaseModel):
    id: str
    title: str
    route: str = ""                 # URL/route or CLI command if applicable
    kind: str = "page"             # page | modal | cli | state | dashboard
    description: str = ""
    elements: list[ScreenElement] = Field(default_factory=list)
    user_actions: list[str] = Field(default_factory=list)
    leads_to: str = ""             # id of the next screen this typically leads to


class Sandbox(BaseModel):
    """High-level visual walkthrough of what the app looks like and how a user moves through it."""
    title: str = ""
    summary: str = ""
    app_type: str = ""             # web app | api | cli | library | mobile | service
    screens: list[WalkthroughScreen] = Field(default_factory=list)
    challenge: str = ""


class VideoScene(BaseModel):
    id: str
    title: str
    narration: str = ""            # what the presenter says (spoken)
    bullets: list[str] = Field(default_factory=list)
    visual: str = "intro"          # intro | components | architecture | dataflow | schema | tech | outro
    accent: str = "blue"


class VideoExplainer(BaseModel):
    title: str = ""
    persona: str = "Alex"          # the male presenter's name
    tagline: str = ""
    scenes: list[VideoScene] = Field(default_factory=list)


class Component(BaseModel):
    id: str
    name: str
    kind: str = ""                 # frontend | backend service | worker | library | cli | infra | database
    path: str = ""
    tech: list[str] = Field(default_factory=list)
    responsibility: str = ""
    key_files: list[str] = Field(default_factory=list)


class ResearchBrief(BaseModel):
    """Produced by the Researcher agent that crawls the repo and delegates context."""
    what: str = ""                  # what this project is, in one plain sentence
    does: str = ""                 # what it does for users
    how: str = ""                  # how it works at a high level
    entry_points: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    has_database: bool = False
    notes: str = ""
    # curated file paths each specialist agent should read (agent name -> paths)
    file_assignments: dict[str, list[str]] = Field(default_factory=dict)


class ExplorerFindings(BaseModel):
    summary: str = ""
    entry_points: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)


class AnalysisStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    error = "error"


class AgentProgress(BaseModel):
    name: str
    status: str = "waiting"  # waiting | running | done | error
    detail: str = ""


class AnalysisResult(BaseModel):
    id: str
    repo_url: str
    owner: str = ""              # username who generated it
    created_at: float = 0.0
    scope_path: str = ""         # subfolder the analysis was restricted to (blank = whole repo)
    status: AnalysisStatus = AnalysisStatus.queued
    progress: list[AgentProgress] = Field(default_factory=list)
    percent: int = 0
    error: Optional[str] = None
    llm_powered: bool = False

    repo: RepoMeta = Field(default_factory=RepoMeta)
    preferences: Preferences = Field(default_factory=Preferences)
    research: ResearchBrief = Field(default_factory=ResearchBrief)
    explorer: ExplorerFindings = Field(default_factory=ExplorerFindings)
    architecture: Architecture = Field(default_factory=Architecture)
    dataflow: DataFlow = Field(default_factory=DataFlow)
    schema_: Schema = Field(default_factory=Schema, alias="schema")
    guide: Guide = Field(default_factory=Guide)
    sandbox: Sandbox = Field(default_factory=Sandbox)
    video: VideoExplainer = Field(default_factory=VideoExplainer)

    model_config = {"populate_by_name": True}

    def as_document(self) -> dict[str, Any]:
        return _strip_surrogates(self.model_dump(by_alias=True, mode="json"))


class AnalysisSummary(BaseModel):
    id: str
    repo_url: str
    repo_name: str = ""
    repo_owner: str = ""
    status: AnalysisStatus = AnalysisStatus.queued
    percent: int = 0
    created_at: float = 0.0
    llm_powered: bool = False
