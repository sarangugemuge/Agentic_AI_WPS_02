"""
Tests for Phase 6: Owner-Controlled Database Persistence.
Verifies:
1. DATABASE_URL normalization and engine configuration.
2. Complete entity CRUD: User, Repository, JobProfile, JobSkillRequirement,
   Assessment, SkillFinding, EvidenceCitation, SkillGap, CommitHistory.
3. Multi-version assessment tracking for the same repo + job profile.
4. True persistence across application / engine restarts.
5. Migration idempotency and non-destructive execution.
"""
import os
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select, func

from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.database import get_normalized_database_url
from app.core.migrations import run_migrations
from app.models.user import User
from app.models.repository import Repository
from app.models.job_profile import JobProfile
from app.models.job_skill_requirement import JobSkillRequirement
from app.models.assessment import Assessment, AssessmentStatus, TriggerEvent
from app.models.skill_finding import SkillFinding, SkillStatus
from app.models.evidence import EvidenceCitation
from app.models.skill_gap import SkillGap
from app.models.commit_history import CommitHistory


def test_database_url_normalization():
    """Verify that raw driverless URLs are properly normalized for async engines."""
    assert get_normalized_database_url("sqlite:///./test.db") == "sqlite+aiosqlite:///./test.db"
    assert get_normalized_database_url("sqlite+aiosqlite:///./test.db") == "sqlite+aiosqlite:///./test.db"
    assert (
        get_normalized_database_url("postgresql://user:pass@localhost:5432/db")
        == "postgresql+asyncpg://user:pass@localhost:5432/db"
    )
    assert (
        get_normalized_database_url("postgres://user:pass@localhost:5432/db")
        == "postgresql+asyncpg://user:pass@localhost:5432/db"
    )


async def test_entity_creation_and_relationships():
    """Verify all 8 entities and their cross-relationships."""
    test_db_url = "sqlite+aiosqlite:///:memory:"
    test_engine = create_async_engine(test_db_url, echo=False)
    await run_migrations(test_engine)

    Session = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        # 1. User
        user = User(
            username="owner_user",
            email="owner@skillsync.local",
            full_name="SkillSync Project Owner",
            is_owner=True,
        )
        session.add(user)

        # 2. Repository
        repo = Repository(
            github_owner="test-owner",
            repo_name="test-repo",
            default_branch="main",
            latest_commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            language="Python",
        )
        session.add(repo)
        await session.flush()

        # 3. Commit History
        commit = CommitHistory(
            repository_id=repo.id,
            commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            commit_message="Initial commit with FastAPI endpoints",
            author_name="Owner Dev",
            committed_at=datetime.now(timezone.utc),
        )
        session.add(commit)

        # 4. Job Profile & JobSkillRequirement
        job = JobProfile(
            title="Backend Architect",
            company_context="Tech Corp",
            raw_description="Looking for an experienced Python developer with FastAPI and PostgreSQL.",
        )
        job.extracted_skills = ["Python", "FastAPI", "PostgreSQL"]
        session.add(job)
        await session.flush()

        req1 = JobSkillRequirement(job_profile_id=job.id, skill_name="Python", importance="required")
        req2 = JobSkillRequirement(job_profile_id=job.id, skill_name="FastAPI", importance="required")
        session.add_all([req1, req2])

        # 5. Assessment (Version 1)
        assessment_v1 = Assessment(
            repository_id=repo.id,
            job_profile_id=job.id,
            version=1,
            commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            overall_score=75.0,
            summary="Demonstrates strong Python and FastAPI foundational knowledge.",
            status=AssessmentStatus.COMPLETED,
        )
        session.add(assessment_v1)
        await session.flush()

        # 6. Skill Findings and Evidence
        finding = SkillFinding(
            assessment_id=assessment_v1.id,
            skill_name="FastAPI",
            category="Backend Framework",
            status=SkillStatus.DEMONSTRATED,
            confidence_score=90.0,
            rationale="Multiple routers defined using APIRouter.",
            limitations="No custom middleware found.",
            recommended_next_steps="Add rate limiting middleware.",
        )
        session.add(finding)
        await session.flush()

        evidence = EvidenceCitation(
            skill_finding_id=finding.id,
            file_path="app/main.py",
            start_line=1,
            end_line=25,
            commit_sha=assessment_v1.commit_sha,
            code_snippet="app = FastAPI()",
            context_explanation="Application entrypoint",
        )
        session.add(evidence)

        # 7. Skill Gap
        gap = SkillGap(
            assessment_id=assessment_v1.id,
            skill_name="PostgreSQL",
            category="Database",
            gap_severity="missing",
            description="No PostgreSQL migrations or models detected.",
            recommended_action="Introduce asyncpg integration with migration scripts.",
            priority=1,
        )
        session.add(gap)

        # 8. Assessment (Version 2 for the same repo and job profile)
        assessment_v2 = Assessment(
            repository_id=repo.id,
            job_profile_id=job.id,
            version=2,
            commit_sha="b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
            overall_score=92.0,
            summary="Added PostgreSQL support, score improved.",
            status=AssessmentStatus.COMPLETED,
        )
        session.add(assessment_v2)

        await session.commit()

    # Query back and verify relationships
    async with Session() as session:
        # Verify user
        u = await session.execute(select(User).where(User.username == "owner_user"))
        loaded_user = u.scalar_one()
        assert loaded_user.is_owner is True
        assert loaded_user.email == "owner@skillsync.local"

        # Verify repo & commits
        r = await session.execute(
            select(Repository).where(Repository.id == repo.id).options(selectinload(Repository.commits))
        )
        loaded_repo = r.scalar_one()
        assert len(loaded_repo.commits) == 1
        assert loaded_repo.commits[0].commit_sha == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"

        # Verify job profile & requirements
        j = await session.execute(
            select(JobProfile).where(JobProfile.id == job.id).options(selectinload(JobProfile.skill_requirements))
        )
        loaded_job = j.scalar_one()
        assert len(loaded_job.skill_requirements) == 2

        # Verify multiple versions preserved
        assessments_stmt = (
            select(Assessment)
            .where(Assessment.repository_id == repo.id, Assessment.job_profile_id == job.id)
            .order_by(Assessment.version.asc())
            .options(
                selectinload(Assessment.skill_findings).selectinload(SkillFinding.evidence_citations),
                selectinload(Assessment.skill_gaps),
            )
        )
        res = await session.execute(assessments_stmt)
        versions = list(res.scalars().all())
        assert len(versions) == 2
        assert versions[0].version == 1
        assert versions[0].overall_score == 75.0
        assert len(versions[0].skill_findings) == 1
        assert len(versions[0].skill_findings[0].evidence_citations) == 1
        assert len(versions[0].skill_gaps) == 1

        assert versions[1].version == 2
        assert versions[1].overall_score == 92.0

    await test_engine.dispose()


async def test_persistence_across_application_restarts():
    """Simulate total application shutdown and restart on an owner-controlled file DB."""
    temp_db_path = "persistence_restart_verification.db"
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)

    db_url = f"sqlite+aiosqlite:///{temp_db_path}"

    try:
        # === APPLICATION RUN 1 (Start app, run migrations, save records) ===
        engine_run_1 = create_async_engine(db_url, echo=False)
        await run_migrations(engine_run_1)
        Session1 = async_sessionmaker(bind=engine_run_1, class_=AsyncSession, expire_on_commit=False)

        async with Session1() as session:
            repo = Repository(
                github_owner="persist-owner",
                repo_name="persist-project",
                default_branch="main",
                latest_commit_sha="deadbeef1234567890abcdef1234567890abcdef",
            )
            session.add(repo)
            await session.flush()

            job = JobProfile(
                title="Lead SRE",
                raw_description="Looking for SRE with Kubernetes, Terraform, and Python.",
            )
            job.extracted_skills = ["Kubernetes", "Terraform", "Python"]
            session.add(job)
            await session.flush()

            assessment = Assessment(
                repository_id=repo.id,
                job_profile_id=job.id,
                version=1,
                commit_sha="deadbeef1234567890abcdef1234567890abcdef",
                overall_score=88.5,
                summary="Robust automated infrastructure discovered.",
                status=AssessmentStatus.COMPLETED,
            )
            session.add(assessment)
            await session.flush()

            gap = SkillGap(
                assessment_id=assessment.id,
                skill_name="Terraform",
                gap_severity="partially_demonstrated",
                description="Terraform config files present but lacked automated validation.",
                recommended_action="Add tflint / checkov in CI workflow.",
                priority=1,
            )
            session.add(gap)

            commit = CommitHistory(
                repository_id=repo.id,
                commit_sha="deadbeef1234567890abcdef1234567890abcdef",
                commit_message="Add CI deployment pipeline",
                author_name="DevOps Engineer",
                committed_at=datetime.now(timezone.utc),
            )
            session.add(commit)

            saved_assessment_id = assessment.id
            saved_repo_id = repo.id
            saved_job_id = job.id
            await session.commit()

        # === APPLICATION SHUTDOWN (dispose engine, drop all connections) ===
        await engine_run_1.dispose()

        # === APPLICATION RUN 2 (Start brand new app instance, connect to same DB) ===
        engine_run_2 = create_async_engine(db_url, echo=False)
        await run_migrations(engine_run_2)  # must be idempotent
        Session2 = async_sessionmaker(bind=engine_run_2, class_=AsyncSession, expire_on_commit=False)

        async with Session2() as session:
            # Query the assessment saved in Run 1
            stmt = (
                select(Assessment)
                .where(Assessment.id == saved_assessment_id)
                .options(
                    selectinload(Assessment.repository).selectinload(Repository.commits),
                    selectinload(Assessment.job_profile),
                    selectinload(Assessment.skill_gaps),
                )
            )
            res = await session.execute(stmt)
            loaded = res.scalar_one()

            assert loaded.id == saved_assessment_id
            assert loaded.overall_score == 88.5
            assert loaded.version == 1
            assert loaded.commit_sha == "deadbeef1234567890abcdef1234567890abcdef"
            assert loaded.repository.repo_name == "persist-project"
            assert len(loaded.repository.commits) == 1
            assert loaded.repository.commits[0].commit_sha == "deadbeef1234567890abcdef1234567890abcdef"
            assert loaded.job_profile.title == "Lead SRE"
            assert len(loaded.skill_gaps) == 1
            assert loaded.skill_gaps[0].skill_name == "Terraform"
            assert loaded.skill_gaps[0].priority == 1

        await engine_run_2.dispose()

    finally:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)
