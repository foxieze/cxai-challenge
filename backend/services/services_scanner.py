"""
Module 2: Scraping & Comparison Engine
Scans managed sites' HTML content against the RegulatorySchema
to find prohibited terms, missing disclaimers, and dosage violations.
"""

from __future__ import annotations
import re
from bs4 import BeautifulSoup
from models.schemas import (
    ManagedSite,
    RegulatorySchema,
    ScanMatch,
)
from core.audit_logger import audit_logger


def _extract_visible_text(html: str) -> list[tuple[str, str]]:
    """
    Parse HTML and return (element_selector, text) pairs for all
    visible text nodes.
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "meta", "link"]): #To remove non-visible elements
        tag.decompose()

    results: list[tuple[str, str]] = []
    for idx, element in enumerate(soup.find_all(string=True)):
        parent = element.parent
        selector = f"{parent.name}" if parent else "unknown"
        if parent and parent.get("class"):
            selector += f".{'.'.join(parent['class'])}"
        if parent and parent.get("id"):
            selector += f"#{parent['id']}"
        text = element.strip()
        if text:
            results.append((f"{selector}[{idx}]", text))

    return results


def _get_context(full_text: str, match_start: int, match_end: int, window: int = 50) -> str:
    """Return ±window characters around a match."""
    ctx_start = max(0, match_start - window)
    ctx_end = min(len(full_text), match_end + window)
    prefix = "..." if ctx_start > 0 else ""
    suffix = "..." if ctx_end < len(full_text) else ""
    return f"{prefix}{full_text[ctx_start:ctx_end]}{suffix}"


async def scan_site(
    site: ManagedSite,
    regulation: RegulatorySchema,
) -> list[ScanMatch]:
    """
    Scan a single site's HTML against the regulatory schema.

    Checks:
      1. Prohibited terms (case-insensitive, word-boundary matching)
      2. Missing required disclaimers
      3. Dosage claim violations
    """
    matches: list[ScanMatch] = []
    text_nodes = _extract_visible_text(site.html_content)
    full_text = " ".join(text for _, text in text_nodes)

    #Check1: Prohibited Terms
    for prohibited in regulation.prohibited_terms:
        pattern = re.compile(
            rf"\b{re.escape(prohibited.term)}\b", re.IGNORECASE
        )
        for selector, node_text in text_nodes:
            for m in pattern.finditer(node_text):
                matches.append(
                    ScanMatch(
                        site_id=site.site_id,
                        site_url=site.url,
                        matched_text=m.group(),
                        surrounding_context=_get_context(
                            node_text, m.start(), m.end()
                        ),
                        rule_violated=(
                            f"Prohibited term: '{prohibited.term}' — "
                            f"{prohibited.reason}"
                        ),
                        element_selector=selector,
                    )
                )

    #Check2: Missing Disclaimers
    for disclaimer in regulation.required_disclaimers:
        #To check if any affected drug is mentioned on the page
        drugs_on_page = [
            drug
            for drug in disclaimer.applies_to
            if re.search(rf"\b{re.escape(drug)}\b", full_text, re.IGNORECASE)
        ]
        if drugs_on_page:
            
            if disclaimer.text.lower() not in full_text.lower(): #To check if disclaimer text is present
                matches.append(
                    ScanMatch(
                        site_id=site.site_id,
                        site_url=site.url,
                        matched_text=f"[MISSING DISCLAIMER for: {', '.join(drugs_on_page)}]",
                        surrounding_context=(
                            f"Page mentions {', '.join(drugs_on_page)} but "
                            f"lacks required disclaimer: '{disclaimer.text[:80]}...'"
                        ),
                        rule_violated=(
                            f"Missing required disclaimer "
                            f"(placement: {disclaimer.placement})"
                        ),
                        element_selector=f"<{disclaimer.placement}>",
                    )
                )

    #Check3: Dosage Claims
    if regulation.max_dosage_claims:
        dosage_pattern = re.compile(
            r"\b(\d+)\s*(mg|mcg|ml|g)\b", re.IGNORECASE
        )
        for selector, node_text in text_nodes:
            for m in dosage_pattern.finditer(node_text):
                matches.append(
                    ScanMatch(
                        site_id=site.site_id,
                        site_url=site.url,
                        matched_text=m.group(),
                        surrounding_context=_get_context(
                            node_text, m.start(), m.end()
                        ),
                        rule_violated=(
                            f"Dosage claim detected — max allowed: "
                            f"{regulation.max_dosage_claims}"
                        ),
                        element_selector=selector,
                    )
                )

    # Audit
    await audit_logger.log(
        actor="scanner",
        action="scan_site",
        reasoning=(
            f"Scanned site '{site.name}' ({site.url}) against regulation "
            f"'{regulation.regulation_id}' to detect non-compliant content "
            f"before it reaches consumers."
        ),
        input_summary=f"Site: {site.url}, Regulation: {regulation.regulation_id}",
        output_summary=f"Found {len(matches)} potential violations.",
        metadata={
            "site_id": site.site_id,
            "regulation_id": regulation.regulation_id,
            "match_count": len(matches),
        },
    )

    return matches


async def scan_all_sites(
    sites: list[ManagedSite],
    regulation: RegulatorySchema,
) -> list[ScanMatch]:
    """Scan all managed sites and return aggregated matches."""
    all_matches: list[ScanMatch] = []
    for site in sites:
        site_matches = await scan_site(site, regulation)
        all_matches.extend(site_matches)
    return all_matches
