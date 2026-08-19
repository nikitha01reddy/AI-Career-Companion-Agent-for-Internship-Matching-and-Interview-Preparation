"""Schemas for skill-gap analysis (LLM I/O + API response)."""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator


def _coerce_readiness_aliases(data: Any) -> Any:
    """Normalize common cloud-model renames before ReadinessScore validation."""
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    if "matched" not in normalized and "matched_count" in normalized:
        normalized["matched"] = normalized.pop("matched_count")
    if "total" not in normalized and "total_count" in normalized:
        normalized["total"] = normalized.pop("total_count")
    return normalized


Importance = Literal["high", "medium", "low"]


class ReadinessScore(BaseModel):
    """How many job skills the candidate already covers."""

    matched: int = Field(ge=0)
    total: int = Field(ge=0)
    percentage: int = Field(ge=0, le=100)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        return _coerce_readiness_aliases(data)

    @field_validator("percentage", mode="before")
    @classmethod
    def _coerce_percentage(cls, value: Any) -> Any:
        if isinstance(value, float):
            return round(value)
        return value

    @model_validator(mode="after")
    def _clamp_matched_and_percentage(self) -> Self:
        matched = min(self.matched, self.total) if self.total else 0
        percentage = 0 if self.total == 0 else round((matched / self.total) * 100)
        self.matched = matched
        self.percentage = percentage
        return self


class MatchedSkill(BaseModel):
    """A skill the candidate already has that the job needs."""

    skill: str
    status: Literal["matched"] = "matched"

    @field_validator("skill")
    @classmethod
    def _strip_skill(cls, value: str) -> str:
        return value.strip()


class SkillGapItem(BaseModel):
    """A job-required skill the candidate is missing."""

    skill: str
    importance: Importance
    reason: str

    @field_validator("skill", "reason")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class SkillGapLLMResult(BaseModel):
    """Structured skill-gap payload produced by the LLM."""

    readiness: ReadinessScore
    matched_skills: list[MatchedSkill] = Field(default_factory=list)
    skill_gaps: list[SkillGapItem] = Field(default_factory=list)
    summary: str = ""

    @field_validator("summary")
    @classmethod
    def _strip_summary(cls, value: str) -> str:
        return value.strip()


class SkillGapContext(BaseModel):
    """JSON payload sent to the LLM for one skill-gap request."""

    skills: list[str] = Field(default_factory=list)
    job: dict[str, Any]


class SkillGapResponse(BaseModel):
    """API response for skill-gap analysis against a target job."""

    job_title: str
    readiness: ReadinessScore
    matched_skills: list[MatchedSkill] = Field(default_factory=list)
    skill_gaps: list[SkillGapItem] = Field(default_factory=list)
    summary: str = ""


def prune_skill_gap_result(result: SkillGapLLMResult) -> SkillGapLLMResult:
    """Drop blank rows and keep readiness consistent with listed skills."""
    matched = [
        MatchedSkill(skill=item.skill, status="matched")
        for item in result.matched_skills
        if item.skill
    ]
    gaps = [
        SkillGapItem(skill=item.skill, importance=item.importance, reason=item.reason)
        for item in result.skill_gaps
        if item.skill and item.reason
    ]
    total = len(matched) + len(gaps)
    readiness = ReadinessScore(
        matched=len(matched),
        total=total if total > 0 else result.readiness.total,
        percentage=0,
    )
    return SkillGapLLMResult(
        readiness=readiness,
        matched_skills=matched,
        skill_gaps=gaps,
        summary=result.summary,
    )
