"""Tool wrappers around existing services for the career agent.

Each tool is a thin async function that delegates to an existing service or
retriever. No business logic is duplicated; the agent dispatch node calls these
based on the classified intent. Every tool wraps its call in a try/except so
that any backend failure becomes a graceful ``ToolResult(error=...)`` instead of
an uncaught 500.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.agents.orchestrator import MatchingOrchestrator
from app.database.repositories.user_detail_repository import UserDetailRepository
from app.rag.retriever import InternshipRetriever
from app.schemas.matching import MatchingRequest
from app.schemas.user_detail import DocumentType
from app.services.interview_prep_service import InterviewPrepService
from app.services.skill_gap_service import SkillGapService


@dataclass
class ToolResult:
    """Outcome of a tool call — either structured data or a soft error message."""

    tool: str
    data: Any
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class CareerTools:
    """Wraps existing services as agent-callable tools.

    ``user_id`` and the latest resume id are resolved once per chat turn by the
    agent/service and injected into tool calls that need them.
    """

    def __init__(
        self,
        *,
        retriever: InternshipRetriever,
        matching: MatchingOrchestrator,
        skill_gap: SkillGapService,
        interview_prep: InterviewPrepService,
        details: UserDetailRepository,
    ) -> None:
        self._retriever = retriever
        self._matching = matching
        self._skill_gap = skill_gap
        self._interview_prep = interview_prep
        self._details = details

    async def latest_resume_id(self, user_id: UUID) -> UUID | None:
        """Return the id of the user's newest parsed resume, or None."""
        resumes = await self._details.list_by_user(user_id, DocumentType.RESUME)
        return resumes[0].id if resumes else None

    async def job_search(
        self,
        *,
        query: str,
        location: str | None = None,
        top_k: int = 5,
    ) -> ToolResult:
        """Search internships by natural-language query and optional location."""
        try:
            full_query = f"{query} in {location}" if location else query
            results = await asyncio.to_thread(self._retriever.search, full_query, top_k, None)
            jobs = [
                {
                    "job_id": r.job_id,
                    "score": round(r.score, 4),
                    "title": r.job.title if r.job else "",
                    "company": r.job.company if r.job else "",
                    "location": r.job.location if r.job else "",
                    "required_skills": list(r.job.skills_required) if r.job else [],
                    "description": r.job.description if r.job else "",
                    "apply_url": r.job.apply_url if r.job else "",
                }
                for r in results
            ]
            return ToolResult(tool="job_search", data=jobs)
        except Exception as exc:
            return ToolResult(tool="job_search", data=None, error=str(exc))

    async def match_jobs(self, *, user_id: UUID) -> ToolResult:
        """Match the user's latest resume against internships (ranked)."""
        try:
            resume_id = await self.latest_resume_id(user_id)
            if resume_id is None:
                return ToolResult(
                    tool="match_jobs",
                    data=None,
                    error="No parsed resume found. Ask the user to upload a resume first.",
                )
            response = await self._matching.match(
                user_id, MatchingRequest(user_detail_id=resume_id)
            )
            matches = [
                {
                    "job_id": m.citation.vector_document_id,
                    "score": round(m.score, 4),
                    "title": m.job.title if m.job else "",
                    "company": m.job.company if m.job else "",
                    "location": m.job.location if m.job else "",
                    "required_skills": list(m.job.skills_required) if m.job else [],
                    "apply_url": m.job.apply_url if m.job else "",
                }
                for m in response.matches
            ]
            return ToolResult(tool="match_jobs", data=matches)
        except Exception as exc:
            return ToolResult(tool="match_jobs", data=None, error=str(exc))

    async def skill_gap(self, *, user_id: UUID, job_id: UUID) -> ToolResult:
        """Compare the user's latest resume skills to a job's requirements."""
        try:
            resume_id = await self.latest_resume_id(user_id)
            if resume_id is None:
                return ToolResult(
                    tool="skill_gap",
                    data=None,
                    error="No parsed resume found. Ask the user to upload a resume first.",
                )
            response = await self._skill_gap.analyze(
                user_id=user_id,
                job_id=job_id,
                resume_file_name=None,
                resume_content=None,
                user_detail_id=resume_id,
            )
            return ToolResult(
                tool="skill_gap",
                data={
                    "job_title": response.job_title,
                    "readiness": response.readiness.model_dump(),
                    "matched_skills": [s.model_dump() for s in response.matched_skills],
                    "skill_gaps": [g.model_dump() for g in response.skill_gaps],
                    "summary": response.summary,
                },
            )
        except Exception as exc:
            return ToolResult(tool="skill_gap", data=None, error=str(exc))

    async def interview_prep(
        self,
        *,
        job_id: UUID | None = None,
        instructions: str = "",
    ) -> ToolResult:
        """Generate interview preparation guidance for a job and/or instructions."""
        try:
            if job_id is None and not instructions.strip():
                return ToolResult(
                    tool="interview_prep",
                    data=None,
                    error="interview_prep needs a job_id or instructions.",
                )
            response = await self._interview_prep.prepare(
                job_id=job_id,
                instructions=instructions,
            )
            return ToolResult(
                tool="interview_prep",
                data=response.model_dump(),
            )
        except Exception as exc:
            return ToolResult(tool="interview_prep", data=None, error=str(exc))
