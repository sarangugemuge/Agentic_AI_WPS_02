"""
Database migration and schema evolution manager.
Provides non-destructive schema evolution for SQLite and PostgreSQL.
Ensures zero data loss while adding tables, columns, indexes, and normalized records.
"""
import json
import logging
from typing import Dict, List, Set

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.database import Base
# Import all models to populate Base.metadata
from app.models import (  # noqa: F401
    User,
    Repository,
    JobProfile,
    JobSkillRequirement,
    Assessment,
    SkillFinding,
    EvidenceCitation,
    SkillGap,
    CommitHistory,
    WebhookDelivery,
    LearningPlan,
    LearningPlanStep,
    StepVerificationRecord,
)


logger = logging.getLogger(__name__)


async def get_existing_tables(conn: AsyncConnection, dialect_name: str) -> Set[str]:
    """Retrieve list of table names currently in the database."""
    if dialect_name == "sqlite":
        res = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
        return {row[0] for row in res.fetchall()}
    else:
        # Standard PostgreSQL / ANSI SQL
        res = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
        )
        return {row[0] for row in res.fetchall()}


async def get_table_columns(conn: AsyncConnection, table_name: str, dialect_name: str) -> Set[str]:
    """Retrieve list of column names for a given table."""
    if dialect_name == "sqlite":
        res = await conn.execute(text(f"PRAGMA table_info({table_name});"))
        return {row[1] for row in res.fetchall()}
    else:
        res = await conn.execute(
            text(f"SELECT column_name FROM information_schema.columns WHERE table_name='{table_name}';")
        )
        return {row[0] for row in res.fetchall()}


async def run_migrations(engine: AsyncEngine) -> Dict[str, Any]:
    """
    Executes safe, idempotent migrations.
    - Creates missing tables
    - Safely adds missing columns to existing tables
    - Creates missing indexes
    - Performs non-destructive backfills for normalized entities
    """
    dialect_name = engine.dialect.name
    report: Dict[str, Any] = {
        "dialect": dialect_name,
        "tables_created": [],
        "columns_added": [],
        "indexes_created": [],
        "backfills": {},
    }

    async with engine.begin() as conn:
        existing_tables_before = await get_existing_tables(conn, dialect_name)

        # 1. Create any missing tables defined in Base.metadata
        await conn.run_sync(Base.metadata.create_all)
        existing_tables_after = await get_existing_tables(conn, dialect_name)
        new_tables = existing_tables_after - existing_tables_before
        report["tables_created"] = sorted(list(new_tables))
        if new_tables:
            logger.info(f"[Migration] Created new tables: {report['tables_created']}")

        # 2. Add missing columns to pre-existing tables safely
        column_specs = [
            ("assessments", "version", "INTEGER DEFAULT 1"),
            ("skill_findings", "limitations", "TEXT"),
            ("skill_findings", "recommended_next_steps", "TEXT"),
            ("learning_plans", "objective", "TEXT"),
            ("learning_plans", "concept_explanation", "TEXT"),
            ("learning_plans", "prerequisites_json", "TEXT"),
            ("learning_plans", "current_classification", "VARCHAR(50)"),
            ("learning_plans", "existing_evidence_summary", "TEXT"),
            ("learning_plans", "missing_evidence_summary", "TEXT"),
            ("learning_plans", "repo_improvement_recommendation", "TEXT"),
            ("learning_plans", "verified_resources_json", "TEXT"),
            ("learning_plan_steps", "acceptance_criteria", "TEXT"),
            ("learning_plan_steps", "exercise", "TEXT"),
            ("learning_plan_steps", "verification_rubric", "TEXT"),
            ("step_verification_records", "learning_plan_id", "INTEGER"),
            ("step_verification_records", "original_assessment_id", "INTEGER"),
            ("step_verification_records", "evidence_type", "VARCHAR(50) DEFAULT 'code_file'"),
            ("step_verification_records", "evidence_source", "VARCHAR(100) DEFAULT 'github_repository'"),
            ("step_verification_records", "evidence_locations_json", "TEXT"),
            ("step_verification_records", "evidence_found_json", "TEXT"),
            ("step_verification_records", "rubric_findings_json", "TEXT"),
            ("step_verification_records", "limitations", "TEXT"),
            ("step_verification_records", "missing_work", "TEXT"),
            ("step_verification_records", "next_recommended_action", "TEXT"),
            ("step_verification_records", "reassessment_explanation", "TEXT"),
            ("step_verification_records", "classification_change", "VARCHAR(100)"),
        ]

        for table, col, col_def in column_specs:
            if table in existing_tables_after:
                cols = await get_table_columns(conn, table, dialect_name)
                if col not in cols:
                    try:
                        sql = f"ALTER TABLE {table} ADD COLUMN {col} {col_def};"
                        await conn.execute(text(sql))
                        report["columns_added"].append(f"{table}.{col}")
                        logger.info(f"[Migration] Added column {table}.{col}")
                    except Exception as e:
                        logger.warning(f"[Migration] Notice adding {table}.{col}: {e}")

        # 3. Create missing performance and query indexes
        indexes_to_ensure = [
            ("ix_assessments_repo_job", "assessments", ["repository_id", "job_profile_id"]),
            ("ix_assessments_repo_version", "assessments", ["repository_id", "version"]),
            ("ix_assessments_created_at", "assessments", ["created_at"]),
            ("ix_job_skills_profile_skill", "job_skill_requirements", ["job_profile_id", "skill_name"]),
            ("ix_skill_gaps_assessment_priority", "skill_gaps", ["assessment_id", "priority"]),
            ("ix_commit_history_repo_sha", "commit_history", ["repository_id", "commit_sha"]),
            ("ix_learning_plans_gap_version", "learning_plans", ["skill_gap_id", "version"]),
            ("ix_learning_plans_assessment", "learning_plans", ["assessment_id"]),
            ("ix_learning_plan_steps_plan_step", "learning_plan_steps", ["plan_id", "step_number"]),
            ("ix_step_verification_records_step", "step_verification_records", ["step_id"]),
            ("ix_step_verification_records_plan", "step_verification_records", ["learning_plan_id"]),
            ("ix_step_verification_records_orig_assess", "step_verification_records", ["original_assessment_id"]),
            ("ix_step_verification_records_subsequent_assess", "step_verification_records", ["subsequent_assessment_id"]),
        ]

        for idx_name, table, cols in indexes_to_ensure:
            if table in existing_tables_after:
                try:
                    cols_str = ", ".join(cols)
                    if dialect_name == "sqlite":
                        sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({cols_str});"
                    else:
                        sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({cols_str});"
                    await conn.execute(text(sql))
                    report["indexes_created"].append(idx_name)
                except Exception as e:
                    logger.debug(f"[Migration] Index notice {idx_name}: {e}")

        # 4. Non-destructive backfill: JobSkillRequirement from JobProfile.extracted_skills_json
        if "job_skill_requirements" in existing_tables_after and "job_profiles" in existing_tables_after:
            try:
                res = await conn.execute(
                    text("SELECT id, extracted_skills_json FROM job_profiles WHERE extracted_skills_json IS NOT NULL;")
                )
                profiles = res.fetchall()
                backfilled_skills = 0
                for pid, raw_skills_json in profiles:
                    if not raw_skills_json:
                        continue
                    try:
                        skills_list = json.loads(raw_skills_json)
                    except Exception:
                        continue

                    # Check if already populated
                    chk = await conn.execute(
                        text("SELECT COUNT(*) FROM job_skill_requirements WHERE job_profile_id = :pid"),
                        {"pid": pid},
                    )
                    count = chk.scalar() or 0
                    if count == 0 and skills_list:
                        for s in skills_list:
                            await conn.execute(
                                text(
                                    "INSERT INTO job_skill_requirements (job_profile_id, skill_name, category, importance, created_at) "
                                    "VALUES (:pid, :name, 'general', 'required', datetime('now'))"
                                ),
                                {"pid": pid, "name": s},
                            )
                            backfilled_skills += 1
                report["backfills"]["job_skill_requirements"] = backfilled_skills
                if backfilled_skills > 0:
                    logger.info(f"[Migration] Backfilled {backfilled_skills} JobSkillRequirement rows from existing job profiles.")
            except Exception as e:
                logger.warning(f"[Migration] Backfill job skills warning: {e}")

        # 5. Non-destructive backfill: SkillGap from existing non-demonstrated findings
        if "skill_gaps" in existing_tables_after and "skill_findings" in existing_tables_after:
            try:
                chk = await conn.execute(text("SELECT COUNT(*) FROM skill_gaps;"))
                gap_count = chk.scalar() or 0
                if gap_count == 0:
                    findings_res = await conn.execute(
                        text(
                            "SELECT assessment_id, skill_name, category, status, rationale, recommended_next_steps "
                            "FROM skill_findings "
                            "WHERE UPPER(CAST(status AS VARCHAR)) IN ('NOT_FOUND', 'PARTIALLY_DEMONSTRATED') "
                            "ORDER BY assessment_id, id;"
                        )
                    )
                    findings = findings_res.fetchall()
                    backfilled_gaps = 0
                    current_assessment = None
                    priority_counter = 1
                    for aid, sname, cat, stat, rat, rec in findings:
                        if aid != current_assessment:
                            current_assessment = aid
                            priority_counter = 1

                        action = rec or f"Implement practical project demonstrating {sname}."
                        desc = rat or f"Skill {sname} was {stat} in repository analysis."
                        await conn.execute(
                            text(
                                "INSERT INTO skill_gaps (assessment_id, skill_name, category, gap_severity, description, recommended_action, priority, created_at) "
                                "VALUES (:aid, :sname, :cat, :severity, :desc, :action, :prio, datetime('now'));"
                            ),
                            {
                                "aid": aid,
                                "sname": sname,
                                "cat": cat or "General",
                                "severity": stat,
                                "desc": desc,
                                "action": action,
                                "prio": priority_counter,
                            },
                        )
                        priority_counter += 1
                        backfilled_gaps += 1

                    report["backfills"]["skill_gaps"] = backfilled_gaps
                    if backfilled_gaps > 0:
                        logger.info(f"[Migration] Backfilled {backfilled_gaps} SkillGap rows from existing findings.")
            except Exception as e:
                logger.warning(f"[Migration] Backfill skill gaps warning: {e}")

        # 6. Non-destructive backfill: Assessment version numbering for existing runs
        if "assessments" in existing_tables_after:
            try:
                # Update any assessments where version IS NULL to 1
                await conn.execute(
                    text("UPDATE assessments SET version = 1 WHERE version IS NULL;")
                )
            except Exception as e:
                logger.debug(f"[Migration] Version update notice: {e}")

    return report

