"""Agent that rewrites only LLM-owned cover-letter sections."""

from __future__ import annotations

import json

from app.llm.client import StructuredExtractionClient
from app.schemas.cover_letter_tailoring import (
    LLMTailoredCoverLetterSections,
    TailorCoverLetterContext,
    prune_llm_sections,
)

TAILOR_INSTRUCTIONS = (
    "You are rewriting ONLY these cover-letter sections for job fit: salutation, "
    "opening_paragraph, body_paragraphs, why_this_company, closing_paragraph, and "
    "signature. "
    "The `job` field is the TARGET JOB the candidate is applying to. It describes what "
    "the employer wants — it is NOT the candidate's background. Never copy employer "
    "requirements from `job` into the letter as if they are the candidate's achievements. "
    "Only use facts present in the candidate's own cover-letter content. "
    "Do NOT invent employers, projects, skills, degrees, or numeric claims. "
    "body_paragraphs: the input already has a list of paragraphs. Return the SAME number "
    "of paragraphs, rewritten for clarity and job fit. Never return an empty list when "
    "the input had paragraphs. "
    "why_this_company: rewrite the motivation paragraph toward the target role/company "
    "when present; return empty string only when the source was empty. "
    "signature: a short sign-off line only (e.g. 'Sincerely' or 'Best regards'), not "
    "the candidate's full name. "
    "Use empty string / empty list only when a field is genuinely unknown."
)


class CoverLetterTailoringAgent:
    """Produce pruned LLM-only sections from seeded cover-letter paragraphs."""

    def __init__(self, extraction_client: StructuredExtractionClient) -> None:
        self._extraction_client = extraction_client

    async def tailor(self, context: TailorCoverLetterContext) -> LLMTailoredCoverLetterSections:
        """Call the LLM for rewritable sections only, then prune blank rows."""
        document = json.dumps(context.model_dump(mode="json"), ensure_ascii=False)
        raw = await self._extraction_client.extract(
            document,
            LLMTailoredCoverLetterSections,
            TAILOR_INSTRUCTIONS,
        )
        pruned = prune_llm_sections(raw)
        if not pruned.salutation.strip():
            pruned = pruned.model_copy(update={"salutation": context.source_salutation.strip()})
        return pruned
