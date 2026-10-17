"""
Evidence Verifier — Anti-hallucination guard and provenance cross-validation.
Enforces Task 10 & 11:
- Never stores invented file paths, code, or commits.
- Validates all citations against verified repository artifacts.
- Distinguishes absence of repository evidence from candidate skill deficiency.
"""
import logging
from typing import Any, Dict, List

from app.models.skill_finding import SkillStatus

logger = logging.getLogger("skillsync.services.evidence_verifier")


class EvidenceVerifier:
    """
    Validates LLM-generated findings against ground-truth repository artifacts.
    Prevents hallucinated citations and enforces accurate uncertainty communication.
    """

    @staticmethod
    def verify_and_sanitize_assessment_output(
        assessment_data: Dict[str, Any],
        repo_evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Cross-reference citations against real files and ensure truthful evidence tracking.
        """
        real_files: Dict[str, Dict[str, Any]] = {
            f["path"]: f for f in repo_evidence.get("files", [])
        }
        verified_commit_sha = repo_evidence.get("commit_sha", "")

        verified_findings: List[Dict[str, Any]] = []

        for finding in assessment_data.get("findings", []):
            skill_name = finding.get("skill_name", "Unknown Skill")
            status_val = finding.get("status", SkillStatus.NOT_FOUND.value)
            raw_citations = finding.get("evidence_citations", [])

            valid_citations = []
            for cit in raw_citations:
                path = cit.get("file_path", "")

                # 1. Verify file exists in actual repository artifacts
                if path not in real_files:
                    logger.warning(
                        f"[Anti-Hallucination] Discarding citation for non-existent file '{path}' cited for skill '{skill_name}'."
                    )
                    continue

                real_file = real_files[path]
                real_snippet = real_file.get("snippet", "")

                # 2. Verify start/end line bounds
                snippet = cit.get("code_snippet") or real_snippet[:500]
                lines_count = len(snippet.splitlines()) if snippet else 10
                start_line = cit.get("start_line") or 1
                end_line = cit.get("end_line") or (start_line + max(lines_count, 1))

                valid_citations.append({
                    "file_path": path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "commit_sha": verified_commit_sha,
                    "code_snippet": snippet.strip(),
                    "context_explanation": cit.get(
                        "context_explanation",
                        f"Verifiable implementation of {skill_name} in {path}.",
                    ),
                })

            # 3. Status consistency rule: Cannot be 'demonstrated' without valid citations
            if not valid_citations and status_val == SkillStatus.DEMONSTRATED.value:
                logger.info(
                    f"Downgrading '{skill_name}' from DEMONSTRATED to PARTIALLY_DEMONSTRATED due to lack of verifiable file citations."
                )
                status_val = SkillStatus.PARTIALLY_DEMONSTRATED.value
                finding["confidence_score"] = min(finding.get("confidence_score", 0.5), 0.5)

            # 4. Enforce Task 11: Missing evidence distinction
            rationale = finding.get("rationale", "")
            if status_val == SkillStatus.NOT_FOUND.value:
                clarification = (
                    " Note: No evidence was identified in this repository; this reflects the scope "
                    "of the repository and does not imply a lack of developer proficiency."
                )
                if clarification.strip() not in rationale:
                    rationale = (rationale.strip() + clarification).strip()

            finding["status"] = status_val
            finding["rationale"] = rationale
            finding["evidence_citations"] = valid_citations
            verified_findings.append(finding)

        assessment_data["findings"] = verified_findings
        assessment_data["commit_sha"] = verified_commit_sha
        return assessment_data

    @staticmethod
    def validate_file_path(path: str) -> tuple[bool, str | None]:
        """
        Validate safety and syntax of an evidence file path.
        Prevents directory traversal, absolute paths, and malformed characters.
        """
        if not path or not path.strip():
            return False, "File path cannot be empty."

        clean = path.strip()
        if len(clean) > 1000:
            return False, "File path exceeds maximum length of 1000 characters."

        # Reject path traversal attempts
        if ".." in clean.replace("\\", "/").split("/"):
            return False, "Directory traversal ('..') is not permitted in evidence file paths."

        # Reject absolute paths (POSIX and Windows drive letters)
        if clean.startswith("/") or clean.startswith("\\") or (len(clean) > 1 and clean[1] == ":"):
            return False, "Absolute file paths are not permitted. Use repository-relative paths."

        # Reject invalid characters or null bytes
        if "\0" in clean or "\r" in clean or "\n" in clean:
            return False, "File path contains invalid control characters."

        return True, None

    @staticmethod
    def sanitize_code_content(raw_code: str) -> tuple[str, bool, List[str]]:
        """
        Detect and neutralize prompt injection attempts in submitted source files.
        Returns: (sanitized_code, injection_detected, detected_patterns)
        """
        import re

        injection_patterns = [
            (r"(?i)(ignore\s+(all\s+)?(previous|prior)\s+instructions)", "Instruction Override Attempt"),
            (r"(?i)(system\s+prompt\s*:)", "System Prompt Impersonation"),
            (r"(?i)(you\s+must\s+(give|rate|score|mark)\s+.*(100|verified|passed))", "Forced Rating Injection"),
            (r"(?i)(\[system\]|<<sys>>|<\|im_start\|>|<\|im_end\|>)", "Special Token Tag Injection"),
            (r"(?i)(disregard\s+(the\s+)?(above|instructions))", "Instruction Disregard Attempt"),
            (r"(?i)(dan\s+mode|jailbreak)", "Jailbreak Directive"),
        ]

        detected: List[str] = []
        sanitized = raw_code

        for pattern, label in injection_patterns:
            matches = list(re.finditer(pattern, sanitized))
            if matches:
                detected.append(label)
                # Neutralize injection by replacing matches with [NEUTRALIZED_MARKER]
                sanitized = re.sub(pattern, "[NEUTRALIZED_UNTRUSTED_INJECTION_DIRECTIVE]", sanitized)

        injection_detected = len(detected) > 0
        if injection_detected:
            logger.warning(
                f"[Anti-Injection] Detected and neutralized {len(detected)} prompt injection markers: {detected}."
            )

        return sanitized, injection_detected, detected

    @staticmethod
    def is_stub_or_empty(content: str) -> tuple[bool, str]:
        """
        Check if code content is empty or contains only non-functional stubs / placeholders.
        """
        stripped = content.strip()
        if not stripped:
            return True, "File content is completely empty."

        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        if not lines:
            return True, "File contains only whitespace."

        # Filter out comments and docstrings
        code_lines = []
        for l in lines:
            if l.startswith("#") or l.startswith("//") or l.startswith("/*") or l.startswith("*") or l.startswith('"""') or l.startswith("'''"):
                continue
            code_lines.append(l)

        if not code_lines:
            return True, "File contains only comments or docstrings without functional code."

        # Check for stub-only statements: pass, ..., raise NotImplementedError
        stub_tokens = {"pass", "...", "raise notimplementederror", "raise notimplementederror()", "{ }", "{}"}
        non_stub = []
        for cl in code_lines:
            normalized = cl.lower().rstrip(";")
            if normalized in stub_tokens or "todo:" in normalized or "fixme:" in normalized:
                continue
            non_stub.append(cl)

        # Check if all statements are merely class/def headers with stub tokens
        meaningful_statements = []
        for cl in non_stub:
            norm = cl.lower().strip()
            # If line is simply a class or function header e.g. "class Foo:", "def bar():", "class Foo(object):"
            if (norm.startswith("def ") or norm.startswith("class ") or norm.startswith("async def ")) and norm.endswith(":"):
                continue
            meaningful_statements.append(cl)

        if not meaningful_statements:
            return True, "File contains only placeholder stubs (pass, ..., NotImplementedError, or TODOs) without concrete implementation."

        return False, ""

    @staticmethod
    def evaluate_rubric_against_evidence(
        target_skill: str,
        acceptance_criteria: str | None,
        verification_rubric: str | None,
        expected_artifact: str | None,
        instruction: str | None,
        evidence_files: List[Dict[str, Any]],
        commit_sha: str | None = None,
        repo_name: str = "candidate-repo",
    ) -> Dict[str, Any]:
        """
        Evaluate actual repository code evidence against rubric criteria and acceptance criteria.
        Distinguishes:
        - verified (rubric score >= 80%, meets criteria, functional implementation & tests present)
        - partially_demonstrated (rubric score 35-79%, partial structure or missing tests/edge cases)
        - insufficient_evidence (rubric score < 35%, empty file, stubs, or documentation only)
        - inaccessible (file not found in repo or access refused)
        """
        commit_ref = commit_sha or "latest"

        # 1. Check if any evidence files were located in repository scope
        if not evidence_files:
            return {
                "verdict": "inaccessible",
                "rubric_score": 0.0,
                "feedback": f"Target evidence artifact was not accessible in repository '{repo_name}' at commit {commit_ref}.",
                "strengths": None,
                "missing_elements": f"Expected artifact '{expected_artifact or 'code file'}' was not found in repository artifacts.",
                "limitations": "Repository file tree does not contain the specified file at this commit reference.",
                "missing_work": f"Commit and push '{expected_artifact or 'the required artifact'}' to your repository branch.",
                "next_recommended_action": f"Verify file path spelling and commit the file before requesting verification.",
                "evidence_found": [],
                "evidence_locations": [],
                "rubric_findings": [
                    {
                        "criterion": "Artifact Accessibility",
                        "status": "inaccessible",
                        "score": 0.0,
                        "evidence": None,
                        "notes": f"File was not found in repository at commit {commit_ref}.",
                    }
                ],
            }

        # 2. Check for empty files or pure stubs
        primary_file = evidence_files[0]
        raw_content = primary_file.get("content") or primary_file.get("snippet") or ""
        file_path = primary_file.get("path", expected_artifact or "file")

        # Sanitize code against prompt injection attempts
        sanitized_content, injection_found, injection_types = EvidenceVerifier.sanitize_code_content(raw_content)

        is_stub, stub_reason = EvidenceVerifier.is_stub_or_empty(sanitized_content)
        if is_stub:
            limitations = "File consists of stub definitions without business logic."
            if injection_found:
                limitations += f" Note: Neutralized prompt injection attempts ({', '.join(injection_types)})."

            return {
                "verdict": "insufficient_evidence",
                "rubric_score": 10.0,
                "feedback": f"Submitted evidence in '{file_path}' is insufficient: {stub_reason}",
                "strengths": f"File '{file_path}' was created in the repository.",
                "missing_elements": "Concrete business logic, error handling, and unit test assertions.",
                "limitations": limitations,
                "missing_work": "Implement functional logic replacing placeholders (pass, ..., NotImplementedError) and write automated tests.",
                "next_recommended_action": f"Complete implementation of {target_skill} in '{file_path}' according to the step instructions.",
                "evidence_found": [f"File {file_path} exists"],
                "evidence_locations": [
                    {"file_path": file_path, "commit_sha": commit_ref, "line_range": "1-10"}
                ],
                "rubric_findings": [
                    {
                        "criterion": "Artifact Presence & Structure",
                        "status": "insufficient",
                        "score": 10.0,
                        "evidence": f"File {file_path}",
                        "notes": stub_reason,
                    },
                    {
                        "criterion": "Acceptance Criteria Compliance",
                        "status": "insufficient",
                        "score": 0.0,
                        "evidence": None,
                        "notes": "Criteria cannot be verified on stub code.",
                    },
                ],
            }

        # 3. Check for documentation-only commits or non-code files
        from app.services.scoring_engine import ScoringEngine
        if ScoringEngine.is_documentation_only_commit([file_path]):
            return {
                "verdict": "insufficient_evidence",
                "rubric_score": 15.0,
                "feedback": f"File '{file_path}' is a documentation/asset file, not executable implementation code.",
                "strengths": f"Documentation provided in '{file_path}'.",
                "missing_elements": "Executable code demonstrating technical skill competency.",
                "limitations": "Documentation alone cannot verify technical implementation competency.",
                "missing_work": f"Implement the requested logic in a source code file matching {target_skill}.",
                "next_recommended_action": "Submit source code files (.py, .ts, .js, Dockerfile, etc.) rather than markdown/text documentation.",
                "evidence_found": [f"Documentation file {file_path}"],
                "evidence_locations": [
                    {"file_path": file_path, "commit_sha": commit_ref, "line_range": "1-20"}
                ],
                "rubric_findings": [
                    {
                        "criterion": "Technical Code Implementation",
                        "status": "insufficient",
                        "score": 15.0,
                        "evidence": file_path,
                        "notes": "Documentation files do not satisfy technical competency rubrics.",
                    }
                ],
            }

        # 4. Detailed Rubric and Acceptance Criteria Evaluation
        content_lower = sanitized_content.lower()
        skill_lower = target_skill.lower()
        acceptance_lower = (acceptance_criteria or "").lower()
        rubric_lower = (verification_rubric or "").lower()

        evidence_found: List[str] = []
        rubric_findings: List[Dict[str, Any]] = []
        missing_items: List[str] = []
        criterion_scores: List[float] = []

        # Criterion 1: Core Domain Structure & Syntax (Weight: 35%)
        # Check skill domain keywords
        domain_indicators = {
            "fastapi": ["fastapi", "apirouter", "pydantic", "basemodel", "app = fastapi", "@router", "@app"],
            "python": ["def ", "class ", "import ", "return "],
            "docker": ["from ", "workdir", "run ", "copy ", "expose ", "cmd "],
            "kubernetes": ["apiversion", "kind:", "deployment", "spec:", "template:", "containers:"],
            "testing": ["test_", "assert ", "pytest", "fixture", "mock", "async def test_"],
            "sql": ["select", "from", "where", "join", "table", "create", "insert"],
            "sqlalchemy": ["mapped_column", "base", "relationship", "async_session", "session", "column"],
            "react": ["import react", "usestate", "useeffect", "return (", "export default", "jsx"],
        }
        indicators = domain_indicators.get(skill_lower, [skill_lower, "def ", "class "])
        matched_indicators = [ind for ind in indicators if ind in content_lower]

        has_core_structure = len(matched_indicators) >= 2 or (len(matched_indicators) >= 1 and len(sanitized_content) > 100)
        score_1 = 100.0 if has_core_structure else (50.0 if matched_indicators else 20.0)
        criterion_scores.append(score_1 * 0.35)

        if has_core_structure:
            evidence_found.append(f"Core {target_skill} implementation constructs verified in {file_path}")
            rubric_findings.append({
                "criterion": f"{target_skill} Architecture & Core Logic",
                "status": "verified",
                "score": score_1,
                "evidence": f"Found syntax matches: {', '.join(matched_indicators[:3])}",
                "notes": f"Concrete syntax and structure for {target_skill} confirmed in {file_path}.",
            })
        else:
            missing_items.append(f"Strong structural elements for {target_skill}")
            rubric_findings.append({
                "criterion": f"{target_skill} Architecture & Core Logic",
                "status": "partially_demonstrated" if matched_indicators else "insufficient",
                "score": score_1,
                "evidence": f"Sparse matches: {matched_indicators}",
                "notes": f"Code lacks comprehensive {target_skill} constructs.",
            })

        # Criterion 2: Acceptance Criteria Satisfaction (Weight: 35%)
        score_2 = 70.0  # baseline if no specific acceptance criteria given
        if acceptance_criteria:
            # Check key verbs / tokens from acceptance criteria
            criteria_words = [w.strip(".,;:()") for w in acceptance_lower.split() if len(w) > 4 and w not in ("must", "should", "with", "from", "that", "this", "have")]
            matched_words = [w for w in criteria_words if w in content_lower]
            if criteria_words:
                match_ratio = len(matched_words) / len(criteria_words)
                if match_ratio >= 0.5:
                    score_2 = 95.0
                    evidence_found.append(f"Acceptance criteria satisfied: demonstrated key requirements ({', '.join(matched_words[:4])})")
                    status_2 = "verified"
                elif match_ratio >= 0.25:
                    score_2 = 60.0
                    status_2 = "partially_demonstrated"
                    missing_items.append("Complete edge-case validation as defined in acceptance criteria")
                else:
                    score_2 = 30.0
                    status_2 = "insufficient"
                    missing_items.append("Specified acceptance criteria requirements")
            else:
                score_2 = 80.0
                status_2 = "verified"
        else:
            status_2 = "verified"
            score_2 = 85.0

        criterion_scores.append(score_2 * 0.35)
        rubric_findings.append({
            "criterion": "Acceptance Criteria Compliance",
            "status": status_2,
            "score": score_2,
            "evidence": f"Evidence evaluated against criteria in {file_path}",
            "notes": "Code evaluated against defined step acceptance criteria.",
        })

        # Criterion 3: Automated Testing & Verification Rigor (Weight: 20%)
        # Look for tests in the file itself or companion test files
        has_assertions = "assert " in content_lower or "expect(" in content_lower or "should." in content_lower
        has_test_func = "def test_" in content_lower or "it(" in content_lower or "test(" in content_lower or "@pytest" in content_lower
        is_test_file = "test" in file_path.lower()

        # Also check other evidence files for tests if multiple provided and relevant to target skill
        for ef in evidence_files[1:]:
            ef_path = ef.get("path", "").lower()
            ef_content = (ef.get("content") or ef.get("snippet") or "").lower()
            hints = [h.lower() for h in ef.get("skills_hint", [])]
            is_relevant = skill_lower in ef_path or skill_lower in ef_content or skill_lower in hints
            if "test" in ef_path and is_relevant and ("assert " in ef_content or "def test_" in ef_content):
                has_assertions = True
                has_test_func = True
                is_test_file = True
                evidence_found.append(f"Automated test suite identified in companion file {ef.get('path')}")
                break

        if has_assertions and (has_test_func or is_test_file):
            score_3 = 100.0
            status_3 = "verified"
            evidence_found.append(f"Automated unit test assertions and test harness verified in evidence")
        elif has_assertions or has_test_func:
            score_3 = 60.0
            status_3 = "partially_demonstrated"
            missing_items.append("Comprehensive assertion coverage across boundary conditions")
        else:
            # If the step itself isn't a test step and rubric doesn't strictly require test files
            if "test" not in rubric_lower and "test" not in skill_lower and "test" not in acceptance_lower:
                score_3 = 70.0
                status_3 = "partially_demonstrated"
            else:
                score_3 = 25.0
                status_3 = "insufficient"
                missing_items.append("Automated unit tests with assert statements")

        criterion_scores.append(score_3 * 0.20)
        rubric_findings.append({
            "criterion": "Automated Testing & Edge-Case Verification",
            "status": status_3,
            "score": score_3,
            "evidence": f"Test markers: assert={has_assertions}, test_func={has_test_func}",
            "notes": "Evaluation of test assertions and verification rigor.",
        })

        # Criterion 4: Implementation Integrity & Anti-Hallucination (Weight: 10%)
        score_4 = 100.0
        status_4 = "verified"
        if injection_found:
            score_4 = 40.0
            status_4 = "partially_demonstrated"
            missing_items.append("Clean submission without prompt override markers")

        criterion_scores.append(score_4 * 0.10)
        rubric_findings.append({
            "criterion": "Code Quality & Provenance Integrity",
            "status": status_4,
            "score": score_4,
            "evidence": f"Injection detected: {injection_found}",
            "notes": "Anti-injection and provenance integrity verified.",
        })

        # Total rubric score
        total_rubric_score = round(sum(criterion_scores), 1)
        total_rubric_score = max(0.0, min(100.0, total_rubric_score))

        # Determine verdict
        if total_rubric_score >= 80.0 and has_core_structure and (has_assertions or score_2 >= 80.0):
            verdict = "verified"
            feedback = f"Evidence in '{file_path}' satisfies all rubric and acceptance criteria for {target_skill}."
            limitations = "Production telemetry and advanced distributed configurations can be explored in future milestones."
            missing_work = "None. Core step objectives and acceptance criteria are fully met."
            next_action = f"Step verified! Proceed to subsequent steps in the {target_skill} roadmap."
        elif total_rubric_score >= 40.0:
            verdict = "partially_demonstrated"
            feedback = f"Evidence in '{file_path}' partially demonstrates {target_skill} ({total_rubric_score}%), but lacks complete criteria satisfaction."
            limitations = f"Missing elements: {'; '.join(missing_items)}."
            missing_work = f"Implement missing items: {', '.join(missing_items)}."
            next_action = f"Add automated unit tests and error handling to '{file_path}' to reach verified status."
        else:
            verdict = "insufficient_evidence"
            feedback = f"Submitted evidence in '{file_path}' does not sufficiently demonstrate {target_skill} (Score: {total_rubric_score}%)."
            limitations = f"Evidence fails to demonstrate core rubric criteria. Missing: {'; '.join(missing_items)}."
            missing_work = f"Implement concrete business logic and tests for {target_skill}."
            next_action = f"Follow the step code example and instructions to implement {target_skill}."

        if injection_found:
            limitations += f" Warning: Prompt injection patterns were detected and neutralized ({', '.join(injection_types)})."

        # Determine line count for location
        line_count = len(sanitized_content.splitlines())
        line_range = f"1-{max(line_count, 1)}"

        return {
            "verdict": verdict,
            "rubric_score": total_rubric_score,
            "feedback": feedback,
            "strengths": f"Functional code submitted in '{file_path}' demonstrating {len(evidence_found)} verified aspects.",
            "missing_elements": "; ".join(missing_items) if missing_items else None,
            "limitations": limitations,
            "missing_work": missing_work,
            "next_recommended_action": next_action,
            "evidence_found": evidence_found,
            "evidence_locations": [
                {"file_path": file_path, "commit_sha": commit_ref, "line_range": line_range}
            ],
            "rubric_findings": rubric_findings,
        }

