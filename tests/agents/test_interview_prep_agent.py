"""Tests for interview-prep agent pruning and step renumbering."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agents.interview_prep_agent import InterviewPrepAgent
from app.schemas.interview_prep import (
    BehavioralQuestion,
    FocusArea,
    InterviewPrepContext,
    InterviewPrepLLMResult,
    PreparationStep,
    TechnicalQuestion,
)


class TestInterviewPrepAgent:
    """LLM interview-prep generation + pruning."""

    @pytest.mark.asyncio
    async def test_prunes_blank_rows_and_renumbers_steps(self) -> None:
        client = AsyncMock()
        client.extract.return_value = InterviewPrepLLMResult(
            preparation_summary="Focus on Linux, Python, and monitoring.",
            focus_areas=[
                FocusArea(topic="Linux", reason="Required for SRE role", priority="high"),
                FocusArea(topic="  ", reason="ignored", priority="low"),
                FocusArea(topic="Python", reason="", priority="high"),
            ],
            technical_questions=[
                TechnicalQuestion(
                    question="What is a process?",
                    topic="Operating Systems",
                    difficulty="medium",
                    expected_points=["separate memory", "  ", "threads share memory"],
                ),
                TechnicalQuestion(
                    question="  ",
                    topic="Networking",
                    difficulty="easy",
                    expected_points=[],
                ),
            ],
            behavioral_questions=[
                BehavioralQuestion(
                    question="Tell me about a challenge.",
                    what_interviewer_looks_for=["Problem solving", "  ", "Ownership"],
                ),
                BehavioralQuestion(
                    question="  ",
                    what_interviewer_looks_for=[],
                ),
            ],
            preparation_plan=[
                PreparationStep(
                    step=9,
                    title="Review Requirements",
                    description="Study fundamentals.",
                ),
                PreparationStep(step=2, title="", description="ignored"),
                PreparationStep(step=3, title="Prepare Projects", description=""),
            ],
            interview_tips=["Use examples.", "  ", "Explain your thinking."],
        )
        agent = InterviewPrepAgent(client)
        context = InterviewPrepContext(
            job={"title": "SRE Intern", "required_skills": ["Linux", "Python"]},
            instructions="Focus on production troubleshooting.",
        )

        result = await agent.prepare(context)

        assert result.preparation_summary == "Focus on Linux, Python, and monitoring."
        assert [area.topic for area in result.focus_areas] == ["Linux"]
        assert len(result.technical_questions) == 1
        assert result.technical_questions[0].expected_points == [
            "separate memory",
            "threads share memory",
        ]
        assert len(result.behavioral_questions) == 1
        assert result.behavioral_questions[0].what_interviewer_looks_for == [
            "Problem solving",
            "Ownership",
        ]
        assert [step.step for step in result.preparation_plan] == [1]
        assert result.preparation_plan[0].title == "Review Requirements"
        assert result.interview_tips == ["Use examples.", "Explain your thinking."]
        client.extract.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handles_empty_plan_without_renumbering_error(self) -> None:
        client = AsyncMock()
        client.extract.return_value = InterviewPrepLLMResult(
            preparation_summary="Minimal prep.",
            focus_areas=[],
            technical_questions=[],
            behavioral_questions=[],
            preparation_plan=[],
            interview_tips=[],
        )
        agent = InterviewPrepAgent(client)
        context = InterviewPrepContext(job=None, instructions="general prep")

        result = await agent.prepare(context)

        assert result.preparation_plan == []
