"""Analysis API routes."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ..agents.orchestrator import AGENT_NAMES, run_pipeline
from ..auth import get_current_user, rate_status, record_generation
from ..github_client import GitHubClient, parse_repo_url
from ..models import (
    AgentProgress,
    AnalysisResult,
    AnalysisStatus,
    AnalysisSummary,
    AnalyzeRequest,
    User,
)
from ..storage import get_store

logger = logging.getLogger("githubiq.api")
router = APIRouter(prefix="/api", tags=["analysis"])


def _run_analysis(analysis_id: str, req: AnalyzeRequest) -> None:
    store = get_store()
    result = store.get(analysis_id)
    if result is None:
        return
    try:
        owner, repo = parse_repo_url(req.repo_url)
        with GitHubClient() as gh:
            ctx = gh.fetch_context(owner, repo)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch repo")
        result.status = AnalysisStatus.error
        result.error = f"Could not read repository: {exc}"
        store.upsert(result)
        return
    run_pipeline(result, ctx, store)


@router.post("/analyze", response_model=AnalysisResult, response_model_by_alias=True)
def analyze(
    req: AnalyzeRequest,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> AnalysisResult:
    store = get_store()
    status = rate_status(user)
    if not status.can_generate:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit reached. You can generate {status.max_attempts} analysis "
                f"per {status.window_hours:g}h. Try again in "
                f"{status.seconds_left // 60} min."
            ),
            headers={"Retry-After": str(status.seconds_left)},
        )

    analysis_id = uuid.uuid4().hex[:12]
    result = AnalysisResult(
        id=analysis_id,
        repo_url=req.repo_url,
        owner=user.username,
        created_at=time.time(),
        preferences=req.preferences,
        status=AnalysisStatus.queued,
        progress=[AgentProgress(name=n, status="waiting") for n in AGENT_NAMES],
    )
    store.upsert(result)
    # Record the generation up-front so concurrent requests can't bypass the limit.
    record_generation(store, user)
    background.add_task(_run_analysis, analysis_id, req)
    return result


@router.get("/analyses", response_model=list[AnalysisSummary])
def list_analyses(user: User = Depends(get_current_user)) -> list[AnalysisSummary]:
    results = get_store().list_analyses(user.username)
    return [
        AnalysisSummary(
            id=r.id,
            repo_url=r.repo_url,
            repo_name=r.repo.name,
            repo_owner=r.repo.owner,
            status=r.status,
            percent=r.percent,
            created_at=r.created_at,
            llm_powered=r.llm_powered,
        )
        for r in results
    ]


@router.get("/analysis/{analysis_id}", response_model=AnalysisResult,
            response_model_by_alias=True)
def get_analysis(analysis_id: str) -> AnalysisResult:
    result = get_store().get(analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result
