"""
Repositories API routes — Validate, track, list, inspect, and delete repositories.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.repository import (
    RepositoryCreate,
    RepositoryValidateRequest,
    RepositoryValidateResponse,
    RepositoryResponse,
    RepositoryListResponse,
)
from app.services.repository_service import RepositoryService, get_repository_service

router = APIRouter()


@router.post(
    "/repositories/validate",
    response_model=RepositoryValidateResponse,
    summary="Validate GitHub repository URL",
    description="Checks whether a given GitHub repository URL is properly formatted and accessible without saving it.",
)
async def validate_repository_url(
    payload: RepositoryValidateRequest,
    repo_service: RepositoryService = Depends(get_repository_service),
):
    url = payload.resolved_url
    if not url:
        return RepositoryValidateResponse(
            valid=False,
            message="Please provide a valid GitHub repository URL.",
            is_accessible=False,
        )
    result = await repo_service.validate_url(url)
    return RepositoryValidateResponse(
        valid=result.get("valid", False),
        owner=result.get("owner"),
        repo=result.get("repo"),
        default_branch=result.get("default_branch"),
        message=result.get("message", "Validation completed."),
        is_accessible=result.get("is_accessible", False),
    )


@router.post(
    "/repositories",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add or update a GitHub repository to track",
    description="Validates the repository URL, retrieves repository metadata, and registers it in SkillSync.",
)
async def add_repository(
    payload: RepositoryCreate,
    db: AsyncSession = Depends(get_db),
    repo_service: RepositoryService = Depends(get_repository_service),
):
    url = payload.resolved_url
    repo = await repo_service.create_or_update_repository(db, url)
    return RepositoryResponse.from_orm_with_full_name(repo)


@router.get(
    "/repositories",
    response_model=RepositoryListResponse,
    summary="List tracked repositories",
    description="Returns a paginated list of all repositories tracked by SkillSync.",
)
async def list_repositories(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=100, description="Number of items to return"),
    db: AsyncSession = Depends(get_db),
    repo_service: RepositoryService = Depends(get_repository_service),
):
    repos, total = await repo_service.list_repositories(db, skip=skip, limit=limit)
    return RepositoryListResponse(
        repositories=[RepositoryResponse.from_orm_with_full_name(r) for r in repos],
        total=total,
    )


@router.get(
    "/repositories/{repository_id}",
    response_model=RepositoryResponse,
    summary="Get repository details",
    description="Fetch metadata and details for a tracked repository by ID.",
)
async def get_repository(
    repository_id: int,
    db: AsyncSession = Depends(get_db),
    repo_service: RepositoryService = Depends(get_repository_service),
):
    repo = await repo_service.get_repository_by_id(db, repository_id)
    return RepositoryResponse.from_orm_with_full_name(repo)


@router.delete(
    "/repositories/{repository_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a tracked repository",
    description="Removes a tracked repository and all of its associated assessments from SkillSync.",
)
async def delete_repository(
    repository_id: int,
    db: AsyncSession = Depends(get_db),
    repo_service: RepositoryService = Depends(get_repository_service),
):
    await repo_service.delete_repository(db, repository_id)
    return None


@router.get(
    "/repositories/{repository_id}/sync-status",
    summary="Get repository sync status",
    description="Retrieve synchronization status, latest analyzed commit SHA, and recent webhook deliveries.",
)
async def get_repository_sync_status(
    repository_id: int,
    db: AsyncSession = Depends(get_db),
    repo_service: RepositoryService = Depends(get_repository_service),
):
    repo = await repo_service.get_repository_by_id(db, repository_id)
    from app.models.webhook_delivery import WebhookDelivery
    deliv_stmt = (
        select(WebhookDelivery)
        .where(WebhookDelivery.repository_id == repository_id)
        .order_by(WebhookDelivery.id.desc())
        .limit(10)
    )
    deliv_res = await db.execute(deliv_stmt)
    deliveries = deliv_res.scalars().all()

    from app.models.assessment import Assessment
    assess_stmt = (
        select(Assessment)
        .where(Assessment.repository_id == repository_id)
        .order_by(Assessment.id.desc())
        .limit(1)
    )
    assess_res = await db.execute(assess_stmt)
    latest_assess = assess_res.scalar_one_or_none()

    return {
        "repository_id": repo.id,
        "full_name": repo.full_name,
        "default_branch": repo.default_branch,
        "latest_commit_sha": repo.latest_commit_sha,
        "last_synced_at": repo.updated_at.isoformat() if repo.updated_at else None,
        "sync_status": "synced" if repo.latest_commit_sha else "pending",
        "latest_assessment_version": latest_assess.version if latest_assess else None,
        "latest_score": latest_assess.overall_score if latest_assess else None,
        "webhook_endpoint": "/api/webhooks/github",
        "recent_deliveries_count": len(deliveries),
        "recent_deliveries": [
            {
                "delivery_id": d.delivery_id,
                "commit_sha": d.commit_sha,
                "status": d.status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in deliveries
        ],
    }


@router.post(
    "/repositories/{repository_id}/sync",
    summary="Trigger manual repository synchronization",
    description="Manually triggers synchronization with GitHub and reassesses all associated job profiles.",
)
async def trigger_manual_sync(
    repository_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    repo_service: RepositoryService = Depends(get_repository_service),
):
    repo = await repo_service.get_repository_by_id(db, repository_id)
    from app.services.sync_worker import execute_repository_sync
    from app.models.assessment import TriggerEvent

    background_tasks.add_task(
        execute_repository_sync,
        repository_id=repo.id,
        commit_sha=repo.latest_commit_sha,
        trigger_event=TriggerEvent.MANUAL,
    )

    return {
        "status": "queued",
        "message": f"Manual synchronization for {repo.full_name} enqueued.",
        "repository_id": repo.id,
    }
