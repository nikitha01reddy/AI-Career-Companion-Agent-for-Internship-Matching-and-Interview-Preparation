"""Agent that compares candidate skills against a job posting."""

from __future__ import annotations

import json

from app.llm.client import StructuredExtractionClient
from app.schemas.skill_gap import SkillGapContext, SkillGapLLMResult, prune_skill_gap_result

SKILL_GAP_INSTRUCTIONS = (
    "You are analyzing skill readiness for an internship application. "
    "The DOCUMENT JSON has `skills` (the candidate's skills) and `job` "
    "(the target internship listing). "
    "Compare the candidate's skills to what the job requires (use "
    "`required_skills`, `description`, `title`, and `role`). "
    "Return: "
    "`matched_skills` — skills the candidate already has that the job needs "
    "(each with status exactly \"matched\"); "
    "`skill_gaps` — important job skills the candidate lacks, each with "
    "importance of high|medium|low and a short reason (about one sentence); "
    "`readiness` — matched count, total count (matched + gaps), and percentage; "
    "`summary` — one concise sentence advising what to strengthen. "
    "Do not invent candidate skills. Prefer concrete tool/tech names from the job. "
    "If the job lists few explicit skills, infer the most relevant ones from the "
    "description. Keep total evaluated skills between 3 and 12 when possible."
)


class SkillGapAgent:
    """Produce a pruned skill-gap analysis from candidate skills + job details."""

    def __init__(self, extraction_client: StructuredExtractionClient) -> None:
        self._extraction_client = extraction_client

    async def analyze(self, context: SkillGapContext) -> SkillGapLLMResult:
        """Call the LLM for skill-gap JSON, then prune blank rows."""
        document = json.dumps(context.model_dump(mode="json"), ensure_ascii=False)
        raw = await self._extraction_client.extract(
            document,
            SkillGapLLMResult,
            SKILL_GAP_INSTRUCTIONS,
        )
        return prune_skill_gap_result(raw)
