"""
Module 1: Regulatory Interpreter
Takes a natural-language regulatory update and produces a structured
RegulatorySchema via LLM analysis.
"""

from __future__ import annotations

from models.schemas import RegulatorySchema
from core.llm_client import llm_client
from core.audit_logger import audit_logger

SYSTEM_PROMPT = """\
You are a regulatory compliance analyst for pharmaceutical web content.
Given a natural-language regulatory update, extract a structured JSON object
with EXACTLY these fields:

{
  "title": "short title",
  "effective_date": "YYYY-MM-DD",
  "summary": "plain English summary",
  "affected_drugs": ["DrugA", "DrugB"],
  "prohibited_terms": [
    {
      "term": "the prohibited phrase",
      "reason": "why it is prohibited",
      "replacement": "suggested replacement or null"
    }
  ],
  "required_disclaimers": [
    {
      "text": "exact disclaimer text",
      "placement": "footer",
      "applies_to": ["DrugA"]
    }
  ],
  "max_dosage_claims": "string or null",
  "severity": "critical|high|medium|low|info"
}

Return ONLY valid JSON. No explanations, no markdown fences.
"""


async def interpret_regulation(update_text: str) -> RegulatorySchema:
    """
    Parse a natural-language regulatory update into a structured schema.

    Args:
        update_text: The raw regulatory announcement text.

    Returns:
        A validated RegulatorySchema instance.
    """
    # Step 1: Call LLM
    data = await llm_client.complete_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=f"Regulatory Update:\n\n{update_text}",
    )

    # Step 2: Validate through Pydantic
    schema = RegulatorySchema(**data)

    # Step 3: Audit
    await audit_logger.log(
        actor="interpreter",
        action="interpret_regulation",
        reasoning=(
            "Converted natural-language regulatory update into structured "
            "schema to enable automated scanning and validation."
        ),
        input_summary=update_text[:300],
        output_summary=f"Regulation '{schema.title}' with "
                        f"{len(schema.prohibited_terms)} prohibited terms, "
                        f"{len(schema.required_disclaimers)} disclaimers.",
        metadata={
            "regulation_id": schema.regulation_id,
            "severity": schema.severity.value,
        },
    )

    return schema