"""
AI Service — Interface and Test Double for skill extraction and matching.
Phase 3 uses a clearly identified test double (MockAIService).
Full Google Gemini AI integration (via google-genai) is implemented in Phase 5.
"""
import logging
import re
from typing import Any, Dict, List, Optional, Protocol

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.models.skill_finding import SkillStatus

logger = logging.getLogger("skillsync.services.ai")

# Well-known technical keywords for deterministic test double matching
KNOWN_SKILLS = [
    ("Python", "Programming Languages"),
    ("FastAPI", "Web Frameworks"),
    ("SQLAlchemy", "ORM & Database"),
    ("SQL", "Database"),
    ("PostgreSQL", "Database"),
    ("SQLite", "Database"),
    ("Docker", "DevOps & Containers"),
    ("React", "Frontend Development"),
    ("JavaScript", "Programming Languages"),
    ("TypeScript", "Programming Languages"),
    ("REST API", "API Design"),
    ("AsyncIO", "Asynchronous Programming"),
    ("pytest", "Testing & QA"),
    ("Testing", "Testing & QA"),
    ("Git", "Version Control"),
    ("CI/CD", "DevOps"),
    ("Data Modeling", "Database Design"),
    ("Kubernetes", "DevOps & Containers"),
    ("GraphQL", "API Design"),
    ("AWS", "Cloud Infrastructure"),
    ("Redis", "Caching & Queues"),
]


class AIServiceInterface(Protocol):
    """Interface for AI skill extraction and repo assessment."""
    async def extract_skills(self, job_title: str, job_description: str) -> List[str]:
        """Extract key technical skills and requirements from job text."""
        ...

    async def assess_skills(
        self,
        extracted_skills: List[str],
        repo_evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compare extracted skills against repository evidence and generate findings."""
        ...

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
        """Generate structured learning roadmap plan for a skill gap."""
        ...



class MockAIService:
    """
    [TEST DOUBLE — Phase 3]
    Deterministic skill extraction and code evidence matcher.
    Produces realistic skill findings, confidence scores, and line citations
    without calling external LLM APIs.
    """

    def __init__(self, simulate_timeout: bool = False, simulate_unreachable: bool = False):
        self.simulate_timeout = simulate_timeout
        self.simulate_unreachable = simulate_unreachable

    async def extract_skills(self, job_title: str, job_description: str) -> List[str]:
        """Extract skills using regex keyword matching and role heuristics."""
        logger.info(f"[TEST DOUBLE] Extracting skills for job title '{job_title}'")

        if self.simulate_timeout:
            raise ServiceUnavailableError("Gemini AI API", "Mock AI service timeout simulated.")
        if self.simulate_unreachable:
            raise ServiceUnavailableError("Gemini AI API", "Mock AI service connection refused.")

        combined_text = f"{job_title} {job_description}".lower()
        matched_skills: List[str] = []

        for skill_name, _ in KNOWN_SKILLS:
            pattern = r"\b" + re.escape(skill_name.lower()) + r"\b"
            if re.search(pattern, combined_text):
                matched_skills.append(skill_name)

        # Fallback default skills if no known keywords appeared
        if not matched_skills:
            matched_skills = ["Python", "REST API", "Database Design", "Git", "Testing"]

        # Ensure uniqueness while preserving order
        unique_skills = list(dict.fromkeys(matched_skills))
        return unique_skills

    async def assess_skills(
        self,
        extracted_skills: List[str],
        repo_evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluate extracted skills against the files and content in repo_evidence.
        Performs deterministic keyword and pattern matching on actual file content.
        Returns overall score, summary, and structured skill findings with citations.
        """
        logger.info(f"[TEST DOUBLE] Assessing {len(extracted_skills)} skills against repo evidence")

        if self.simulate_timeout:
            raise ServiceUnavailableError("Gemini AI API", "Mock AI service timeout simulated.")

        repo_files = repo_evidence.get("files", [])
        commit_sha = repo_evidence.get("commit_sha", "a1b2c3d4e5f678901234567890abcdef12345678")

        # Extended skill->keyword search patterns for content-based detection
        SKILL_PATTERNS: dict = {
            "Python": ["import ", "def ", ".py", "python", "pip", "virtualenv", "flask", "django"],
            "FastAPI": ["fastapi", "from fastapi", "APIRouter", "uvicorn"],
            "SQLAlchemy": ["sqlalchemy", "from sqlalchemy", "mapped_column", "declarative", "orm"],
            "SQL": ["select ", "insert into", "create table", ".sql", "query", "database"],
            "PostgreSQL": ["postgresql", "psycopg", "pg_", "asyncpg", "postgres"],
            "SQLite": ["sqlite", "aiosqlite", ".db"],
            "Docker": ["dockerfile", "docker-compose", "FROM ", "EXPOSE ", "docker build"],
            "React": ["import react", "from 'react'", "usestate", "useeffect", "jsx", "tsx"],
            "JavaScript": [".js", ".jsx", "const ", "let ", "async function", "import {"],
            "TypeScript": [".ts", ".tsx", "interface ", ": string", ": number", "typescript"],
            "REST API": ["@router", "@app.get", "@app.post", "apiRouter", "fetch(", "axios"],
            "AsyncIO": ["async def", "await ", "asyncio", "async_session"],
            "pytest": ["import pytest", "def test_", "@pytest.mark", "pytest.fixture"],
            "Testing": ["def test_", "test_", "assert ", "unittest", "testcase"],
            "Git": [".gitignore", ".git", "git clone", "git commit"],
            "CI/CD": [".github/workflows", "github-actions", "ci.yml", "pipeline", "jenkins"],
            "Data Modeling": ["class.*base", "mapped_column", "column(", "foreignkey", "relationship"],
            "Kubernetes": ["kubernetes", "kubectl", "k8s", "deployment.yaml", "helm"],
            "GraphQL": ["graphql", "gql", "schema", "resolver", "mutation"],
            "AWS": ["boto3", "aws-sdk", "s3", "lambda", "cloudformation"],
            "Redis": ["redis", "aioredis", "cache", "celery"],
        }

        # Map each skill to evidence from repo_files
        findings: List[Dict[str, Any]] = []
        demonstrated_count = 0

        skill_category_map = {name: cat for name, cat in KNOWN_SKILLS}

        for skill in extracted_skills:
            category = skill_category_map.get(skill, "General Technical")
            matching_files = []

            # Search patterns for this skill
            search_terms = SKILL_PATTERNS.get(skill, [skill.lower()])
            search_terms_lower = [t.lower() for t in search_terms]

            for f in repo_files:
                hints = [h.lower() for h in f.get("skills_hint", [])]
                path = f.get("path", "").lower()
                snippet = f.get("snippet", "").lower()
                language = f.get("language", "").lower()

                # Check hints, path, and snippet + extended patterns
                found = (
                    skill.lower() in hints
                    or any(t in path for t in search_terms_lower)
                    or any(t in snippet for t in search_terms_lower)
                    or skill.lower() in language
                )
                if found:
                    matching_files.append(f)

            if matching_files:
                # Skill is demonstrated with code evidence
                demonstrated_count += 1
                citations = []
                for idx, mf in enumerate(matching_files[:2]):
                    citations.append({
                        "file_path": mf["path"],
                        "start_line": 1 + (idx * 5),
                        "end_line": 15 + (idx * 5),
                        "commit_sha": commit_sha,
                        "code_snippet": mf.get("snippet", "").strip(),
                        "context_explanation": f"Implementation of {skill} demonstrated in {mf['path']}.",
                    })

                # FIXED: append outside the inner loop so each skill produces exactly one finding
                findings.append({
                    "skill_name": skill,
                    "category": category,
                    "status": SkillStatus.DEMONSTRATED.value,
                    "confidence_score": 0.92,
                    "rationale": f"Strong repository evidence found for {skill} across {len(matching_files)} source files.",
                    "limitations": "Evidence demonstrates core usage; advanced production telemetry or security hardening was not observed.",
                    "recommended_next_steps": f"Deepen {skill} competency by implementing edge-case unit tests and configuration profiles.",
                    "evidence_citations": citations,
                })
            else:
                # Skill is partially demonstrated or not found
                if skill in ["Docker", "Kubernetes", "AWS"]:
                    findings.append({
                        "skill_name": skill,
                        "category": category,
                        "status": SkillStatus.NOT_FOUND.value,
                        "confidence_score": 0.15,
                        "rationale": f"No configuration or source files directly implementing {skill} were located in the repository.",
                        "limitations": "Repository does not contain files for this specific infrastructure requirement.",
                        "recommended_next_steps": f"Create a deployment or containerization configuration (e.g. Dockerfile) for {skill}.",
                        "evidence_citations": [],
                    })
                else:
                    findings.append({
                        "skill_name": skill,
                        "category": category,
                        "status": SkillStatus.PARTIALLY_DEMONSTRATED.value,
                        "confidence_score": 0.55,
                        "rationale": f"Indirect references or related concepts for {skill} found, but lacked dedicated test or feature files.",
                        "limitations": "Referenced in documentation or dependencies without extensive functional implementations.",
                        "recommended_next_steps": f"Implement a dedicated module with test coverage demonstrating hands-on {skill} mastery.",
                        "evidence_citations": [],
                    })

        from app.services.scoring_engine import ScoringEngine
        overall_score, breakdown = ScoringEngine.calculate_score(findings)
        total_skills = len(extracted_skills)

        skill_gaps = [f["skill_name"] for f in findings if f["status"] != SkillStatus.DEMONSTRATED.value]
        recommendations = [
            f"Build a dedicated project module to demonstrate {gap}."
            for gap in skill_gaps[:3]
        ] or ["Continue maintaining repository code quality and unit test coverage."]

        summary = (
            f"Assessment completed against {total_skills} required skills. "
            f"Demonstrated {breakdown['demonstrated']}/{total_skills} skills with verifiable code evidence "
            f"({breakdown['partial']} partially demonstrated). Overall competency match: {overall_score}%."
        )

        from app.services.evidence_verifier import EvidenceVerifier

        raw_result = {
            "overall_score": overall_score,
            "summary": summary,
            "findings": findings,
            "skill_gaps": skill_gaps,
            "prioritized_learning_recommendations": recommendations,
            "commit_sha": commit_sha,
        }

        return EvidenceVerifier.verify_and_sanitize_assessment_output(raw_result, repo_evidence)

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
        Deterministic, evidence-backed learning plan generator for test doubles and fallback.
        Produces complete structured output adhering to AILearningPlanOutput.
        """
        logger.info(f"[TEST DOUBLE] Generating learning plan for '{skill_name}' ({current_classification})")
        if self.simulate_timeout:
            raise ServiceUnavailableError("Gemini AI API", "Mock AI service timeout simulated.")
        if self.simulate_unreachable:
            raise ServiceUnavailableError("Gemini AI API", "Mock AI service connection refused.")

        skill_lower = skill_name.lower()
        scope_note = (
            "Notice: Absence of evidence in the repository reflects current repository scope and "
            "does not indicate that the candidate lacks theoretical knowledge or ability in other environments."
        )

        if "fastapi" in skill_lower:
            plan_dict = {
                "title": "FastAPI Async Routing & Schema Architecture",
                "overview": f"Develop production-ready asynchronous endpoints with Pydantic schemas and dependency injection in {repo_name}. {scope_note}",
                "objective": "Build and verify high-performance asynchronous REST API endpoints with automated validation.",
                "concept_explanation": "FastAPI leverages Python type hints, Pydantic data validation, and Starlette routing to provide high-throughput async APIs.",
                "prerequisites": ["Python 3.10+", "Basic async/await concepts", "HTTP protocol fundamentals"],
                "difficulty_level": difficulty_level,
                "estimated_hours": 4.0,
                "current_classification": current_classification,
                "existing_evidence_summary": existing_evidence_summary,
                "missing_evidence_summary": missing_evidence_summary,
                "repo_improvement_recommendation": f"Implement app/api/ router modules and integration tests in {repo_name}.",
                "verified_resources": sanitize_verified_resources([], "fastapi"),
                "steps": [
                    {
                        "step_number": 1,
                        "title": "Pydantic Request & Response Schemas",
                        "instruction": "Define strict Pydantic models with Field validation, type constraints, and schema examples.",
                        "code_example": "from pydantic import BaseModel, Field\n\nclass ResourceCreate(BaseModel):\n    name: str = Field(..., min_length=2)\n    active: bool = True",
                        "expected_artifact": "app/schemas/resource.py",
                        "acceptance_criteria": "Pydantic models reject invalid inputs with HTTP 422 and serialize valid payloads.",
                        "exercise": "Write a schema validating user inputs with email and positive integer fields.",
                        "verification_rubric": "Code contains BaseModel subclasses, Field constraints, and type annotations.",
                    },
                    {
                        "step_number": 2,
                        "title": "Asynchronous Router with Dependency Injection",
                        "instruction": "Implement an APIRouter with async endpoint functions leveraging Depends() for session/service lifecycle.",
                        "code_example": "from fastapi import APIRouter, Depends\nrouter = APIRouter()\n\n@router.get('/items')\nasync def list_items(db=Depends(get_db)):\n    return await db.fetch_all()",
                        "expected_artifact": "app/api/routes/resource.py",
                        "acceptance_criteria": "Endpoints return correct HTTP status codes (200, 201, 404) and operate asynchronously.",
                        "exercise": "Create an async CRUD router with at least one GET and one POST endpoint.",
                        "verification_rubric": "APIRouter instance, async def handlers, and Depends injection present.",
                    },
                    {
                        "step_number": 3,
                        "title": "Integration Testing with AsyncClient",
                        "instruction": "Write comprehensive integration tests utilizing httpx.AsyncClient covering positive and negative flows.",
                        "code_example": "@pytest.mark.asyncio\nasync def test_endpoint(client: AsyncClient):\n    res = await client.post('/api/items', json={'name': 'Valid'})\n    assert res.status_code == 201",
                        "expected_artifact": "tests/test_api_endpoints.py",
                        "acceptance_criteria": "Tests execute asynchronously and assert status codes, response shapes, and validation errors.",
                        "exercise": "Add unit and integration tests verifying both valid payload and malformed payload behavior.",
                        "verification_rubric": "Test suite with pytest-asyncio and httpx.AsyncClient passing cleanly.",
                    },
                ],
            }
        elif "docker" in skill_lower:
            plan_dict = {
                "title": "Production Containerization with Multi-Stage Builds",
                "overview": f"Create hardened Docker containers and Docker Compose environments for {repo_name}. {scope_note}",
                "objective": "Build secure, lightweight container images using multi-stage builds and compose configurations.",
                "concept_explanation": "Containers bundle code with isolated system dependencies. Multi-stage builds dramatically shrink final images by excluding build tools.",
                "prerequisites": ["Linux command line basics", "Environment variables", "Container basics"],
                "difficulty_level": difficulty_level,
                "estimated_hours": 3.0,
                "current_classification": current_classification,
                "existing_evidence_summary": existing_evidence_summary,
                "missing_evidence_summary": missing_evidence_summary,
                "repo_improvement_recommendation": f"Add a production Dockerfile and docker-compose.yml to {repo_name}.",
                "verified_resources": sanitize_verified_resources([], "docker"),
                "steps": [
                    {
                        "step_number": 1,
                        "title": "Multi-Stage Dockerfile Implementation",
                        "instruction": "Write a multi-stage Dockerfile separating dependencies compilation from the final minimal runtime image.",
                        "code_example": "FROM python:3.11-slim AS builder\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\n\nFROM python:3.11-slim\nWORKDIR /app\nCOPY --from=builder /usr/local /usr/local\nCOPY . .\nUSER nobody\nCMD [\"python\", \"-m\", \"app.main\"]",
                        "expected_artifact": "Dockerfile",
                        "acceptance_criteria": "Image builds cleanly, executes as non-root user, and excludes development dependencies.",
                        "exercise": "Write a Dockerfile using python:3.11-slim with builder and runtime stages.",
                        "verification_rubric": "Presence of multi-stage FROM directives, non-root user creation, and proper WORKDIR.",
                    },
                    {
                        "step_number": 2,
                        "title": "Local Multi-Service Orchestration",
                        "instruction": "Configure docker-compose.yml with environment variable passing, healthchecks, and volume mappings.",
                        "code_example": "version: '3.8'\nservices:\n  app:\n    build: .\n    ports:\n      - '8000:8000'\n    healthcheck:\n      test: ['CMD', 'curl', '-f', 'http://localhost:8000/api/health']\n      interval: 10s",
                        "expected_artifact": "docker-compose.yml",
                        "acceptance_criteria": "Services declare healthchecks, port bindings, and environment variables.",
                        "exercise": "Draft docker-compose.yml connecting application service and dependencies.",
                        "verification_rubric": "Valid compose syntax with service definitions and healthcheck commands.",
                    },
                    {
                        "step_number": 3,
                        "title": "Container Build & Verification Workflow",
                        "instruction": "Add a CI test step or automated script validating that the container builds and runs tests.",
                        "code_example": "docker build -t app:test .\ndocker run --rm app:test pytest",
                        "expected_artifact": ".github/workflows/container.yml or scripts/build.sh",
                        "acceptance_criteria": "Automated script verifies container exit code and test suite execution inside container.",
                        "exercise": "Write a verification shell script or workflow testing container health.",
                        "verification_rubric": "Script invoking container build and verification check.",
                    },
                ],
            }
        elif "kubernetes" in skill_lower:
            plan_dict = {
                "title": "Kubernetes Declarative Workload Architecture",
                "overview": f"Configure declarative Kubernetes Deployments, Services, and ConfigMaps for {repo_name}. {scope_note}",
                "objective": "Deploy and configure scalable containerized workloads using Kubernetes manifests.",
                "concept_explanation": "Kubernetes declarative manifests describe desired state for pods, replication, resource limits, and service discovery.",
                "prerequisites": ["Docker containerization", "YAML syntax", "Networking fundamentals"],
                "difficulty_level": difficulty_level,
                "estimated_hours": 3.5,
                "current_classification": current_classification,
                "existing_evidence_summary": existing_evidence_summary,
                "missing_evidence_summary": missing_evidence_summary,
                "repo_improvement_recommendation": f"Add deployment/k8s manifests with resource limits and probes to {repo_name}.",
                "verified_resources": sanitize_verified_resources([], "kubernetes"),
                "steps": [
                    {
                        "step_number": 1,
                        "title": "Declarative Deployment Manifest with Probes",
                        "instruction": "Create deployment.yaml specifying replicas, resource requests/limits, and liveness/readiness probes.",
                        "code_example": "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app-deployment\nspec:\n  replicas: 2\n  template:\n    spec:\n      containers:\n      - name: app\n        image: app:latest\n        livenessProbe:\n          httpGet:\n            path: /api/health\n            port: 8000",
                        "expected_artifact": "deploy/k8s/deployment.yaml",
                        "acceptance_criteria": "Manifest defines spec.replicas, container image, and HTTP probes.",
                        "exercise": "Draft deployment YAML with resource constraints and readiness probes.",
                        "verification_rubric": "Valid Kubernetes Deployment schema with container specs and health probes.",
                    },
                    {
                        "step_number": 2,
                        "title": "Service & ConfigMap Configuration",
                        "instruction": "Define service.yaml (ClusterIP or NodePort) and configmap.yaml for environment decoupled configuration.",
                        "code_example": "apiVersion: v1\nkind: Service\nmetadata:\n  name: app-service\nspec:\n  type: ClusterIP\n  ports:\n  - port: 80\n    targetPort: 8000\n  selector:\n    app: app-deployment",
                        "expected_artifact": "deploy/k8s/service.yaml",
                        "acceptance_criteria": "Service routes traffic to deployment selector pods across configured ports.",
                        "exercise": "Create Service and ConfigMap manifests routing to the application deployment.",
                        "verification_rubric": "Valid Service manifest with selector matching deployment labels.",
                    },
                    {
                        "step_number": 3,
                        "title": "Kubeval Manifest Validation",
                        "instruction": "Add validation testing to verify YAML syntax and Kubernetes API compliance.",
                        "code_example": "kubectl apply --dry-run=client -f deploy/k8s/",
                        "expected_artifact": "scripts/validate_k8s.sh",
                        "acceptance_criteria": "Validation script verifies syntax against Kubernetes schema without runtime errors.",
                        "exercise": "Run client-side dry-run validation script against all manifest files.",
                        "verification_rubric": "Executable validation command or script testing YAML manifests.",
                    },
                ],
            }
        elif "test" in skill_lower or "pytest" in skill_lower or "qa" in skill_lower:
            plan_dict = {
                "title": "Automated Unit & Integration Testing Architecture",
                "overview": f"Establish comprehensive automated test coverage with fixtures and boundary assertions in {repo_name}. {scope_note}",
                "objective": "Build a modular pytest harness testing business logic, edge cases, and external integrations.",
                "concept_explanation": "Automated testing protects software systems from regressions. Pytest fixtures provide reusable dependency injection.",
                "prerequisites": ["Python unit test syntax", "Mocking principles"],
                "difficulty_level": difficulty_level,
                "estimated_hours": 3.0,
                "current_classification": current_classification,
                "existing_evidence_summary": existing_evidence_summary,
                "missing_evidence_summary": missing_evidence_summary,
                "repo_improvement_recommendation": f"Add a tests/ directory with conftest.py and boundary tests to {repo_name}.",
                "verified_resources": sanitize_verified_resources([], "pytest"),
                "steps": [
                    {
                        "step_number": 1,
                        "title": "Pytest Fixture Harness & Conftest",
                        "instruction": "Configure conftest.py with isolated fixtures, mock client instances, and test doubles.",
                        "code_example": "import pytest\nfrom httpx import AsyncClient, ASGITransport\n\n@pytest.fixture\nasync def client():\n    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:\n        yield ac",
                        "expected_artifact": "tests/conftest.py",
                        "acceptance_criteria": "Fixtures provide clean setup/teardown encapsulation without leaking state across tests.",
                        "exercise": "Create conftest.py defining at least one test client or database session fixture.",
                        "verification_rubric": "Presence of pytest.fixture decorators and yield/teardown mechanics.",
                    },
                    {
                        "step_number": 2,
                        "title": "Boundary & Edge Case Unit Assertions",
                        "instruction": "Implement unit tests asserting edge conditions: null values, empty payloads, and exception handling.",
                        "code_example": "def test_boundary_handling():\n    with pytest.raises(ValueError):\n        process_input(None)",
                        "expected_artifact": "tests/test_units.py",
                        "acceptance_criteria": "Tests verify that exceptions are raised for invalid boundaries and valid inputs pass.",
                        "exercise": "Write tests asserting behavior on empty inputs and invalid boundaries.",
                        "verification_rubric": "Use of pytest.raises and explicit boundary assertions.",
                    },
                    {
                        "step_number": 3,
                        "title": "Coverage Enforcement & CI Execution",
                        "instruction": "Configure pytest.ini or pyproject.toml enforcing minimum branch coverage thresholds.",
                        "code_example": "[tool.pytest.ini_options]\naddopts = \"--cov=app --cov-report=term-missing --cov-fail-under=80\"\nasyncio_mode = \"auto\"",
                        "expected_artifact": "pytest.ini or pyproject.toml",
                        "acceptance_criteria": "Test command executes all tests cleanly and outputs code coverage percentage.",
                        "exercise": "Set up pytest configuration with asyncio mode and coverage options.",
                        "verification_rubric": "Presence of pytest configuration file with coverage parameters.",
                    },
                ],
            }
        else:
            plan_dict = {
                "title": f"{skill_name} Verifiable Implementation Architecture",
                "overview": f"Implement structured, evidence-backed code artifacts for {skill_name} in {repo_name}. {scope_note}",
                "objective": f"Demonstrate hands-on competency in {skill_name} to satisfy requirements for {job_title}.",
                "concept_explanation": f"{skill_name} is a key requirement. Developing dedicated modules with automated tests provides concrete proof of ability.",
                "prerequisites": ["Basic software engineering fundamentals", "Git workflow"],
                "difficulty_level": difficulty_level,
                "estimated_hours": 3.0,
                "current_classification": current_classification,
                "existing_evidence_summary": existing_evidence_summary,
                "missing_evidence_summary": missing_evidence_summary,
                "repo_improvement_recommendation": f"Add a dedicated module and unit tests for {skill_name} to {repo_name}.",
                "verified_resources": sanitize_verified_resources([], skill_name),
                "steps": [
                    {
                        "step_number": 1,
                        "title": f"Design Core Module & Data Models for {skill_name}",
                        "instruction": f"Implement core classes, data structures, and interfaces representing {skill_name}.",
                        "code_example": f"# Core domain service for {skill_name}\nclass DomainService:\n    def process(self, data: dict) -> dict:\n        return {{'status': 'processed', 'data': data}}",
                        "expected_artifact": f"app/services/{skill_name.lower().replace(' ', '_')}.py",
                        "acceptance_criteria": "Module defines clear classes with typed methods and docstrings.",
                        "exercise": f"Create a dedicated service module implementing core {skill_name} behavior.",
                        "verification_rubric": "Modular design, type annotations, and absence of syntax errors.",
                    },
                    {
                        "step_number": 2,
                        "title": f"Integrate Error Handling & Logging for {skill_name}",
                        "instruction": "Implement robust exception handling, logging, and edge case guards around the core logic.",
                        "code_example": "import logging\nlogger = logging.getLogger(__name__)\n\ndef safe_execute(payload: dict):\n    if not payload:\n        logger.warning('Empty payload received')\n        raise ValueError('Payload required')\n    return True",
                        "expected_artifact": f"app/services/{skill_name.lower().replace(' ', '_')}.py",
                        "acceptance_criteria": "Exceptions are caught or propagated cleanly with descriptive error messages.",
                        "exercise": "Add input validation and logging to the service module.",
                        "verification_rubric": "Presence of try/except or validation checks and logging calls.",
                    },
                    {
                        "step_number": 3,
                        "title": f"Write Comprehensive Automated Tests for {skill_name}",
                        "instruction": "Write automated unit tests verifying standard flows and error conditions.",
                        "code_example": f"def test_{skill_name.lower().replace(' ', '_')}_execution():\n    service = DomainService()\n    res = service.process({{'key': 'val'}})\n    assert res['status'] == 'processed'",
                        "expected_artifact": f"tests/test_{skill_name.lower().replace(' ', '_')}.py",
                        "acceptance_criteria": "Test functions assert expected return values and exception triggers.",
                        "exercise": "Write at least two unit tests validating happy and error paths.",
                        "verification_rubric": "Passing pytest assertions verifying module behavior.",
                    },
                ],
            }

        # Deterministic schema validation
        from app.schemas.gap_solver import AILearningPlanOutput
        validated = AILearningPlanOutput.model_validate(plan_dict)
        return validated.model_dump()


# Canonical verified documentation registry — strictly verified canonical sources only
VERIFIED_DOCUMENTATION_MAP: Dict[str, List[Dict[str, str]]] = {
    "default": [
        {"title": "Official Python 3 Documentation", "url": "https://docs.python.org/3/"},
    ],
    "python": [
        {"title": "Official Python 3 Documentation", "url": "https://docs.python.org/3/"},
        {"title": "Python Standard Library Reference", "url": "https://docs.python.org/3/library/"},
    ],
    "fastapi": [
        {"title": "FastAPI Official Documentation", "url": "https://fastapi.tiangolo.com/"},
        {"title": "FastAPI Tutorial - User Guide", "url": "https://fastapi.tiangolo.com/tutorial/"},
    ],
    "docker": [
        {"title": "Docker Official Documentation", "url": "https://docs.docker.com/"},
        {"title": "Docker Compose Reference", "url": "https://docs.docker.com/compose/"},
    ],
    "kubernetes": [
        {"title": "Kubernetes Official Documentation", "url": "https://kubernetes.io/docs/"},
        {"title": "Kubernetes Concepts Reference", "url": "https://kubernetes.io/docs/concepts/"},
    ],
    "testing": [
        {"title": "Pytest Official Documentation", "url": "https://docs.pytest.org/en/stable/"},
    ],
    "pytest": [
        {"title": "Pytest Official Documentation", "url": "https://docs.pytest.org/en/stable/"},
    ],
    "sqlalchemy": [
        {"title": "SQLAlchemy 2.0 Documentation", "url": "https://docs.sqlalchemy.org/en/20/"},
    ],
    "react": [
        {"title": "React Official Documentation", "url": "https://react.dev/"},
        {"title": "React Quick Start Guide", "url": "https://react.dev/learn"},
    ],
    "javascript": [
        {"title": "MDN JavaScript Guide", "url": "https://developer.mozilla.org/en-US/docs/Web/JavaScript"},
    ],
    "typescript": [
        {"title": "TypeScript Official Handbook", "url": "https://www.typescriptlang.org/docs/"},
    ],
    "git": [
        {"title": "Official Git Documentation", "url": "https://git-scm.com/doc"},
    ],
    "postgresql": [
        {"title": "PostgreSQL Documentation", "url": "https://www.postgresql.org/docs/"},
    ],
    "sqlite": [
        {"title": "SQLite Documentation", "url": "https://www.sqlite.org/docs.html"},
    ],
    "redis": [
        {"title": "Redis Official Documentation", "url": "https://redis.io/docs/"},
    ],
}

ALLOWED_DOC_DOMAINS = (
    "docs.python.org",
    "fastapi.tiangolo.com",
    "docs.docker.com",
    "kubernetes.io",
    "docs.pytest.org",
    "docs.sqlalchemy.org",
    "react.dev",
    "developer.mozilla.org",
    "www.typescriptlang.org",
    "git-scm.com",
    "www.postgresql.org",
    "www.sqlite.org",
    "redis.io",
)


def sanitize_verified_resources(resources_or_plan: Any, skill_name: str) -> List[Dict[str, str]]:
    """
    Strictly verifies that resource URLs belong to official authoritative documentation domains.
    Discards any unverified, hallucinated, or external course links.
    Falls back to canonical registry if none remain.
    """
    raw_list = []
    if isinstance(resources_or_plan, dict):
        raw_list = resources_or_plan.get("verified_resources", [])
    elif isinstance(resources_or_plan, list):
        raw_list = resources_or_plan

    verified = []
    for item in raw_list:
        if isinstance(item, dict):
            url = item.get("url", "").strip()
            title = item.get("title", "").strip()
        elif hasattr(item, "url") and hasattr(item, "title"):
            url = getattr(item, "url", "").strip()
            title = getattr(item, "title", "").strip()
        else:
            continue

        if not url:
            continue

        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.netloc.lower()
            if any(host == d or host.endswith("." + d) for d in ALLOWED_DOC_DOMAINS):
                verified.append({"title": title or "Official Documentation", "url": url})
        except Exception:
            continue

    if not verified:
        # Fallback to verified canonical registry
        skill_lower = skill_name.lower()
        key = "default"
        for k in VERIFIED_DOCUMENTATION_MAP:
            if k in skill_lower:
                key = k
                break
        verified = VERIFIED_DOCUMENTATION_MAP.get(key, VERIFIED_DOCUMENTATION_MAP["default"])

    return verified


class AIService:
    """
    Production AI Service coordinating with GeminiEngine.
    Falls back to MockAIService if GEMINI_API_KEY is not configured or in test double mode.
    """

    def __init__(self, engine: Optional[Any] = None):
        from app.services.gemini_engine import GeminiEngine
        self.engine = engine or GeminiEngine()
        self.mock_fallback = MockAIService()

    async def extract_skills(self, job_title: str, job_description: str) -> List[str]:
        if not settings.gemini_api_key or settings.use_test_doubles:
            logger.info("Using deterministic skill extraction (GEMINI_API_KEY unset or test doubles active).")
            return await self.mock_fallback.extract_skills(job_title, job_description)
        return await self.engine.extract_skills(job_title, job_description)

    async def assess_skills(
        self,
        extracted_skills: List[str],
        repo_evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not settings.gemini_api_key or settings.use_test_doubles:
            logger.info("Using deterministic assessment engine (GEMINI_API_KEY unset or test doubles active).")
            return await self.mock_fallback.assess_skills(extracted_skills, repo_evidence)
        return await self.engine.assess_skills(extracted_skills, repo_evidence)

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
        if not settings.gemini_api_key or settings.use_test_doubles:
            logger.info("Using deterministic learning plan generator (test doubles active).")
            return await self.mock_fallback.generate_learning_plan(
                skill_name=skill_name,
                category=category,
                job_title=job_title,
                job_requirement_text=job_requirement_text,
                current_classification=current_classification,
                existing_evidence_summary=existing_evidence_summary,
                missing_evidence_summary=missing_evidence_summary,
                repo_name=repo_name,
                difficulty_level=difficulty_level,
                focus_areas=focus_areas,
            )
        try:
            plan_dict = await self.engine.generate_learning_plan(
                skill_name=skill_name,
                category=category,
                job_title=job_title,
                job_requirement_text=job_requirement_text,
                current_classification=current_classification,
                existing_evidence_summary=existing_evidence_summary,
                missing_evidence_summary=missing_evidence_summary,
                repo_name=repo_name,
                difficulty_level=difficulty_level,
                focus_areas=focus_areas,
            )
            # Ensure resources are strictly canonical verified URLs
            plan_dict["verified_resources"] = sanitize_verified_resources(
                plan_dict.get("verified_resources", []), skill_name
            )
            from app.schemas.gap_solver import AILearningPlanOutput
            validated = AILearningPlanOutput.model_validate(plan_dict)
            return validated.model_dump()
        except Exception as exc:
            logger.warning(f"Gemini plan generation failed ({exc}); falling back to deterministic roadmap.")
            return await self.mock_fallback.generate_learning_plan(
                skill_name=skill_name,
                category=category,
                job_title=job_title,
                job_requirement_text=job_requirement_text,
                current_classification=current_classification,
                existing_evidence_summary=existing_evidence_summary,
                missing_evidence_summary=missing_evidence_summary,
                repo_name=repo_name,
                difficulty_level=difficulty_level,
                focus_areas=focus_areas,
            )


def get_ai_service() -> AIServiceInterface:
    """Factory to retrieve AI service instance based on configuration."""
    if settings.use_test_doubles or not settings.gemini_api_key:
        return MockAIService()
    return AIService()

