"""User profile summary business logic."""

from __future__ import annotations

from uuid import UUID

from app.core.exceptions import ResourceNotFoundError
from app.database.repositories.user_repository import UserRepository
from app.schemas.user_detail import ProfileSummaryResponse


class ProfileService:
    """Return stored user and profile fields for matching."""

    def __init__(self, user_repository: UserRepository) -> None:
        self._users = user_repository

    async def create_summary(self, user_id: UUID) -> ProfileSummaryResponse:
        """Return the authenticated user's stored profile fields."""
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("User not found")

        location = user.profile.location_preference if user.profile else None
        skills = user.profile.skills if user.profile else []
        return ProfileSummaryResponse(
            user_id=user.id,
            name=user.name,
            email=user.email,
            location_preference=location,
            skills=skills,
            profile_summary="",
        )
