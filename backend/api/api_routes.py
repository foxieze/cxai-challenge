"""
API routes for the Regulatory Compliance Accelerator.
Provides endpoints for the frontend dashboard.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from models.schemas import (
    ComplianceReport,
    ManagedSite,
)
from services.interpreter import interpret_regulation
from services.scanner import scan_all_sites
from services.validator import validate_matches
from services.drafter import generate_diffs
from core.audit_logger import audit_logger

router = APIRouter(prefix="/api/v1", tags=["compliance"])


# ─── Request Models ──────────────────────────────────────────────────────────

class RunComplianceRequest(BaseModel):
    """Request body for a full compliance pipeline run."""
    regulatory_update: str = Field(
        ...,
        min_length=10,
        description="Natural-language text of the regulatory update",
    )
    sites: list[ManagedSite] = Field(
        ...,
        min_length=1,
        description="List of managed sites to scan",
    )


class AuditQueryParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    action_filter: str | None = None


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post(
    "/compliance/run",
    response_model=ComplianceReport,
    summary="Run full compliance pipeline",
    description=(
        "Accepts a regulatory update in natural language and a list of sites. "
        "Returns a full compliance report with fixes and proposed diffs."
    ),
)
async def run_compliance_pipeline(request: RunComplianceRequest) -> ComplianceReport:
    """
    End-to-end compliance pipeline:
      1. Interpret the regulatory update → structured schema
      2. Scan all sites against the schema
      3. Validate matches → fix-focused feedback
      4. Generate proposed diffs for human review
      5. Return the complete report
    """
    try:
        # Step 1: Interpret
        regulation = await interpret_regulation(request.regulatory_update)

        # Step 2: Scan
        matches = await scan_all_sites(request.sites, regulation)

        # Step 3: Validate
        fixes = await validate_matches(matches, regulation)

        # Step 4: Draft diffs
        diffs = await generate_diffs(fixes, request.sites, regulation)

        # Step 5: Build report
        report = ComplianceReport(
            regulation=regulation,
            total_sites_scanned=len(request.sites),
            total_issues_found=len(fixes),
            fixes=fixes,
            diffs=diffs,
            summary=(
                f"Scanned {len(request.sites)} site(s) against regulation "
                f"'{regulation.title}'. Found {len(fixes)} issue(s) "
                f"requiring attention. {len(diffs)} proposed change(s) "
                f"generated for review."
            ),
        )

        await audit_logger.log(
            actor="api",
            action="run_compliance_pipeline",
            reasoning=(
                "Full pipeline executed successfully. Report generated for "
                "dashboard consumption with fixes and diffs for human review."
            ),
            input_summary=f"Regulation text: {request.regulatory_update[:200]}",
            output_summary=f"Report {report.report_id}: {len(fixes)} fixes",
            metadata={"report_id": report.report_id},
        )

        return report

    except Exception as e:
        await audit_logger.log(
            actor="api",
            action="run_compliance_pipeline_error",
            reasoning=f"Pipeline failed with error: {str(e)}. Logged for investigation.",
            input_summary=request.regulatory_update[:200],
            output_summary=f"ERROR: {str(e)[:200]}",
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/compliance/fixes",
    response_model=list,
    summary="Retrieve the Fix List for the dashboard",
    description="Returns all pending fix recommendations from the last pipeline run.",
)
async def get_fix_list():
    """
    Dashboard endpoint: retrieve all audit entries tagged as validation
    results, allowing the frontend to render the Fix List.
    """
    entries = await audit_logger.get_entries(
        limit=200, action_filter="validate_match"
    )
    return [entry.model_dump() for entry in entries]


@router.get(
    "/audit",
    summary="Retrieve audit trail",
    description="Returns the full audit trail for transparency and compliance.",
)
async def get_audit_trail(limit: int = 50, action_filter: str | None = None):
    entries = await audit_logger.get_entries(
        limit=limit, action_filter=action_filter
    )
    return [entry.model_dump() for entry in entries]


@router.get("/health", summary="Health check")
async def health_check():
    return {"status": "healthy", "service": "regulatory-compliance-accelerator"}