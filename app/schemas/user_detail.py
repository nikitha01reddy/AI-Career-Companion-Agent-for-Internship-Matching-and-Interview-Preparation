"""API schemas for parsed resumes and cover letters."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DocumentType(StrEnum):
    """Supported uploaded document categories."""

    RESUME = "resume"
    COVER_LETTER = "cover_letter"


class EducationItem(BaseModel):
    """Education entry extracted from a resume."""

    institution: str = ""
    degree: str = ""
    start_date: str = ""
    end_date: str = ""
    details: str = ""


class ProjectItem(BaseModel):
    """Project entry extracted from a resume."""

    name: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    url: str = ""


class ExperienceItem(BaseModel):
    """Employment entry extracted from a resume."""

    company: str = Field(
        default="",
        description=(
            "Employer or organisation name. It is usually printed on the line "
            "directly above or below the job title."
        ),
    )
    role: str = Field(default="", description="Job title held at this employer.")
    start_date: str = Field(default="", description="Start date as written, e.g. 'Feb 2026'.")
    end_date: str = Field(
        default="",
        description="End date as written. Use 'Present' for a current role.",
    )
    responsibilities: list[str] = Field(
        default_factory=list,
        description=(
            "Every bullet point listed under this role, each as one string. "
            "Bullets belong inside this list; never turn a bullet into its own "
            "experience entry."
        ),
    )


class CertificationItem(BaseModel):
    """Certification entry extracted from a resume."""

    name: str = ""
    issuer: str = ""
    date: str = ""
    credential_url: str = ""


class ResumeData(BaseModel):
    """Structured fields extracted from a resume."""

    education: list[EducationItem] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(
        default_factory=list,
        description=(
            "One entry per employer or internship in the experience section. "
            "Return an empty list only when the resume has no employment history."
        ),
    )
    headline: str = Field(
        default="",
        description=(
            "The professional title line printed directly under the candidate's "
            "name at the top of the resume, e.g. 'Associate Data Scientist'."
        ),
    )
    profile_summary: str = Field(
        default="",
        description=(
            "The candidate's summary, profile, or career objective paragraph, "
            "copied from the resume. Always fill this when such a section exists."
        ),
    )
    certifications: list[CertificationItem] = Field(default_factory=list)
    phone_number: str = ""
    linkedin: str = ""


class CoverLetterData(BaseModel):
    """Structured fields extracted from a cover letter."""

    applicant_name: str = ""
    email: str = ""
    phone_number: str = ""
    address: str | None = None
    date: str = ""
    hiring_manager_name: str | None = None
    company_name: str = ""
    company_address: str | None = None
    job_title: str = ""
    salutation: str = ""
    opening_paragraph: str = ""
    body_paragraphs: list[str] = Field(default_factory=list)
    why_this_company: str = ""
    closing_paragraph: str = ""
    signature: str = ""


class ParsedResumeResponse(BaseModel):
    """Persisted resume and its extracted content."""

    id: uuid.UUID
    user_id: uuid.UUID
    type: DocumentType = DocumentType.RESUME
    file_name: str
    file_path: str
    extracted: ResumeData
    created_at: datetime
    updated_at: datetime


class ParsedCoverLetterResponse(BaseModel):
    """Persisted cover letter and its extracted content."""

    id: uuid.UUID
    user_id: uuid.UUID
    type: DocumentType = DocumentType.COVER_LETTER
    file_name: str
    file_path: str
    extracted: CoverLetterData
    created_at: datetime
    updated_at: datetime


class ProfileSummaryResponse(BaseModel):
    """User identity, preferences, and generated matching summary."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    name: str
    email: str
    location_preference: str | None = None
    skills: list[str] = Field(default_factory=list)
    profile_summary: str
