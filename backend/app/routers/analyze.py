"""Analysis API routes."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from .. import cancel as cancel_registry
from ..agents.orchestrator import AGENT_NAMES, run_pipeline
from ..auth import get_current_user, rate_status, record_generation
from ..github_client import GitHubClient, parse_repo_url
from ..messaging import enqueue_analysis, servicebus_enabled
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

# Terminal states in which a job can no longer be cancelled.
_TERMINAL = {AnalysisStatus.done, AnalysisStatus.error, AnalysisStatus.cancelled}


def _run_analysis(analysis_id: str, req: AnalyzeRequest) -> None:
    """In-process execution path (used when Service Bus is not configured)."""
    store = get_store()
    result = store.get(analysis_id)
    if result is None:
        return
    cancel_event = cancel_registry.register(analysis_id)
    try:
        owner, repo = parse_repo_url(req.repo_url)
        with GitHubClient() as gh:
            ctx = gh.fetch_context(owner, repo, req.scope_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch repo")
        result.status = AnalysisStatus.error
        result.error = f"Could not read repository: {exc}"
        store.upsert(result)
        return
    try:
        run_pipeline(result, ctx, store, cancel_event=cancel_event)
    finally:
        cancel_registry.clear(analysis_id)


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
        scope_path=req.scope_path.strip().strip("/"),
        preferences=req.preferences,
        status=AnalysisStatus.queued,
        progress=[AgentProgress(name=n, status="waiting") for n in AGENT_NAMES],
    )
    store.upsert(result)
    # Record the generation up-front so concurrent requests can't bypass the limit.
    record_generation(store, user)

    # Prefer async dispatch to a worker via Service Bus; fall back to running the
    # job in-process so local dev / demos work without any broker configured.
    if servicebus_enabled() and enqueue_analysis(analysis_id):
        logger.info("Analysis %s dispatched to worker queue", analysis_id)
    else:
        background.add_task(_run_analysis, analysis_id, req)
    return result


@router.post("/analysis/{analysis_id}/cancel", response_model=AnalysisResult,
             response_model_by_alias=True)
def cancel_analysis(
    analysis_id: str, user: User = Depends(get_current_user)
) -> AnalysisResult:
    store = get_store()
    result = store.get(analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if not user.is_admin and result.owner != user.username:
        raise HTTPException(status_code=403, detail="Not allowed to cancel this run")
    if result.status in _TERMINAL:
        return result  # already finished; nothing to cancel

    # Persist the flag (a worker in another process polls it) AND signal any
    # in-process run so it aborts promptly.
    result.cancel_requested = True
    if result.status == AnalysisStatus.queued:
        # Not started yet — mark it cancelled right away for snappy feedback.
        result.status = AnalysisStatus.cancelled
        result.error = "Cancelled by user."
    store.upsert(result)
    cancel_registry.request_cancel(analysis_id)
    return result


@router.get("/repo/tree")
def repo_tree(repo_url: str, _user: User = Depends(get_current_user)) -> dict:
    """Directory listing for the folder-scope explorer on the analysis form."""
    try:
        owner, repo = parse_repo_url(repo_url)
        with GitHubClient() as gh:
            dirs = gh.list_dirs(owner, repo)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not read repository: {exc}")
    return {"owner": owner, "repo": repo, "dirs": dirs}


@router.get("/analyses", response_model=list[AnalysisSummary])
def list_analyses(user: User = Depends(get_current_user)) -> list[AnalysisSummary]:
    store = get_store()
    # Admins see every user's sessions; regular users see only their own.
    results = store.list_all_analyses() if user.is_admin else store.list_analyses(user.username)
    return [
        AnalysisSummary(
            id=r.id,
            repo_url=r.repo_url,
            repo_name=r.repo.name,
            repo_owner=r.repo.owner,
            owner=r.owner,
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
