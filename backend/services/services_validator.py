"""
Module 3: Explainable Validation
Produces fix-focused feedback with confidence scores — not just booleans.
Each violation gets: WHY it's wrong, WHAT to fix, HOW confident we are.
"""

from __future__ import annotations

import re

from models.schemas import (
    ComplianceStatus,
    FixRecommendation,
    RegulatorySchema,
    ScanMatch,
    Severity,
)
from core.audit_logger import audit_logger


def _compute_confidence(match: ScanMatch, regulation: RegulatorySchema) -> float:
    """
    Heuristic confidence score based on match quality.

    Scoring factors:
      - Exact prohibited term match: +0.4
      - Missing disclaimer (structural): +0.35
      - Dosage claim (needs human review): +0.25
      - Context richness (longer surrounding context): +0.1
      - Word-boundary match (not substring): +0.15
    """
    score = 0.0

    if "Prohibited term" in match.rule_violated:
        score += 0.40
        # Check if the match is an exact word-boundary match
        term = match.matched_text.lower()
        context_lower = match.surrounding_context.lower()
        pattern = rf"\b{re.escape(term)}\b"
        if re.search(pattern, context_lower):
            score += 0.15
    elif "Missing required disclaimer" in match.rule_violated:
        score += 0.35
    elif "Dosage claim" in match.rule_violated:
        score += 0.25

    # Context richness bonus
    if len(match.surrounding_context) > 30:
        score += 0.10

    # Regulatory severity multiplier
    severity_multiplier = {
        Severity.CRITICAL: 1.0,
        Severity.HIGH: 0.95,
        Severity.MEDIUM: 0.85,
        Severity.LOW: 0.75,
        Severity.INFO: 0.60,
    }
    score *= severity_multiplier.get(regulation.severity, 0.85)

    return round(min(score, 1.0), 2)


def _generate_fix(match: ScanMatch, regulation: RegulatorySchema) -> str:
    """Generate a specific, actionable fix recommendation."""

    if "Prohibited term" in match.rule_violated:
        # Find the matching prohibited term for its replacement
        for pt in regulation.prohibited_terms:
            if pt.term.lower() in match.matched_text.lower():
                if pt.replacement:
                    return (
                        f"Replace '{match.matched_text}' with "
                        f"'{pt.replacement}' in element "
                        f"{match.element_selector or 'unknown'}."
                    )
                return (
                    f"Remove the phrase '{match.matched_text}' from element "
                    f"{match.element_selector or 'unknown'}. "
                    f"Reason: {pt.reason}"
                )
        return f"Remove or replace '{match.matched_text}'."

    if "Missing required disclaimer" in match.rule_violated:
        for disc in regulation.required_disclaimers:
            return (
                f"Add the following disclaimer to the page "
                f"{disc.placement}: \"{disc.text}\""
            )
        return "Add the required regulatory disclaimer to this page."

    if "Dosage claim" in match.rule_violated:
        return (
            f"Review dosage claim '{match.matched_text}'. "
            f"Maximum allowed claim: {regulation.max_dosage_claims}. "
            f"Update or remove the claim to comply."
        )

    return "Manual review required for this flagged content."


def _determine_severity(match: ScanMatch, regulation: RegulatorySchema) -> Severity:
    """Map match type to severity level."""
    if "Prohibited term" in match.rule_violated:
        return regulation.severity  # inherit from regulation
    if "Missing required disclaimer" in match.rule_violated:
        return Severity.HIGH
    if "Dosage claim" in match.rule_violated:
        return Severity.MEDIUM
    return Severity.LOW


async def validate_matches(
    matches: list[ScanMatch],
    regulation: RegulatorySchema,
) -> list[FixRecommendation]:
    """
    Convert raw scanner matches into explainable, fix-focused feedback.

    Each FixRecommendation contains:
      - WHY the component is non-compliant
      - WHAT the recommended fix is
      - Confidence score (0.0–1.0)
    """
    fixes: list[FixRecommendation] = []

    for match in matches:
        confidence = _compute_confidence(match, regulation)
        fix_text = _generate_fix(match, regulation)
        severity = _determine_severity(match, regulation)

        # Determine compliance status based on confidence
        if confidence >= 0.6:
            status = ComplianceStatus.NON_COMPLIANT
        elif confidence >= 0.3:
            status = ComplianceStatus.REVIEW_REQUIRED
        else:
            status = ComplianceStatus.COMPLIANT

        fix = FixRecommendation(
            site_id=match.site_id,
            site_url=match.site_url,
            status=status,
            reason=match.rule_violated,
            recommended_fix=fix_text,
            confidence_score=confidence,
            severity=severity,
            matched_text=match.matched_text,
            rule_reference=regulation.regulation_id,
        )
        fixes.append(fix)

        # Audit each validation decision
        await audit_logger.log(
            actor="validator",
            action="validate_match",
            reasoning=(
                f"Evaluated match '{match.matched_text}' on {match.site_url}. "
                f"Confidence: {confidence}. Status: {status.value}. "
                f"This ensures every detection is explainable and actionable."
            ),
            input_summary=f"Match: {match.match_id} on {match.site_url}",
            output_summary=f"Fix: {fix.issue_id}, confidence={confidence}",
            metadata={
                "issue_id": fix.issue_id,
                "confidence": confidence,
                "status": status.value,
                "severity": severity.value,
            },
        )

    return fixes