"""
Phase 5 Tests — SkillSync AI Assessment Engine, Schema Enforcement, and Anti-Hallucination.
Verifies skill classification, uncertainty handling, ground-truth citation verification,
and graceful handling of missing or invalid LLM configurations.
"""
from app.models.skill_finding import SkillStatus
from app.schemas.ai_schemas import (
    JobSkillExtractionResult,
    ExtractedSkillItem,
    AIAssessmentOutput,
    AISkillFinding,
    AIEvidenceCitation,
)
from app.services.evidence_verifier import EvidenceVerifier
from app.services.gemini_engine import GeminiEngine
from app.services.ai_service import MockAIService, AIService
from app.core.exceptions import ServiceUnavailableError


def test_ai_schema_validation_success():
    """Verify that AIAssessmentOutput strictly validates compliant structured outputs."""
    valid_data = {
        "overall_score": 85.0,
        "summary": "Candidate demonstrated strong backend skills with Python and FastAPI.",
        "findings": [
            {
                "skill_name": "FastAPI",
                "category": "Web Frameworks",
                "status": "demonstrated",
                "confidence_score": 0.95,
                "rationale": "High code coverage and modular route setup.",
                "limitations": "Telemetry tracing not configured.",
                "recommended_next_steps": "Add OpenTelemetry instrumentation.",
                "evidence_citations": [
                    {
                        "file_path": "backend/app/main.py",
                        "start_line": 1,
                        "end_line": 20,
                        "code_snippet": "from fastapi import FastAPI\napp = FastAPI()",
                        "context_explanation": "FastAPI instantiated with lifecycle hooks.",
                    }
                ],
            }
        ],
        "skill_gaps": ["Docker"],
        "prioritized_learning_recommendations": [
            "Add a multi-stage Dockerfile to containerize the service."
        ],
    }
    output = AIAssessmentOutput.model_validate(valid_data)
    assert output.overall_score == 85.0
    assert len(output.findings) == 1
    assert output.findings[0].skill_name == "FastAPI"
    assert output.findings[0].status == "demonstrated"
    assert len(output.findings[0].evidence_citations) == 1


def test_anti_hallucination_verifier_discards_invented_files():
    """
    Task 10: Store only verified evidence references; never invent code, file paths, or commits.
    If LLM hallucinates a file path that doesn't exist in repo evidence, it MUST be discarded.
    """
    repo_evidence = {
        "owner": "testorg",
        "repo": "testrepo",
        "commit_sha": "abc12345",
        "files": [
            {"path": "real/app.py", "language": "Python", "snippet": "print('real')"}
        ],
    }

    raw_llm_data = {
        "overall_score": 90.0,
        "summary": "Test summary",
        "findings": [
            {
                "skill_name": "Kubernetes",
                "category": "DevOps",
                "status": "demonstrated",
                "confidence_score": 0.9,
                "rationale": "Claimed deployment in k8s/deployment.yaml",
                "evidence_citations": [
                    {
                        "file_path": "k8s/deployment.yaml",  # Does NOT exist in repo_evidence!
                        "start_line": 1,
                        "end_line": 10,
                        "code_snippet": "apiVersion: apps/v1",
                        "context_explanation": "Fake deployment manifest",
                    }
                ],
            }
        ],
    }

    sanitized = EvidenceVerifier.verify_and_sanitize_assessment_output(raw_llm_data, repo_evidence)
    finding = sanitized["findings"][0]

    # The invented citation must have been rejected
    assert len(finding["evidence_citations"]) == 0
    # Status must be downgraded because there are no verifiable citations
    assert finding["status"] == SkillStatus.PARTIALLY_DEMONSTRATED.value


def test_missing_evidence_distinction():
    """
    Task 11: Keep missing evidence distinct from a conclusion that the student lacks a skill.
    """
    repo_evidence = {
        "owner": "testorg",
        "repo": "testrepo",
        "commit_sha": "abc12345",
        "files": [],
    }

    raw_llm_data = {
        "overall_score": 0.0,
        "summary": "No matching code",
        "findings": [
            {
                "skill_name": "AWS",
                "category": "Cloud Infrastructure",
                "status": "not_found",
                "confidence_score": 0.1,
                "rationale": "No AWS infrastructure manifests found.",
                "evidence_citations": [],
            }
        ],
    }

    sanitized = EvidenceVerifier.verify_and_sanitize_assessment_output(raw_llm_data, repo_evidence)
    finding = sanitized["findings"][0]
    assert finding["status"] == "not_found"
    # Verifier appends clear note regarding repository scope
    assert "does not imply a lack of developer proficiency" in finding["rationale"]


def test_gemini_engine_missing_key_behavior():
    """
    Task 9: Handle unavailable LLM services cleanly without crashing.
    When API key is not configured, GeminiEngine raises ServiceUnavailableError.
    """
    engine = GeminiEngine(api_key="")
    try:
        engine._get_client()
        assert False, "Should have raised ServiceUnavailableError"
    except ServiceUnavailableError as exc:
        assert "GEMINI_API_KEY is not configured" in exc.message


async def test_ai_service_fallback_when_unconfigured():
    """
    When GEMINI_API_KEY is missing, AIService transparently delegates to deterministic fallback.
    """
    ai_service = AIService()
    skills = await ai_service.extract_skills(
        job_title="Full Stack Engineer",
        job_description="Seeking proficiency in Python, FastAPI, React, and SQL database design.",
    )
    assert len(skills) > 0
    assert "Python" in skills
    assert "FastAPI" in skills
    assert "React" in skills
