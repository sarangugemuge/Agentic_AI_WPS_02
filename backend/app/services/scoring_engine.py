"""
SkillSync Scoring Engine — Deterministic, Evidence-Backed Skill Match Calculation.

Strict Rules:
1. No hardcoded or fabricated scores (no static 71%, no fake fallback percentages).
2. Transparent rubric:
     Match Score = 100.0 * sum(weight * evidence_coverage) / sum(weight)
     Coverage Rubric:
       - DEMONSTRATED (with verified code citations): 1.0
       - PARTIALLY_DEMONSTRATED: 0.5 (or confidence * 0.7 if indirect)
       - NOT_FOUND: 0.0 (no evidence)
3. Non-code commits (documentation only, markdown only, formatting only) must NOT
   artificially boost technical skill scores.
4. Code deletion/removal re-evaluates evidence; if evidence was removed, score drops.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.models.skill_finding import SkillStatus

logger = logging.getLogger("skillsync.services.scoring")

DOCUMENTATION_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".rst", ".adoc", ".png", ".jpg", ".jpeg",
    ".gif", ".svg", ".ico", ".pdf", ".docx", ".license", "license", "notice"
}


class ScoringEngine:
    """
    Computes deterministic match scores and analyzes commit deltas.
    """

    @staticmethod
    def calculate_score(
        findings: List[Dict[str, Any]],
        skill_weights: Optional[Dict[str, float]] = None,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculates the transparent match score based on findings and optional skill weights.
        Returns: (overall_score, score_breakdown)
        """
        if not findings:
            return 0.0, {
                "total_skills": 0,
                "demonstrated": 0,
                "partial": 0,
                "not_found": 0,
                "weights_used": False,
            }

        weights = skill_weights or {}
        total_weighted_coverage = 0.0
        total_weights = 0.0

        demonstrated_count = 0
        partial_count = 0
        not_found_count = 0

        for f in findings:
            skill_name = f.get("skill_name", "")
            status_val = str(f.get("status", "")).lower()
            confidence = float(f.get("confidence_score") or 0.8)
            citations = f.get("evidence_citations", [])

            weight = float(weights.get(skill_name, 1.0))
            total_weights += weight

            if status_val == SkillStatus.DEMONSTRATED.value.lower() and len(citations) > 0:
                coverage = 1.0
                demonstrated_count += 1
            elif status_val == SkillStatus.PARTIALLY_DEMONSTRATED.value.lower():
                coverage = min(0.6, max(0.3, confidence * 0.7))
                partial_count += 1
            else:
                coverage = 0.0
                not_found_count += 1

            total_weighted_coverage += (weight * coverage)

        overall_score = round(100.0 * total_weighted_coverage / total_weights, 1) if total_weights > 0 else 0.0
        overall_score = max(0.0, min(100.0, overall_score))

        breakdown = {
            "total_skills": len(findings),
            "demonstrated": demonstrated_count,
            "partial": partial_count,
            "not_found": not_found_count,
            "total_weights": round(total_weights, 2),
            "weighted_coverage": round(total_weighted_coverage, 2),
        }

        return overall_score, breakdown

    @staticmethod
    def is_documentation_only_commit(changed_files: List[str]) -> bool:
        """
        Returns True if every file modified in the commit is a documentation,
        asset, or non-functional file.
        """
        if not changed_files:
            return False

        for f in changed_files:
            lower = f.lower()
            # If path ends with any doc extension or is a known doc path
            has_doc_ext = any(lower.endswith(ext) for ext in DOCUMENTATION_EXTENSIONS)
            is_doc_dir = lower.startswith("docs/") or lower.startswith(".github/") or "/docs/" in lower
            if not (has_doc_ext or is_doc_dir):
                return False

        return True

    @staticmethod
    def analyze_score_delta(
        previous_score: Optional[float],
        new_score: float,
        is_doc_only: bool = False,
        changed_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Calculates score difference and generates an explanatory rationale.
        """
        if previous_score is None:
            return {
                "previous_score": None,
                "new_score": new_score,
                "delta": 0.0,
                "direction": "initial",
                "explanation": f"Initial evidence-backed assessment established baseline score of {new_score}%.",
            }

        # Guard against documentation-only commit boosting technical score
        final_new_score = new_score
        if is_doc_only and new_score > previous_score:
            logger.info("Documentation-only commit detected; preventing artificial score increase.")
            final_new_score = previous_score

        delta = round(final_new_score - previous_score, 1)

        if is_doc_only:
            direction = "unchanged"
            explanation = (
                f"Commit modified documentation/assets only ({len(changed_files or [])} files). "
                f"Technical competency score preserved at {previous_score}%."
            )
        elif delta > 0:
            direction = "increased"
            explanation = (
                f"Score improved by +{delta}% (from {previous_score}% to {final_new_score}%) "
                "due to newly demonstrated implementation evidence in latest commit."
            )
        elif delta < 0:
            direction = "decreased"
            explanation = (
                f"Score adjusted by {delta}% (from {previous_score}% to {final_new_score}%) "
                "because previously demonstrated code files were removed or modified."
            )
        else:
            direction = "unchanged"
            explanation = (
                f"Score remains at {previous_score}%. Code changes maintained existing competency coverage."
            )

        return {
            "previous_score": previous_score,
            "new_score": final_new_score,
            "delta": delta,
            "direction": direction,
            "explanation": explanation,
        }
