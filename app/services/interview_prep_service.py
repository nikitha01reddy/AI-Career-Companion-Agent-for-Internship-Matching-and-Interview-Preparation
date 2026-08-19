"""Interview-prep workflow: resolve optional job + instructions → LLM guidance."""

from __future__ import annotations

from uuid import UUID

from app.agents.interview_prep_agent import InterviewPrepAgent
from app.core.exceptions import ResourceNotFoundError
from app.database.repositories.job_repository import JobRepository
from app.models.job import Job
from app.schemas.interview_prep import InterviewPrepContext, InterviewPrepResponse


class InterviewPrepService:
    """Coordinate optional job lookup and LLM interview-prep generation."""

    def __init__(
        self,
        *,
        jobs: JobRepository,
        agent: InterviewPrepAgent,
    ) -> None:
        self._jobs = jobs
        self._agent = agent

    async def prepare(
        self,
        *,
        job_id: UUID | None = None,
        instructions: str = "",
    ) -> InterviewPrepResponse:
        """Generate interview preparation guidance for a job and/or instructions."""
        job = await self._resolve_job(job_id) if job_id is not None else None
        context = InterviewPrepContext(
            job=self._job_payload(job) if job is not None else None,
            instructions=instructions.strip(),
        )
        result = await self._agent.prepare(context)
        return InterviewPrepResponse(
            job_title=job.title if job is not None else "",
            preparation_summary=result.preparation_summary,
            focus_areas=result.focus_areas,
            technical_questions=result.technical_questions,
            behavioral_questions=result.behavioral_questions,
            preparation_plan=result.preparation_plan,
            interview_tips=result.interview_tips,
        )

    async def _resolve_job(self, job_id: UUID) -> Job:
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            raise ResourceNotFoundError("Job not found")
        return job

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
