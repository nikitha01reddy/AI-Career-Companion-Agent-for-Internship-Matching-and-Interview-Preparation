"""Schemas for the conversational career agent (LLM I/O + API)."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ResumeContext(BaseModel):
    """Subset of a parsed resume forwarded to the chat agent."""

    headline: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    profile_summary: str = ""


class CareerContext(BaseModel):
    """Candidate context sent to the chat agent as system-prompt data."""

    name: str
    skills: list[str] = Field(default_factory=list)
    location_preference: str | None = None
    resume: ResumeContext | None = None


ChatIntent = Literal[
    "greet",
    "find_jobs",
    "match",
    "skill_gap",
    "interview_prep",
    "general",
]


class IntentDecision(BaseModel):
    """Structured intent classification produced by the router node."""

    intent: ChatIntent
    job_id: UUID | None = None
    query: str = ""
    location: str | None = None
    instructions: str = ""

    @field_validator("query", "instructions")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("location")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class ChatRequest(BaseModel):
    """Inbound chat message from a user."""

    message: str
    conversation_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value.strip()


class ChatResponse(BaseModel):
    """Outbound chat reply from the agent."""

    conversation_id: UUID
    reply: str
    intent: ChatIntent
    tool_used: str | None = None
