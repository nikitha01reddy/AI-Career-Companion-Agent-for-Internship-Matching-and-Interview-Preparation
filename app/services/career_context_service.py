"""Build the candidate career context from user, profile, and latest resume."""

from __future__ import annotations

from uuid import UUID

from app.database.repositories.user_detail_repository import UserDetailRepository
from app.database.repositories.user_repository import UserRepository
from app.models.user_detail import UserDetail
from app.schemas.conversation import CareerContext, ResumeContext
from app.schemas.user_detail import DocumentType


class CareerContextService:
    """Resolve a candidate's profile + latest resume into a CareerContext."""

    def __init__(
        self,
        users: UserRepository,
        details: UserDetailRepository,
    ) -> None:
        self._users = users
        self._details = details

    async def build(self, user_id: UUID) -> CareerContext:
        """Load the user, profile skills, and newest parsed resume."""
        user = await self._users.get_by_id(user_id)
        if user is None:
            return CareerContext(name="")

        profile = user.profile
        profile_skills = list(profile.skills or []) if profile is not None else []

        resumes = await self._details.list_by_user(user_id, DocumentType.RESUME)
        resume_ctx = self._resume_context(resumes[0]) if resumes else None

        merged_skills = self._merge_skills(profile_skills, resume_ctx)

        return CareerContext(
            name=user.name,
            skills=merged_skills,
            location_preference=(
                profile.location_preference if profile is not None else None
            ),
            resume=resume_ctx,
        )

    @staticmethod
    def _resume_context(detail: UserDetail) -> ResumeContext:
        return ResumeContext(
            headline=detail.headline or "",
            skills=list(detail.skills or []),
            experience=list(detail.experience or []),
            projects=list(detail.projects or []),
            education=list(detail.education or []),
            profile_summary=detail.profile_summary or "",
        )

    @staticmethod
    def _merge_skills(
        profile_skills: list[str],
        resume: ResumeContext | None,
    ) -> list[str]:
        seen: dict[str, str] = {}
        for skill in [*profile_skills, *(resume.skills if resume else [])]:
            cleaned = str(skill).strip()
            if cleaned:
                seen.setdefault(cleaned.casefold(), cleaned)
        return list(seen.values())
