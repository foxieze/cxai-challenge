"""
Module 4: Drafting Logic
Generates 'Proposed Change Diffs' (before vs. after) for each flagged
issue so a human reviewer can approve before deployment.
"""

from __future__ import annotations
import re
from models.schemas import (
    FixRecommendation,
    ManagedSite,
    ProposedDiff,
    RegulatorySchema,
)
from core.audit_logger import audit_logger


async def generate_diffs(
    fixes: list[FixRecommendation],
    sites: list[ManagedSite],
    regulation: RegulatorySchema,
) -> list[ProposedDiff]:
    """
    For each fix, produce a before/after diff for human review.

    Args:
        fixes: Validated fix recommendations from the Validator.
        sites: The original managed sites (for 'before' content).
        regulation: The regulatory schema driving the changes.

    Returns:
        A list of ProposedDiff objects.
    """
    site_map = {s.site_id: s for s in sites}
    diffs: list[ProposedDiff] = []

    for fix in fixes:
        site = site_map.get(fix.site_id)
        if not site:
            continue

        diff = _create_diff_for_fix(fix, site, regulation)
        if diff:
            diffs.append(diff)

            await audit_logger.log(
                actor="drafter",
                action="generate_diff",
                reasoning=(
                    f"Generated proposed change diff for issue {fix.issue_id} "
                    f"on site '{site.name}'. This diff allows human review "
                    f"before any automated deployment, ensuring safety."
                ),
                input_summary=f"Fix: {fix.issue_id}, Site: {site.url}",
                output_summary=(
                    f"Diff {diff.diff_id}: "
                    f"{diff.change_type} — '{diff.before[:50]}...' → "
                    f"'{diff.after[:50]}...'"
                ),
                metadata={
                    "diff_id": diff.diff_id,
                    "issue_id": fix.issue_id,
                    "change_type": diff.change_type,
                    "site_id": site.site_id,
                },
            )

    return diffs


def _create_diff_for_fix(
    fix: FixRecommendation,
    site: ManagedSite,
    regulation: RegulatorySchema,
) -> ProposedDiff | None:
    """Create a single diff based on the fix type."""

    if "Prohibited term" in fix.reason: #Prohibited Term Replacement
        for pt in regulation.prohibited_terms:
            if pt.term.lower() in fix.matched_text.lower():
                replacement = pt.replacement or "[REMOVED]"
                before_snippet = _extract_snippet(
                    site.html_content, fix.matched_text
                )
                after_snippet = re.sub(
                    re.escape(fix.matched_text),
                    replacement,
                    before_snippet,
                    flags=re.IGNORECASE,
                )
                return ProposedDiff(
                    issue_id=fix.issue_id,
                    site_id=fix.site_id,
                    site_url=fix.site_url,
                    before=before_snippet,
                    after=after_snippet,
                    change_type="replacement",
                    reasoning=(
                        f"Term '{pt.term}' is prohibited by regulation "
                        f"{regulation.regulation_id}: {pt.reason}. "
                        f"Replacing with '{replacement}'."
                    ),
                )

    if "Missing required disclaimer" in fix.reason:  #Missing Disclaimer Insertion
        for disc in regulation.required_disclaimers:
            disclaimer_html = (
                f'<div class="regulatory-disclaimer" '
                f'data-regulation="{regulation.regulation_id}">'
                f"{disc.text}</div>"
            )
            if disc.placement == "footer":
                before_snippet = "</body>"
                after_snippet = f"{disclaimer_html}\n</body>"
            elif disc.placement == "header":
                before_snippet = "<body>"
                after_snippet = f"<body>\n{disclaimer_html}"
            else:
                before_snippet = "<!-- no disclaimer -->"
                after_snippet = disclaimer_html

            return ProposedDiff(
                issue_id=fix.issue_id,
                site_id=fix.site_id,
                site_url=fix.site_url,
                before=before_snippet,
                after=after_snippet,
                change_type="insertion",
                reasoning=(
                    f"Regulation {regulation.regulation_id} requires a "
                    f"disclaimer in the {disc.placement}. Page references "
                    f"affected drugs but lacks the disclaimer."
                ),
            )


    if "Dosage claim" in fix.reason: #Dosage Claim
        before_snippet = _extract_snippet(site.html_content, fix.matched_text)
        return ProposedDiff(
            issue_id=fix.issue_id,
            site_id=fix.site_id,
            site_url=fix.site_url,
            before=before_snippet,
            after=f"<!-- REVIEW: dosage claim removed pending compliance --> "
                  f"[Dosage information available upon request]",
            change_type="replacement",
            reasoning=(
                f"Dosage claim '{fix.matched_text}' may exceed the "
                f"allowed maximum of {regulation.max_dosage_claims}. "
                f"Flagged for human review."
            ),
        )

    return None


def _extract_snippet(html: str, target: str, window: int = 80) -> str:
    """Extract a snippet of HTML around the target text."""
    idx = html.lower().find(target.lower())
    if idx == -1:
        return target
    start = max(0, idx - window)
    end = min(len(html), idx + len(target) + window)
    return html[start:end]
