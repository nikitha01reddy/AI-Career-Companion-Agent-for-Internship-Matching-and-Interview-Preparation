"""Schemas for interview preparation (LLM I/O + API response)."""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

Priority = Literal["high", "medium", "low"]
Difficulty = Literal["easy", "medium", "hard"]


class FocusArea(BaseModel):
    """A subject the candidate should concentrate on while preparing."""

    topic: str
    reason: str
    priority: Priority

    @field_validator("topic", "reason")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class TechnicalQuestion(BaseModel):
    """A role-relevant technical interview question."""

    question: str
    topic: str
    difficulty: Difficulty
    expected_points: list[str] = Field(default_factory=list)

    @field_validator("question", "topic")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("expected_points")
    @classmethod
    def _strip_points(cls, value: list[str]) -> list[str]:
        return [point.strip() for point in value if point.strip()]


class BehavioralQuestion(BaseModel):
    """A behavioral interview question."""

    question: str
    what_interviewer_looks_for: list[str] = Field(default_factory=list)

    @field_validator("question")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("what_interviewer_looks_for")
    @classmethod
    def _strip_looks_for(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class PreparationStep(BaseModel):
    """A single ordered step in the preparation plan."""

    step: int = Field(ge=1)
    title: str
    description: str

    @field_validator("title", "description")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class InterviewPrepLLMResult(BaseModel):
    """Structured interview-prep payload produced by the LLM."""

    preparation_summary: str = ""
    focus_areas: list[FocusArea] = Field(default_factory=list)
    technical_questions: list[TechnicalQuestion] = Field(default_factory=list)
    behavioral_questions: list[BehavioralQuestion] = Field(default_factory=list)
    preparation_plan: list[PreparationStep] = Field(default_factory=list)
    interview_tips: list[str] = Field(default_factory=list)

    @field_validator("preparation_summary")
    @classmethod
    def _strip_summary(cls, value: str) -> str:
        return value.strip()

    @field_validator("interview_tips")
    @classmethod
    def _strip_tips(cls, value: list[str]) -> list[str]:
        return [tip.strip() for tip in value if tip.strip()]

    @model_validator(mode="after")
    def _renumber_steps(self) -> Self:
        if self.preparation_plan:
            self.preparation_plan = [
                step.model_copy(update={"step": index})
                for index, step in enumerate(self.preparation_plan, start=1)
            ]
        return self


class InterviewPrepContext(BaseModel):
    """JSON payload sent to the LLM for one interview-prep request."""

    job: dict[str, Any] | None = None
    instructions: str = ""


class InterviewPrepResponse(BaseModel):
    """API response for interview preparation guidance."""

    job_title: str
    preparation_summary: str = ""
    focus_areas: list[FocusArea] = Field(default_factory=list)
    technical_questions: list[TechnicalQuestion] = Field(default_factory=list)
    behavioral_questions: list[BehavioralQuestion] = Field(default_factory=list)
    preparation_plan: list[PreparationStep] = Field(default_factory=list)
    interview_tips: list[str] = Field(default_factory=list)


def prune_interview_prep_result(result: InterviewPrepLLMResult) -> InterviewPrepLLMResult:
    """Drop blank rows and renumber the preparation plan sequentially."""
    focus = [area for area in result.focus_areas if area.topic and area.reason]
    technical = [question for question in result.technical_questions if question.question]
    behavioral = [question for question in result.behavioral_questions if question.question]
    plan = [step for step in result.preparation_plan if step.title and step.description]
    return InterviewPrepLLMResult(
        preparation_summary=result.preparation_summary,
        focus_areas=focus,
        technical_questions=technical,
        behavioral_questions=behavioral,
        preparation_plan=plan,
        interview_tips=result.interview_tips,
    )
