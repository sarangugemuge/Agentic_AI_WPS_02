"""
Gemini AI Engine — Real implementation of skill extraction and repository code evaluation.
Powered by Google Gemini 2.0 Flash (`google-genai` SDK).
Implements structured output enforcement, anti-hallucination guards, and error resilience.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.schemas.ai_schemas import JobSkillExtractionResult, AIAssessmentOutput
from app.services.evidence_verifier import EvidenceVerifier

logger = logging.getLogger("skillsync.services.gemini_engine")


class GeminiEngine:
    """
    Client for Google Gemini 2.0 Flash executing structured skill extraction and code evaluation.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_model or "gemini-2.0-flash"
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        """Instantiate google.genai.Client with API key."""
        if not self.api_key or not self.api_key.strip():
            raise ServiceUnavailableError(
                "Gemini AI API",
                "GEMINI_API_KEY is not configured. Set GEMINI_API_KEY in .env or environment.",
            )
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key.strip())
        return self._client

    async def extract_skills(self, job_title: str, job_description: str) -> List[str]:
        """
        Extract explicit and inferred technical skills from a job description.
        Returns normalized skill names.
        """
        logger.info(f"Extracting skills with Gemini ({self.model}) for '{job_title}'")
        client = self._get_client()

        prompt = f"""You are an expert technical recruiter and software architect analyzing a job posting.
Extract both explicit and strongly-inferred technical competencies, tools, frameworks, and concepts required for this role.
Group them into consistent categories (e.g., Programming Languages, Web Frameworks, Database, DevOps & Cloud, QA & Testing, Architecture).

Job Title: {job_title}
Job Description:
{job_description}
"""

        try:
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=JobSkillExtractionResult,
                    temperature=0.2,
                ),
            )
            raw_text = response.text
            parsed = JobSkillExtractionResult.model_validate_json(raw_text)
            skill_names = [s.name for s in parsed.skills]
            # Ensure unique while preserving order
            return list(dict.fromkeys(skill_names))

        except Exception as exc:
            logger.error(f"Gemini skill extraction failed: {str(exc)}", exc_info=True)
            raise ServiceUnavailableError("Gemini AI API", f"Gemini skill extraction failed: {str(exc)}")

    async def assess_skills(
        self,
        extracted_skills: List[str],
        repo_evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Analyze repository source code against required skills using Gemini.
        Validates output against AIAssessmentOutput and enforces ground-truth citations.
        """
        logger.info(f"Assessing {len(extracted_skills)} skills with Gemini against repository {repo_evidence.get('owner')}/{repo_evidence.get('repo')}")
        client = self._get_client()

        files_context = []
        for f in repo_evidence.get("files", []):
            files_context.append({
                "path": f["path"],
                "language": f["language"],
                "snippet": f.get("snippet", "")[:1500],
            })

        system_instruction = (
            "You are the SkillSync AI Assessment Engine. Your job is to rigorously assess developer skills "
            "based exclusively on verified source code evidence provided from their GitHub repository.\n"
            "STRICT RULES:\n"
            "1. NEVER hallucinate or invent file paths or code. Only cite files that exist in the provided repository files.\n"
            "2. If no file in the repository demonstrates a skill, classify it as 'not_found' or 'partially_demonstrated'.\n"
            "3. If evidence is missing, note that this reflects the repository scope, not necessarily candidate deficiency.\n"
            "4. For each skill, provide an accurate confidence_score (0.0 to 1.0), rationale, limitations, and recommended next steps.\n"
            "5. Provide overall_score (0 to 100), summary, skill_gaps list, and prioritized_learning_recommendations."
        )

        user_content = f"""Assess these required skills:
{json.dumps(extracted_skills, indent=2)}

Repository: {repo_evidence.get('owner')}/{repo_evidence.get('repo')} (Commit: {repo_evidence.get('commit_sha')})
Total files inspected: {len(files_context)}

Repository File Artifacts:
{json.dumps(files_context, indent=2)}
"""

        try:
            response = client.models.generate_content(
                model=self.model,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=AIAssessmentOutput,
                    temperature=0.2,
                ),
            )
            raw_text = response.text
            parsed = AIAssessmentOutput.model_validate_json(raw_text)

            raw_dict = parsed.model_dump()

            # Enforce ground-truth verification on citations
            verified_dict = EvidenceVerifier.verify_and_sanitize_assessment_output(
                assessment_data=raw_dict,
                repo_evidence=repo_evidence,
            )

            # Enforce deterministic mathematical score from verified findings
            from app.services.scoring_engine import ScoringEngine
            det_score, breakdown = ScoringEngine.calculate_score(verified_dict.get("findings", []))
            verified_dict["overall_score"] = det_score

            return verified_dict

        except Exception as exc:
            logger.error(f"Gemini skill assessment failed: {str(exc)}", exc_info=True)
            raise ServiceUnavailableError("Gemini AI API", f"Gemini skill assessment failed: {str(exc)}")

    async def generate_learning_plan(
        self,
        skill_name: str,
        category: Optional[str],
        job_title: str,
        job_requirement_text: str,
        current_classification: str,
        existing_evidence_summary: str,
        missing_evidence_summary: str,
        repo_name: str,
        difficulty_level: str = "intermediate",
        focus_areas: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive, actionable learning roadmap plan for a skill gap.
        Uses structured output schema (AILearningPlanOutput) and enforces deterministic validation.
        """
        logger.info(f"Generating learning plan with Gemini ({self.model}) for '{skill_name}' ({current_classification})")
        client = self._get_client()

        system_instruction = (
            "You are the SkillSync Learning Roadmap Architect. Your task is to produce a rigorous, "
            "verifiable learning plan that enables a developer to remediate an identified skill gap "
            "by adding authentic code evidence to their GitHub repository.\n\n"
            "STRICT RULES:\n"
            "1. DISTINGUISH SCOPE: Evidence not being present in the repository ('not_demonstrated') reflects "
            "the scope of the repository, not necessarily a personal candidate deficit. State this clearly.\n"
            "2. VERIFIED RESOURCES ONLY: Never hallucinate courses, certifications, or URLs. Only cite official "
            "canonical documentation (e.g., https://fastapi.tiangolo.com/, https://docs.python.org/3/, https://docs.docker.com/).\n"
            "3. ACTIONABLE CODE EVIDENCE: Every step must produce concrete, testable artifacts in the candidate repository.\n"
            "4. DETERMINISTIC SCHEMA: Output must strictly conform to the provided AILearningPlanOutput schema."
        )

        user_content = f"""Generate a structured learning plan for the following skill gap:
Target Skill: {skill_name}
Category: {category or 'General'}
Job Target Role: {job_title}
Job Requirement: {job_requirement_text}
Current Classification: {current_classification}
Existing Evidence Summary: {existing_evidence_summary}
Missing Evidence Summary: {missing_evidence_summary}
Target Repository: {repo_name}
Target Difficulty: {difficulty_level}
Optional Focus Areas: {json.dumps(focus_areas or [])}
"""

        try:
            from app.schemas.gap_solver import AILearningPlanOutput
            response = client.models.generate_content(
                model=self.model,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=AILearningPlanOutput,
                    temperature=0.2,
                ),
            )
            raw_text = response.text
            parsed = AILearningPlanOutput.model_validate_json(raw_text)
            return parsed.model_dump()
        except Exception as exc:
            logger.error(f"Gemini learning plan generation failed: {str(exc)}", exc_info=True)
            raise ServiceUnavailableError("Gemini AI API", f"Gemini learning plan generation failed: {str(exc)}")

