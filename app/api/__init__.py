"""API routers package."""

from app.api.auth import router as auth_router
from app.api.conversations import router as chat_router
from app.api.cover_letter_tailoring import router as cover_letter_tailoring_router
from app.api.interview_prep import router as interview_prep_router
from app.api.jobs import router as jobs_router
from app.api.matching import router as matching_router
from app.api.resume_tailoring import router as resume_tailoring_router
from app.api.skill_gaps import router as skill_gaps_router
from app.api.user_details import router as user_details_router

__all__ = [
    "auth_router",
    "chat_router",
    "cover_letter_tailoring_router",
    "interview_prep_router",
    "jobs_router",
    "matching_router",
    "resume_tailoring_router",
    "skill_gaps_router",
    "user_details_router",
]
