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
    "You are a professional resume editor tailoring ONLY these sections for one target "
    "internship application: headline, summary, skill_groups, experience, and projects. "
    "The DOCUMENT JSON contains the candidate's source material plus optional `job` "
    "(target listing) and required `instructions` (user guidance). Honor `instructions` "
    "when they do not conflict with the rules below. "
    "The `job` field describes what the EMPLOYER wants — it is NOT the candidate's "
    "background. Never copy skills, tools, employers, or achievements from `job` unless "
    "they already appear in the candidate's experience, projects, or `skills` list. "
    "Only use facts present in the candidate's own data. Do NOT invent employers, "
    "degrees, projects, dates, skills, metrics, or tools. "
    "Writing quality (all rewritten text): "
    "Use crisp, professional language suitable for a one-page PDF resume. "
    "Prefer strong action verbs (Built, Designed, Implemented, Optimized, Led). "
    "Keep lines concise — each bullet should be one readable line (roughly 12–22 words). "
    "Lead with impact and relevance to the target role when possible. "
    "Do not use first-person pronouns (I/me/my). Do not use filler phrases "
    "(e.g. 'responsible for', 'helped with', 'various tasks'). "
    "Preserve any numbers, percentages, or scale facts exactly as given in the source. "
    "Section rules: "
    "headline — Job-relevant professional title under the candidate's name. "
    "Format like 'Role — Specialty' or 'Role | Focus' (e.g. 'Software Engineer — Python "
    "Backend'). Align to the target job title when justified by the candidate's background. "
    "If you cannot improve it, return `source_headline` unchanged (or empty if absent). "
    "Maximum ~8 words; no company names. "
    "summary — One Career Objective paragraph: 2–4 sentences, ~40–90 words. "
    "Open with the candidate's strongest fit for the target role, then mention key "
    "skills/stack and one concrete outcome area from experience or projects. "
    "Frame toward the target job without claiming skills the candidate lacks. "
    "skill_groups — Reorganize ONLY skills from the candidate's `skills` list into "
    "clear categories (category + skills array). Put the most job-relevant categories "
    "first. Use 3–7 groups when enough skills exist. Each skill string must already "
    "appear in `skills` (case-insensitive match allowed). Do not add new skills. "
    "experience — Return the SAME number of roles in the SAME order. Keep role, company, "
    "start_date, end_date, and location exactly as provided. Rewrite ONLY `bullets`. "
    "Use 2–4 strong bullets per role when source had content. Start each bullet with a "
    "past-tense verb. Never return an empty bullets list when the input item had bullets. "
    "projects — Return the SAME projects in the SAME order. Keep name, url, and "
    "technologies exactly as provided. Rewrite ONLY `bullets`. Use 2–4 bullets when "
    "source had content; highlight technical depth and outcomes relevant to the target job. "
    "Field-name rules (use these EXACT JSON keys — do not rename them): "
    "Top-level keys: headline, summary, skill_groups, experience, projects. "
    "`skill_groups` items must have: category, skills. "
    "`experience` items must have: role, company, start_date, end_date, location, bullets. "
    "`projects` items must have: name, url, bullets, technologies. "
    "Example skill_groups item: "
    '{"category":"Backend Development","skills":["FastAPI","PostgreSQL","Redis"]}. '
    "Example experience bullet style: "
    '"Built REST APIs with FastAPI serving 10k+ daily requests with Redis caching." '
    "Use empty string / empty list only when a field is genuinely unknown in the source."
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
