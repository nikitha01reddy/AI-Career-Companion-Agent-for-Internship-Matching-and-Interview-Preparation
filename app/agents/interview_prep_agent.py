"""Agent that produces interview preparation guidance."""

from __future__ import annotations

import json

from app.llm.client import StructuredExtractionClient
from app.schemas.interview_prep import (
    InterviewPrepContext,
    InterviewPrepLLMResult,
    prune_interview_prep_result,
)

INTERVIEW_PREP_INSTRUCTIONS = (
    "You are an interview preparation coach for an internship candidate. "
    "The DOCUMENT JSON has an optional `job` (the target internship listing) "
    "and optional `instructions` (free-form guidance from the candidate). "
    "Use the job's `title`, `role`, `required_skills`, and `description` to "
    "decide what to prepare. Honor any `instructions` the candidate provided, "
    "adapting focus, depth, or topics accordingly. "
    "Return: "
    "`preparation_summary` — one concise sentence describing what this prep "
    "covers and why; "
    "`focus_areas` — the most important subjects to study, each with a short "
    "reason and priority of high|medium|low; "
    "`technical_questions` — role-relevant technical questions, each with a "
    "topic, difficulty of easy|medium|hard, and `expected_points` the model "
    "answer should touch; "
    "`behavioral_questions` — behavioral questions, each with "
    "`what_interviewer_looks_for` as a list of traits/skills; "
    "`preparation_plan` — an ordered list of actionable steps, each with a "
    "title and description; "
    "`interview_tips` — short, practical tips for the interview. "
    "Base every recommendation on the job and instructions only. Do not "
    "invent candidate details. Prefer concrete tool/tech names from the job. "
    "Provide 3-6 focus areas, 5-10 technical questions, 3-6 behavioral "
    "questions, 3-6 preparation steps, and 3-8 tips when possible. "
    "Field-name rules (use these EXACT JSON keys — do not rename them): "
    "`focus_areas` items must have: topic, reason, priority. "
    "`technical_questions` items must have: question, topic, difficulty, "
    "expected_points. Put the actual interview question in `question` and the "
    "subject category in `topic` — do not merge them. "
    "`behavioral_questions` items must have: question, what_interviewer_looks_for. "
    "`preparation_plan` items must have: step, title, description. "
    "Example focus_areas item: "
    "{\"topic\":\"Linux\",\"reason\":\"Required for SRE\",\"priority\":\"high\"}. "
    "Example technical_questions item: "
    "{\"question\":\"What is a process?\",\"topic\":\"Operating Systems\","
    "\"difficulty\":\"medium\",\"expected_points\":[\"separate memory\"]}."
)


class InterviewPrepAgent:
    """Produce a pruned interview-prep plan from job details and instructions."""

    def __init__(self, extraction_client: StructuredExtractionClient) -> None:
        self._extraction_client = extraction_client

    async def prepare(self, context: InterviewPrepContext) -> InterviewPrepLLMResult:
        """Call the LLM for interview-prep JSON, then prune blank rows."""
        document = json.dumps(context.model_dump(mode="json"), ensure_ascii=False)
        raw = await self._extraction_client.extract(
            document,
            InterviewPrepLLMResult,
            INTERVIEW_PREP_INSTRUCTIONS,
        )
        return prune_interview_prep_result(raw)
