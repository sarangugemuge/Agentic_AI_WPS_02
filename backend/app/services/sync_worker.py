"""
SkillSync Repository Sync Worker — Asynchronous, durable background worker
responsible for synchronizing repository updates and dynamically reassessing
all associated candidate job profiles without blocking webhooks.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models.repository import Repository
from app.models.job_profile import JobProfile
from app.models.assessment import Assessment, AssessmentStatus, TriggerEvent
from app.models.webhook_delivery import WebhookDelivery
from app.services.orchestrator import get_orchestrator
from app.services.event_broadcaster import get_broadcaster

logger = logging.getLogger("skillsync.services.sync_worker")

# Per-repository lock to prevent concurrent sync races on rapid consecutive pushes
_repo_locks: Dict[int, asyncio.Lock] = {}


def get_repo_lock(repo_id: int) -> asyncio.Lock:
    if repo_id not in _repo_locks:
        _repo_locks[repo_id] = asyncio.Lock()
    return _repo_locks[repo_id]


async def execute_repository_sync(
    repository_id: int,
    commit_sha: Optional[str] = None,
    delivery_id: Optional[str] = None,
    trigger_event: TriggerEvent = TriggerEvent.PUSH,
) -> Dict[str, Any]:
    """
    Background worker task to synchronize a repository and reassess all associated job profiles.
    Runs asynchronously and broadcasts live updates via Server-Sent Events (SSE).
    """
    broadcaster = get_broadcaster()
    orchestrator = get_orchestrator()
    lock = get_repo_lock(repository_id)

    async with lock:
        async with async_session_factory() as db:
            # 1. Fetch Repository
            repo_stmt = select(Repository).where(Repository.id == repository_id)
            repo_res = await db.execute(repo_stmt)
            repository = repo_res.scalar_one_or_none()

            if not repository:
                logger.error(f"[Sync Worker] Repository ID {repository_id} not found.")
                return {"status": "error", "message": "Repository not found"}

            effective_sha = commit_sha or repository.latest_commit_sha or "HEAD"

            # Broadcast sync start
            await broadcaster.broadcast(
                "sync_started",
                {
                    "repository_id": repository.id,
                    "repository_name": repository.full_name,
                    "commit_sha": effective_sha,
                    "status": "syncing",
                    "message": f"Synchronizing repository {repository.full_name} at commit {effective_sha[:7] if len(effective_sha) >= 7 else effective_sha}...",
                },
            )

            # 2. Identify ALL target job profiles associated with this repository
            # Find all profiles assessed against this repo or all existing profiles
            profile_ids_stmt = (
                select(Assessment.job_profile_id)
                .where(Assessment.repository_id == repository.id)
                .distinct()
            )
            profile_ids_res = await db.execute(profile_ids_stmt)
            associated_profile_ids = [row[0] for row in profile_ids_res.fetchall()]

            if not associated_profile_ids:
                # If never assessed against this repo, grab latest job profiles
                all_profiles_stmt = select(JobProfile.id).order_by(JobProfile.id.desc()).limit(5)
                all_res = await db.execute(all_profiles_stmt)
                associated_profile_ids = [row[0] for row in all_res.fetchall()]

            if not associated_profile_ids:
                logger.warning(f"[Sync Worker] No job profiles found to assess for repository {repository.id}.")
                await broadcaster.broadcast(
                    "sync_progress",
                    {
                        "repository_id": repository.id,
                        "message": "Repository synchronized, but no saved job profiles exist to evaluate.",
                    },
                )
                return {"status": "synced_no_profiles", "repository": repository.full_name}

            logger.info(
                f"[Sync Worker] Found {len(associated_profile_ids)} job profile(s) to reassess for {repository.full_name}."
            )

            # 3. Reassess Each Associated Job Profile Dynamically
            completed_assessments = []
            errors = []

            for idx, profile_id in enumerate(associated_profile_ids, 1):
                try:
                    await broadcaster.broadcast(
                        "sync_progress",
                        {
                            "repository_id": repository.id,
                            "profile_index": idx,
                            "total_profiles": len(associated_profile_ids),
                            "message": f"Analyzing evidence for profile {idx}/{len(associated_profile_ids)}...",
                        },
                    )

                    assessment = await orchestrator.run_assessment(
                        db=db,
                        repository_id=repository.id,
                        job_profile_id=profile_id,
                        commit_sha=effective_sha if effective_sha != "HEAD" else None,
                        trigger_event=trigger_event,
                    )

                    completed_assessments.append({
                        "profile_id": profile_id,
                        "assessment_id": assessment.id,
                        "score": assessment.overall_score,
                        "version": assessment.version,
                    })

                except Exception as exc:
                    logger.error(
                        f"[Sync Worker Error] Reassessment failed for profile {profile_id}: {exc}",
                        exc_info=True,
                    )
                    errors.append({"profile_id": profile_id, "error": str(exc)})

            # 4. Update Repository Synchronization Metadata
            repository.latest_commit_sha = effective_sha if effective_sha != "HEAD" else repository.latest_commit_sha
            repository.updated_at = datetime.now(timezone.utc)
            await db.commit()

            # 5. Update Webhook Delivery record if applicable
            if delivery_id:
                delivery_status = "processed" if completed_assessments else ("failed" if errors else "processed")
                await db.execute(
                    update(WebhookDelivery)
                    .where(WebhookDelivery.delivery_id == delivery_id)
                    .values(
                        status=delivery_status,
                        commit_sha=effective_sha if effective_sha != "HEAD" else None,
                        repository_id=repository.id,
                    )
                )
                await db.commit()

            # 6. Broadcast Sync Completion
            summary_payload = {
                "repository_id": repository.id,
                "repository_name": repository.full_name,
                "commit_sha": effective_sha,
                "completed_count": len(completed_assessments),
                "total_profiles": len(associated_profile_ids),
                "assessments": completed_assessments,
                "errors": errors,
                "message": f"Synchronization completed. Reassessed {len(completed_assessments)} job profiles.",
            }
            await broadcaster.broadcast("sync_completed", summary_payload)

            return summary_payload
