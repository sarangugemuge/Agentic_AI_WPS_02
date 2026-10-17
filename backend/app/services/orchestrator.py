"""
Assessment Orchestrator — Coordinates the complete assessment lifecycle.
Executes explicit, observable steps:
  Step 1: Validate input
  Step 2: Analyze requirements
  Step 3: Obtain repository evidence
  Step 4: Compare skills
  Step 5: Validate results
  Step 6: Persist results
  Step 7: Return the assessment
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    NotFoundError,
    BusinessValidationError,
    ServiceUnavailableError,
)
from app.models.repository import Repository
from app.models.job_profile import JobProfile
from app.models.assessment import Assessment, AssessmentStatus, TriggerEvent
from app.models.skill_finding import SkillFinding, SkillStatus
from app.models.evidence import EvidenceCitation
from app.models.skill_gap import SkillGap
from app.models.commit_history import CommitHistory
from app.services.github_service import get_github_service
from app.services.ai_service import get_ai_service


logger = logging.getLogger("skillsync.orchestrator")


class AssessmentOrchestrator:
    """
    Coordinates repository analysis against job profiles.
    Follows explicit steps with strict validation, error isolation, and persistence.
    """

    def __init__(
        self,
        github_service: Any = None,
        ai_service: Any = None,
    ):
        self.github_service = github_service or get_github_service()
        self.ai_service = ai_service or get_ai_service()

    # ── Step 1: Validate Input ──────────────────────────────────────────
    async def step_1_validate_input(
        self,
        db: AsyncSession,
        repository_id: int,
        job_profile_id: Optional[int] = None,
        job_title: Optional[str] = None,
        job_description: Optional[str] = None,
        company_context: Optional[str] = None,
    ) -> Tuple[Repository, JobProfile]:
        """Verify repository exists and prepare/validate job profile."""
        logger.info(f"[Step 1/7] Validating input for repository_id={repository_id}")

        # Check repository
        repo_stmt = select(Repository).where(Repository.id == repository_id)
        repo_result = await db.execute(repo_stmt)
        repo = repo_result.scalar_one_or_none()
        if not repo:
            raise NotFoundError("Repository", repository_id)

        # Check or create JobProfile
        if job_profile_id:
            profile_stmt = select(JobProfile).where(JobProfile.id == job_profile_id)
            profile_result = await db.execute(profile_stmt)
            job_profile = profile_result.scalar_one_or_none()
            if not job_profile:
                raise NotFoundError("JobProfile", job_profile_id)
        elif job_title and job_description:
            if len(job_description.strip()) < 20:
                raise BusinessValidationError("Job description must be at least 20 characters long.")

            # Extract initial skills and create JobProfile
            skills = await self.ai_service.extract_skills(job_title.strip(), job_description.strip())
            job_profile = JobProfile(
                title=job_title.strip(),
                company_context=company_context.strip() if company_context else None,
                raw_description=job_description.strip(),
            )
            job_profile.extracted_skills = skills
            db.add(job_profile)
            await db.flush()  # assign ID
        else:
            raise BusinessValidationError(
                "Either 'job_profile_id' or both 'job_title' and 'job_description' must be provided."
            )

        logger.info(f"[Step 1/7 Passed] Repository '{repo.full_name}' and JobProfile '{job_profile.title}' validated.")
        return repo, job_profile

    # ── Step 2: Analyze Requirements ────────────────────────────────────
    async def step_2_analyze_requirements(self, job_profile: JobProfile) -> List[str]:
        """Analyze job profile text to identify key technical competencies."""
        logger.info(f"[Step 2/7] Analyzing requirements for job profile ID: {job_profile.id}")

        skills = job_profile.extracted_skills
        if not skills:
            skills = await asyncio.wait_for(
                self.ai_service.extract_skills(job_profile.title, job_profile.raw_description),
                timeout=settings.ai_timeout_seconds,
            )
            job_profile.extracted_skills = skills

        if not skills:
            raise BusinessValidationError("Failed to extract any identifiable skills from the provided job profile.")

        logger.info(f"[Step 2/7 Passed] Extracted {len(skills)} competencies: {skills}")
        return skills

    # ── Step 3: Obtain Repository Evidence ──────────────────────────────
    async def step_3_obtain_repository_evidence(
        self, repository: Repository, commit_sha: Optional[str] = None
    ) -> Dict[str, Any]:
        """Retrieve repository code artifacts, file tree, and latest commit evidence."""
        target_ref = commit_sha or repository.latest_commit_sha or repository.default_branch
        logger.info(f"[Step 3/7] Obtaining repository evidence for {repository.full_name} at ref: {target_ref}")

        try:
            evidence = await asyncio.wait_for(
                self.github_service.get_repository_evidence_artifacts(
                    owner=repository.github_owner,
                    repo=repository.repo_name,
                    branch=repository.default_branch,
                    commit_sha=commit_sha,
                ),
                timeout=settings.github_timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise ServiceUnavailableError("GitHub API", f"Timeout fetching evidence for {repository.full_name}.")

        if not evidence or not evidence.get("files"):
            raise BusinessValidationError(f"No source code files available in repository {repository.full_name}.")

        logger.info(f"[Step 3/7 Passed] Retrieved {len(evidence.get('files', []))} code artifacts from commit {evidence.get('commit_sha')}.")
        return evidence

    # ── Step 4: Compare Skills ──────────────────────────────────────────
    async def step_4_compare_skills(
        self,
        extracted_skills: List[str],
        repo_evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Match extracted requirements against repository code evidence."""
        logger.info(f"[Step 4/7] Comparing {len(extracted_skills)} skills against repository evidence")

        try:
            comparison_results = await asyncio.wait_for(
                self.ai_service.assess_skills(extracted_skills, repo_evidence),
                timeout=settings.ai_timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise ServiceUnavailableError("Gemini AI API", "Timeout during skill comparison.")

        logger.info(f"[Step 4/7 Passed] Comparison completed with overall score: {comparison_results.get('overall_score')}%")
        return comparison_results

    # ── Step 5: Validate Results ────────────────────────────────────────
    async def step_5_validate_results(self, assessment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanity check and enforce schema consistency on assessment output."""
        logger.info("[Step 5/7] Validating assessment results and citations")

        score = assessment_data.get("overall_score")
        if score is None or not (0.0 <= score <= 100.0):
            raise BusinessValidationError(f"Invalid overall assessment score: {score}. Expected 0-100.")

        findings = assessment_data.get("findings", [])
        if not findings:
            raise BusinessValidationError("Assessment generated zero skill findings.")

        valid_statuses = {s.value for s in SkillStatus}
        for f in findings:
            if not f.get("skill_name"):
                raise BusinessValidationError("Encountered skill finding without a skill_name.")
            status = f.get("status")
            if status not in valid_statuses:
                raise BusinessValidationError(f"Invalid skill status '{status}' for {f.get('skill_name')}.")

        logger.info(f"[Step 5/7 Passed] Validated {len(findings)} skill findings.")
        return assessment_data

    # ── Step 6: Persist Results ─────────────────────────────────────────
    async def step_6_persist_results(
        self,
        db: AsyncSession,
        repository: Repository,
        job_profile: JobProfile,
        assessment_data: Dict[str, Any],
        trigger_event: TriggerEvent = TriggerEvent.MANUAL,
    ) -> Assessment:
        """Atomically persist assessment, findings, and citations to database."""
        logger.info(f"[Step 6/7] Persisting assessment for repo {repository.id} and job profile {job_profile.id}")

        from datetime import datetime, timezone

        commit_sha = assessment_data.get("commit_sha") or repository.latest_commit_sha

        # 1. Determine assessment version for this repository + job profile combination
        v_stmt = select(func.count(Assessment.id)).where(
            Assessment.repository_id == repository.id,
            Assessment.job_profile_id == job_profile.id,
        )
        v_res = await db.execute(v_stmt)
        version_num = (v_res.scalar() or 0) + 1

        assessment = Assessment(
            repository_id=repository.id,
            job_profile_id=job_profile.id,
            version=version_num,
            commit_sha=commit_sha,
            overall_score=assessment_data.get("overall_score"),
            summary=assessment_data.get("summary"),
            trigger_event=trigger_event,
            status=AssessmentStatus.COMPLETED,
        )
        db.add(assessment)
        await db.flush()  # assign assessment.id

        # 2. Persist findings and citations
        findings = assessment_data.get("findings", [])
        for item in findings:
            finding = SkillFinding(
                assessment_id=assessment.id,
                skill_name=item["skill_name"],
                category=item.get("category"),
                status=SkillStatus(item["status"]),
                confidence_score=item.get("confidence_score"),
                rationale=item.get("rationale"),
                limitations=item.get("limitations"),
                recommended_next_steps=item.get("recommended_next_steps"),
            )
            db.add(finding)
            await db.flush()

            for cit in item.get("evidence_citations", []):
                citation = EvidenceCitation(
                    skill_finding_id=finding.id,
                    file_path=cit["file_path"],
                    start_line=cit.get("start_line"),
                    end_line=cit.get("end_line"),
                    commit_sha=cit.get("commit_sha") or commit_sha,
                    code_snippet=cit.get("code_snippet"),
                    context_explanation=cit.get("context_explanation"),
                )
                db.add(citation)

        # 3. Persist evidence-backed SkillGap records
        priority_counter = 1
        for item in findings:
            status_val = item.get("status")
            status_str = status_val.value if hasattr(status_val, "value") else str(status_val)
            if status_str.lower() in ("not_found", "partially_demonstrated", "manual_verification"):
                gap = SkillGap(
                    assessment_id=assessment.id,
                    skill_name=item["skill_name"],
                    category=item.get("category"),
                    gap_severity=status_str.lower(),
                    description=item.get("rationale") or item.get("limitations") or f"Skill {item['skill_name']} requires additional evidence.",
                    recommended_action=item.get("recommended_next_steps") or f"Implement practical project demonstrating {item['skill_name']}.",
                    priority=priority_counter,
                )
                db.add(gap)
                priority_counter += 1

        # 4. Record commit history revision for provenance and reproducibility
        if commit_sha:
            c_stmt = select(CommitHistory).where(
                CommitHistory.repository_id == repository.id,
                CommitHistory.commit_sha == commit_sha,
            )
            c_res = await db.execute(c_stmt)
            if not c_res.scalar_one_or_none():
                commit_record = CommitHistory(
                    repository_id=repository.id,
                    commit_sha=commit_sha,
                    commit_message=f"Assessment revision {commit_sha[:7]} for {repository.repo_name}",
                    committed_at=datetime.now(timezone.utc),
                )
                db.add(commit_record)

        await db.commit()
        logger.info(f"[Step 6/7 Passed] Successfully persisted Assessment ID {assessment.id} (version {version_num}).")
        return assessment

    # ── Step 7: Return the Assessment ───────────────────────────────────
    async def step_7_return_assessment(self, db: AsyncSession, assessment_id: int) -> Assessment:
        """Fetch complete assessment with all nested relationships for API response."""
        logger.info(f"[Step 7/7] Retrieving full Assessment ID: {assessment_id}")

        stmt = (
            select(Assessment)
            .where(Assessment.id == assessment_id)
            .options(
                selectinload(Assessment.job_profile),
                selectinload(Assessment.repository),
                selectinload(Assessment.skill_findings).selectinload(SkillFinding.evidence_citations),
                selectinload(Assessment.skill_gaps),
            )
        )
        result = await db.execute(stmt)
        assessment = result.scalar_one_or_none()
        if not assessment:
            raise NotFoundError("Assessment", assessment_id)

        logger.info(f"[Step 7/7 Complete] Assessment ID {assessment_id} ready for response.")
        return assessment


    # ── Pipeline Orchestration ──────────────────────────────────────────
    async def run_assessment(
        self,
        db: AsyncSession,
        repository_id: int,
        job_profile_id: Optional[int] = None,
        job_title: Optional[str] = None,
        job_description: Optional[str] = None,
        company_context: Optional[str] = None,
        commit_sha: Optional[str] = None,
        trigger_event: TriggerEvent = TriggerEvent.MANUAL,
    ) -> Assessment:
        """
        Execute all 7 assessment steps in sequence with state tracking,
        deterministic scoring, change delta analysis, and real-time broadcast.
        """
        logger.info(f"=== Starting Assessment Pipeline for repo {repository_id} (commit: {commit_sha}) ===")

        # Step 1: Validate Input
        repo, profile = await self.step_1_validate_input(
            db=db,
            repository_id=repository_id,
            job_profile_id=job_profile_id,
            job_title=job_title,
            job_description=job_description,
            company_context=company_context,
        )

        # Retrieve previous assessment to track score progress / regression
        prev_stmt = (
            select(Assessment)
            .where(
                Assessment.repository_id == repo.id,
                Assessment.job_profile_id == profile.id,
                Assessment.status == AssessmentStatus.COMPLETED,
            )
            .order_by(Assessment.id.desc())
            .limit(1)
        )
        prev_res = await db.execute(prev_stmt)
        prev_assessment = prev_res.scalar_one_or_none()
        previous_score = prev_assessment.overall_score if prev_assessment else None

        try:
            # Step 2: Analyze Requirements
            extracted_skills = await self.step_2_analyze_requirements(profile)

            # Step 3: Obtain Repository Evidence at specific commit SHA
            repo_evidence = await self.step_3_obtain_repository_evidence(repo, commit_sha=commit_sha)
            actual_commit_sha = repo_evidence.get("commit_sha") or commit_sha or repo.latest_commit_sha

            # Inspect commit metadata for doc-only changes or deletions
            commit_details = await self.github_service.get_commit_details(
                repo.github_owner, repo.repo_name, actual_commit_sha
            )
            is_doc_only = commit_details.get("is_doc_only", False)
            changed_files = commit_details.get("changed_files", [])

            # Step 4: Compare Skills
            comparison = await self.step_4_compare_skills(extracted_skills, repo_evidence)

            # Step 5: Validate Results & Enforce Deterministic Scoring Rubric
            validated_data = await self.step_5_validate_results(comparison)

            from app.services.scoring_engine import ScoringEngine
            raw_score, score_breakdown = ScoringEngine.calculate_score(validated_data.get("findings", []))
            delta_info = ScoringEngine.analyze_score_delta(
                previous_score=previous_score,
                new_score=raw_score,
                is_doc_only=is_doc_only,
                changed_files=changed_files,
            )

            validated_data["overall_score"] = delta_info["new_score"]
            validated_data["commit_sha"] = actual_commit_sha
            validated_data["summary"] = f"{delta_info['explanation']} {validated_data.get('summary', '')}".strip()

            # Step 6: Persist Results
            saved_assessment = await self.step_6_persist_results(
                db=db,
                repository=repo,
                job_profile=profile,
                assessment_data=validated_data,
                trigger_event=trigger_event,
            )

            # Step 7: Return Assessment
            completed_assessment = await self.step_7_return_assessment(db, saved_assessment.id)

            # Broadcast real-time SSE notification to connected frontend clients
            from app.services.event_broadcaster import get_broadcaster
            broadcaster = get_broadcaster()
            await broadcaster.broadcast(
                "assessment_completed",
                {
                    "assessment_id": completed_assessment.id,
                    "repository_id": repo.id,
                    "repository_name": repo.full_name,
                    "job_profile_id": profile.id,
                    "job_title": profile.title,
                    "version": completed_assessment.version,
                    "previous_score": previous_score,
                    "new_score": delta_info["new_score"],
                    "delta": delta_info["delta"],
                    "direction": delta_info["direction"],
                    "explanation": delta_info["explanation"],
                    "commit_sha": actual_commit_sha,
                    "trigger_event": trigger_event.value if hasattr(trigger_event, "value") else str(trigger_event),
                },
            )

            return completed_assessment

        except Exception as exc:
            logger.error(f"Assessment pipeline encountered an error: {str(exc)}", exc_info=True)
            failed_assessment = Assessment(
                repository_id=repo.id,
                job_profile_id=profile.id,
                status=AssessmentStatus.FAILED,
                trigger_event=trigger_event,
                error_message=str(exc),
            )
            db.add(failed_assessment)
            await db.commit()
            raise


def get_orchestrator() -> AssessmentOrchestrator:
    """FastAPI dependency provider for AssessmentOrchestrator."""
    return AssessmentOrchestrator()
