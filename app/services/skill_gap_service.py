"""Skill-gap workflow: resolve skills + job → LLM analysis."""

from __future__ import annotations

from uuid import UUID

from app.agents.skill_gap_agent import SkillGapAgent
from app.core.exceptions import (
    InvalidDocumentSelectionError,
    ResourceAccessDeniedError,
    ResourceNotFoundError,
)
from app.database.repositories.job_repository import JobRepository
from app.database.repositories.user_detail_repository import UserDetailRepository
from app.models.job import Job
from app.models.user_detail import UserDetail
from app.schemas.skill_gap import SkillGapContext, SkillGapResponse
from app.schemas.user_detail import DocumentType
from app.services.user_detail_service import UserDetailService


class SkillGapService:
    """Coordinate resume/skills resolution, job lookup, and LLM skill-gap analysis."""

    def __init__(
        self,
        *,
        details: UserDetailRepository,
        jobs: JobRepository,
        detail_service: UserDetailService,
        agent: SkillGapAgent,
    ) -> None:
        self._details = details
        self._jobs = jobs
        self._detail_service = detail_service
        self._agent = agent

    async def analyze(
        self,
        *,
        user_id: UUID,
        job_id: UUID,
        resume_file_name: str | None = None,
        resume_content: bytes | None = None,
        user_detail_id: UUID | None = None,
    ) -> SkillGapResponse:
        """Compare the user's skills against a job and return readiness gaps."""
        has_upload = resume_content is not None and bool((resume_file_name or "").strip())
        if has_upload == (user_detail_id is not None):
            raise ValueError("Provide exactly one of resume file or user_detail_id")

        detail = await self._resolve_resume(
            user_id=user_id,
            resume_file_name=resume_file_name,
            resume_content=resume_content,
            user_detail_id=user_detail_id,
            has_upload=has_upload,
        )
        job = await self._resolve_job(job_id)
        skills = self._skills_from_detail(detail)
        context = SkillGapContext(skills=skills, job=self._job_payload(job))
        analysis = await self._agent.analyze(context)
        return SkillGapResponse(
            job_title=job.title,
            readiness=analysis.readiness,
            matched_skills=analysis.matched_skills,
            skill_gaps=analysis.skill_gaps,
            summary=analysis.summary,
        )

    async def _resolve_resume(
        self,
        *,
        user_id: UUID,
        resume_file_name: str | None,
        resume_content: bytes | None,
        user_detail_id: UUID | None,
        has_upload: bool,
    ) -> UserDetail:
        if has_upload:
            assert resume_content is not None
            parsed = await self._detail_service.parse_resume(
                user_id,
                resume_file_name or "resume.pdf",
                resume_content,
            )
            detail = await self._details.get_by_id(parsed.id)
            if detail is None:
                raise ResourceNotFoundError("Parsed resume not found")
            return detail

        assert user_detail_id is not None
        detail = await self._details.get_by_id(user_detail_id)
        if detail is None:
            raise ResourceNotFoundError("User detail not found")
        if detail.user_id != user_id:
            raise ResourceAccessDeniedError("The selected document does not belong to this user")
        if detail.document_type != DocumentType.RESUME.value:
            raise InvalidDocumentSelectionError("Only a parsed resume can be used for skill gaps")
        return detail

    async def _resolve_job(self, job_id: UUID) -> Job:
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            raise ResourceNotFoundError("Job not found")
        return job

    @staticmethod
    def _skills_from_detail(detail: UserDetail) -> list[str]:
        raw = detail.skills or []
        seen: dict[str, str] = {}
        for skill in raw:
            cleaned = str(skill).strip()
            if cleaned:
                seen.setdefault(cleaned.casefold(), cleaned)
        return list(seen.values())

    @staticmethod
    def _job_payload(job: Job) -> dict[str, object]:
        return {
            "id": str(job.id),
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": job.description,
            "required_skills": list(job.required_skills or []),
            "salary": job.salary,
            "type": job.job_type,
            "role": job.role,
            "duration": job.duration,
        }
