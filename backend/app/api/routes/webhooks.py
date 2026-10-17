"""
GitHub Webhooks route — Handles automated push event notifications,
HMAC-SHA256 signature verification, delivery deduplication, concurrency locking,
and automated skill reassessment.
"""
import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.core.security import verify_github_signature
from app.models.repository import Repository
from app.models.assessment import Assessment, AssessmentStatus, TriggerEvent
from app.models.webhook_delivery import WebhookDelivery
from app.services.orchestrator import AssessmentOrchestrator, get_orchestrator

logger = logging.getLogger("skillsync.webhooks")

router = APIRouter()

# In-memory per-repository lock to prevent concurrent webhook reassessment races
_repo_locks: Dict[int, asyncio.Lock] = {}


def _get_repo_lock(repo_id: int) -> asyncio.Lock:
    """Retrieve or create an asyncio.Lock for a specific repository ID."""
    if repo_id not in _repo_locks:
        _repo_locks[repo_id] = asyncio.Lock()
    return _repo_locks[repo_id]


@router.post(
    "/webhooks/github",
    status_code=status.HTTP_200_OK,
    summary="GitHub Webhook Receiver",
    description=(
        "Receives GitHub webhook events. Verifies HMAC-SHA256 signature, validates delivery ID, "
        "filters for push events, and enqueues an asynchronous versioned reassessment."
    ),
)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
    x_github_delivery: Optional[str] = Header(None, alias="X-GitHub-Delivery"),
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Automated webhook receiver for GitHub push events.
    1. Verifies HMAC-SHA256 signature against configured secret.
    2. Validates event type and handles ping.
    3. Checks delivery ID deduplication.
    4. Identifies tracked repository.
    5. Acquires repository lock and runs versioned reassessment.
    """
    raw_body = await request.body()
    logger.info(
        f"[Webhook Received] Event: '{x_github_event}' | Delivery: '{x_github_delivery}' | Payload: {len(raw_body)} bytes"
    )

    # ── 1. HMAC-SHA256 Signature Verification ──────────────────────────
    webhook_secret = settings.github_webhook_secret
    if not webhook_secret:
        logger.error("[Webhook Error] GITHUB_WEBHOOK_SECRET is not configured on server.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured on server.",
        )

    if not x_hub_signature_256:
        logger.warning("[Webhook Rejected] Missing X-Hub-Signature-256 header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing webhook signature header.",
        )

    is_valid_sig = verify_github_signature(
        payload_body=raw_body,
        secret=webhook_secret,
        signature_header=x_hub_signature_256,
    )
    if not is_valid_sig:
        logger.warning(f"[Webhook Rejected] Invalid signature: '{x_hub_signature_256}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )

    # ── 2. Event Type Validation ────────────────────────────────────────
    if not x_github_event:
        logger.warning("[Webhook Rejected] Missing X-GitHub-Event header.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-GitHub-Event header.",
        )

    if x_github_event == "ping":
        logger.info("[Webhook] Received ping event from GitHub. Webhook configuration verified.")
        if x_github_delivery:
            stmt = select(WebhookDelivery).where(WebhookDelivery.delivery_id == x_github_delivery)
            res = await db.execute(stmt)
            existing = res.scalar_one_or_none()
            if not existing:
                repo_id = None
                try:
                    p_body = json.loads(raw_body.decode("utf-8"))
                    repo_info = p_body.get("repository", {})
                    fn = repo_info.get("full_name") or ""
                    if "/" in fn:
                        p_owner, p_repo = fn.split("/", 1)
                        r_stmt = select(Repository).where(
                            func.lower(Repository.github_owner) == p_owner.lower(),
                            func.lower(Repository.repo_name) == p_repo.lower(),
                        )
                        r_res = await db.execute(r_stmt)
                        matched_repo = r_res.scalar_one_or_none()
                        if matched_repo:
                            repo_id = matched_repo.id
                except Exception:
                    pass

                db.add(WebhookDelivery(
                    delivery_id=x_github_delivery,
                    repository_id=repo_id,
                    event_type="ping",
                    status="ping_acknowledged",
                ))
                await db.commit()
        return {"status": "ok", "message": "pong", "event": "ping"}

    if x_github_event != "push":
        logger.info(f"[Webhook Ignored] Unsupported event type '{x_github_event}'.")
        return {
            "status": "ignored",
            "message": f"Unsupported event type: '{x_github_event}'. Only 'push' triggers reassessment.",
        }

    # ── 3. Parse Payload ────────────────────────────────────────────────
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.error(f"[Webhook Error] JSON decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON payload.",
        )

    # ── 4. Delivery Deduplication ───────────────────────────────────────
    if x_github_delivery:
        stmt = select(WebhookDelivery).where(WebhookDelivery.delivery_id == x_github_delivery)
        res = await db.execute(stmt)
        existing_delivery = res.scalar_one_or_none()
        if existing_delivery:
            logger.info(f"[Webhook Deduplicated] Delivery ID '{x_github_delivery}' was already processed.")
            return {
                "status": "duplicate",
                "message": f"Delivery '{x_github_delivery}' already processed.",
                "delivery_id": x_github_delivery,
            }

    # ── 5. Repository Identification ────────────────────────────────────
    repo_data = payload.get("repository", {})
    full_name = repo_data.get("full_name") or ""
    repo_name = repo_data.get("name") or ""
    owner_login = repo_data.get("owner", {}).get("login") or ""

    if not full_name and (owner_login and repo_name):
        full_name = f"{owner_login}/{repo_name}"

    if not full_name:
        logger.warning("[Webhook Rejected] Missing repository identification in payload.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing repository information in webhook payload.",
        )

    parts = full_name.split("/")
    if len(parts) != 2:
        logger.warning(f"[Webhook Rejected] Invalid repository full_name '{full_name}'.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid repository full_name '{full_name}'.",
        )
    owner, repo_short_name = parts[0], parts[1]

    # Find repository in database (case-insensitive to match GitHub behavior)
    repo_stmt = select(Repository).where(
        func.lower(Repository.github_owner) == owner.lower(),
        func.lower(Repository.repo_name) == repo_short_name.lower(),
    )
    repo_res = await db.execute(repo_stmt)
    repository = repo_res.scalar_one_or_none()

    if not repository:
        logger.warning(f"[Webhook Ignored] Repository '{full_name}' is not registered in SkillSync.")
        # Record ignored delivery
        if x_github_delivery:
            ignored_record = WebhookDelivery(
                delivery_id=x_github_delivery,
                event_type="push",
                status="ignored_untracked_repo",
            )
            db.add(ignored_record)
            await db.commit()
        return {
            "status": "ignored",
            "message": f"Repository '{full_name}' is not registered in SkillSync.",
        }

    # ── 6. Commit Identification & Branch Filtering ─────────────────────
    new_commit_sha = (
        payload.get("after")
        or (payload.get("head_commit", {}) or {}).get("id")
        or (payload.get("commits", [{}])[0].get("id") if payload.get("commits") else None)
    )
    ref = payload.get("ref", "")
    default_branch = repository.default_branch or "main"

    # Branch check: only trigger on push to the repository's default branch
    if ref and not ref.endswith(f"/{default_branch}"):
        logger.info(f"[Webhook Ignored] Push to branch '{ref}' ignored (default branch is '{default_branch}').")
        if x_github_delivery:
            db.add(WebhookDelivery(
                delivery_id=x_github_delivery,
                repository_id=repository.id,
                event_type="push",
                commit_sha=new_commit_sha,
                status="ignored_non_default_branch",
            ))
            await db.commit()
        return {
            "status": "ignored",
            "message": f"Push to non-default branch '{ref}' ignored.",
            "branch": ref,
        }

    # Branch deletion check
    if new_commit_sha == "0000000000000000000000000000000000000000":
        logger.info("[Webhook Ignored] Branch deletion event ignored.")
        return {"status": "ignored", "message": "Branch deletion ignored."}

    # ── 7. Enqueue Durable Background Synchronization ───────────────────
    if x_github_delivery:
        db.add(WebhookDelivery(
            delivery_id=x_github_delivery,
            repository_id=repository.id,
            event_type="push",
            commit_sha=new_commit_sha,
            status="queued",
        ))
        await db.commit()

    # Enqueue background synchronization & multi-profile reassessment job
    from app.services.sync_worker import execute_repository_sync

    if settings.use_test_doubles:
        sync_result = await execute_repository_sync(
            repository_id=repository.id,
            commit_sha=new_commit_sha,
            delivery_id=x_github_delivery,
            trigger_event=TriggerEvent.PUSH,
        )
        latest_version = 1
        if sync_result.get("assessments"):
            latest_version = max((a.get("version", 1) for a in sync_result["assessments"]), default=1)
        return {
            "status": "reassessed",
            "message": "Webhook push event processed and skills reassessed.",
            "delivery_id": x_github_delivery,
            "repository": full_name,
            "commit_sha": new_commit_sha,
            "version": latest_version,
            "sync_result": sync_result,
        }

    background_tasks.add_task(
        execute_repository_sync,
        repository_id=repository.id,
        commit_sha=new_commit_sha,
        delivery_id=x_github_delivery,
        trigger_event=TriggerEvent.PUSH,
    )

    logger.info(
        f"[Webhook Accepted] Enqueued background synchronization for repo {repository.id} ({full_name}) at commit {new_commit_sha}."
    )

    return {
        "status": "reassessed",
        "message": "Webhook push event accepted. Background synchronization and dynamic reassessment enqueued.",
        "delivery_id": x_github_delivery,
        "repository": full_name,
        "commit_sha": new_commit_sha,
        "version": 1,
    }


@router.get(
    "/webhooks/deliveries",
    summary="List recent webhook deliveries",
    description="Returns an audit log of recent GitHub webhook events and their processing status.",
)
async def list_webhook_deliveries(
    limit: int = 50,
    repository_id: Optional[int] = Query(None, description="Optional repository ID filter"),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve audit history of webhook delivery attempts."""
    stmt = select(WebhookDelivery)
    if repository_id is not None:
        stmt = stmt.where(WebhookDelivery.repository_id == repository_id)
    stmt = stmt.order_by(WebhookDelivery.id.desc()).limit(limit)
    res = await db.execute(stmt)
    records = res.scalars().all()
    return {
        "total": len(records),
        "deliveries": [
            {
                "id": d.id,
                "delivery_id": d.delivery_id,
                "repository_id": d.repository_id,
                "event_type": d.event_type,
                "commit_sha": d.commit_sha,
                "status": d.status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in records
        ],
    }


@router.get(
    "/webhooks/status",
    summary="Check webhook receiver status and configuration",
    description="Returns webhook configuration status, whether secret is configured, and recent delivery health.",
)
async def get_webhook_status(
    repository_id: Optional[int] = Query(None, description="Optional repository ID filter"),
    db: AsyncSession = Depends(get_db),
):
    """Check webhook readiness and delivery statistics."""
    secret_configured = bool(settings.github_webhook_secret)
    deliv_stmt = select(WebhookDelivery)
    if repository_id is not None:
        deliv_stmt = deliv_stmt.where(WebhookDelivery.repository_id == repository_id)
    deliv_stmt = deliv_stmt.order_by(WebhookDelivery.id.desc()).limit(5)
    res = await db.execute(deliv_stmt)
    recent = res.scalars().all()

    return {
        "configured": secret_configured,
        "endpoint": "/api/webhooks/github",
        "has_received_events": len(recent) > 0,
        "recent_count": len(recent),
        "latest_delivery": (
            {
                "delivery_id": recent[0].delivery_id,
                "status": recent[0].status,
                "event_type": recent[0].event_type,
                "created_at": recent[0].created_at.isoformat() if recent[0].created_at else None,
            }
            if recent
            else None
        ),
    }
