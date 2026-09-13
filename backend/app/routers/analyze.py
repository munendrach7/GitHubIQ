"""Analysis API routes."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException

from ..agents.orchestrator import AGENT_NAMES
from ..auth import get_current_user, rate_status, record_generation
from ..github_client import GitHubClient, parse_repo_url
from ..messaging import enqueue_analysis, servicebus_enabled
from ..models import (
    AdminUserView,
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


@router.post("/analyze", response_model=AnalysisResult, response_model_by_alias=True)
def analyze(
    req: AnalyzeRequest,
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

    # Service Bus is the ONLY processing path. If the queue is unreachable we fail
    # fast rather than silently running the job any other way.
    if not servicebus_enabled():
        raise HTTPException(
            status_code=503,
            detail="Analysis backend is not configured (job queue unavailable).",
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

    # Dispatch to a worker via Service Bus. The worker runs the pipeline and writes
    # all progress/results to Cosmos DB, which this API reads back for status.
    if not enqueue_analysis(analysis_id):
        result.status = AnalysisStatus.error
        result.error = "Could not queue the analysis job. Please try again."
        store.upsert(result)
        raise HTTPException(
            status_code=503,
            detail="Analysis queue is unavailable. Please try again shortly.",
        )
    logger.info("Analysis %s queued to Service Bus for a worker", analysis_id)
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

    # Record a cancel intent in a SEPARATE record the worker polls, so the
    # worker's own progress writes can never overwrite it. A running job's
    # pipeline observes the intent within ~1s and transitions to 'cancelled'.
    store.request_cancel(analysis_id)
    result.cancel_requested = True
    if result.status == AnalysisStatus.queued:
        # Not started yet — mark it cancelled right away for snappy feedback.
        result.status = AnalysisStatus.cancelled
        result.error = "Cancelled by user."
    store.upsert(result)
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


@router.get("/admin/users", response_model=list[AdminUserView])
def admin_list_users(user: User = Depends(get_current_user)) -> list[AdminUserView]:
    """Admin-only: every user in the system and the guides they've generated."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admins only")
    store = get_store()
    by_owner: dict[str, list[AnalysisSummary]] = {}
    for r in store.list_all_analyses():
        by_owner.setdefault(r.owner, []).append(
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
        )
    views = [
        AdminUserView(
            username=u.username,
            created_at=u.created_at,
            is_admin=u.is_admin,
            generations=len(u.generations),
            guides=by_owner.pop(u.username, []),
        )
        for u in store.list_users()
    ]
    # Include any owners that have guides but no stored user record (e.g. admin).
    for owner, guides in by_owner.items():
        if owner:
            views.append(
                AdminUserView(username=owner, generations=len(guides), guides=guides)
            )
    views.sort(key=lambda v: (len(v.guides), v.created_at), reverse=True)
    return views
