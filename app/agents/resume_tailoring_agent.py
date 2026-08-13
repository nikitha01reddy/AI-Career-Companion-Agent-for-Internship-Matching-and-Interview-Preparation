"""Agent that rewrites only LLM-owned resume sections."""

from __future__ import annotations

import json

from app.llm.client import StructuredExtractionClient
from app.schemas.resume_tailoring import (
    LLMTailoredSections,
    TailorResumeContext,
    prune_llm_sections,
)

TAILOR_INSTRUCTIONS = (
    "You are rewriting ONLY these resume sections for job fit: "
    "headline (title under the name), summary, skill_groups, experience, and projects. "
    "The `job` field is the TARGET JOB the candidate is applying to. It describes what "
    "the employer wants — it is NOT the candidate's background. Never copy skills, "
    "tools, or achievements from `job` into the candidate's skills, summary, "
    "experience, or projects. "
    "Only use facts present in the candidate's own experience, projects, and skills. "
    "Do NOT invent employers, degrees, projects, dates, skills, or numeric claims. "
    "headline: prefer a clearer job-relevant title when justified by the target job / "
    "instructions; if you cannot improve it, return source_headline unchanged "
    "(or empty if source_headline is empty). "
    "summary: a short career-objective paragraph describing what the candidate "
    "actually has, framed toward the target role. "
    "skill_groups: select and reorganize the candidate's OWN skills into category "
    "groups (each with category + skills list); every skill must already appear in "
    "the candidate's `skills` list. "
    "experience and projects: each input item already has a `bullets` list. Return the "
    "SAME items with the SAME name/role/company, and rewrite every bullet for clarity "
    "and job fit. Never return an empty bullets list when the input item had bullets. "
    "Keep technologies and url values as provided. "
    "Use empty string / empty list only when a field is genuinely unknown."
)


class ResumeTailoringAgent:
    """Produce pruned LLM-only sections from experience/projects/skills/summary inputs."""

    def __init__(self, extraction_client: StructuredExtractionClient) -> None:
        self._extraction_client = extraction_client

    async def tailor(self, context: TailorResumeContext) -> LLMTailoredSections:
        """Call the LLM for rewritable sections only, then prune blank rows."""
        document = json.dumps(context.model_dump(mode="json"), ensure_ascii=False)
        raw = await self._extraction_client.extract(
            document,
            LLMTailoredSections,
            TAILOR_INSTRUCTIONS,
        )
        pruned = prune_llm_sections(raw)
        if not pruned.headline.strip():
            pruned = pruned.model_copy(update={"headline": context.source_headline.strip()})
        return pruned
