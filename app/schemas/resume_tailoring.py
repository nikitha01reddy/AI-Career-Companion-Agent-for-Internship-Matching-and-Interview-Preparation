"""Schemas for resume tailoring (LLM I/O + LaTeX fill contract)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class TailoredEducationItem(BaseModel):
    """One education row for the LaTeX Education section (kept from source)."""

    degree: str = ""
    institution: str = ""
    start_date: str = ""
    end_date: str = ""
    details: str = ""


class TailoredCertificationItem(BaseModel):
    """One certification row kept directly from the source resume."""

    name: str = ""
    issuer: str = ""
    date: str = ""
    credential_url: str = ""


class TailoredExperienceItem(BaseModel):
    """One experience block (role/company header + bullets) — LLM tailored."""

    role: str = ""
    company: str = ""
    start_date: str = ""
    end_date: str = ""
    location: str = ""
    bullets: list[str] = Field(default_factory=list)


class TailoredProjectItem(BaseModel):
    """One project block (title, optional GitHub link, bullets, tech) — LLM tailored."""

    name: str = ""
    url: str = ""
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class SkillGroup(BaseModel):
    """Categorized skill line for the Skills section (e.g. Programming Languages)."""

    category: str = ""
    skills: list[str] = Field(default_factory=list)


class LLMTailoredSections(BaseModel):
    """Fields the LLM is allowed to rewrite.

    Contact, education, and certifications are merged from the source resume /
    auth identity outside the model — never trusted from this payload.
    """

    headline: str = ""
    summary: str = ""
    skill_groups: list[SkillGroup] = Field(default_factory=list)
    experience: list[TailoredExperienceItem] = Field(default_factory=list)
    projects: list[TailoredProjectItem] = Field(default_factory=list)


class TailoredResumeContent(BaseModel):
    """Final merged resume used to fill ``resume_template.tex.j2``.

    Empty sections are omitted at render time.
    """

    name: str = ""
    headline: str = ""
    email: str = ""
    phone_number: str = ""
    location: str = ""
    linkedin: str = ""
    summary: str = ""
    education: list[TailoredEducationItem] = Field(default_factory=list)
    certifications: list[TailoredCertificationItem] = Field(default_factory=list)
    skill_groups: list[SkillGroup] = Field(default_factory=list)
    experience: list[TailoredExperienceItem] = Field(default_factory=list)
    projects: list[TailoredProjectItem] = Field(default_factory=list)


class TailorResumeContext(BaseModel):
    """JSON payload sent to the LLM for one tailor request."""

    instructions: str
    source_headline: str = ""
    profile_skills: list[str] = Field(default_factory=list)
    location_preference: str | None = None
    experience: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    profile_summary: str = ""
    job: dict[str, Any] | None = None


class TailorResumeResponse(BaseModel):
    """JSON metadata returned alongside the generated PDF (when requested)."""

    resume_id: uuid.UUID
    content: TailoredResumeContent


def _clean(value: str) -> str:
    return value.strip()


def prune_llm_sections(sections: LLMTailoredSections) -> LLMTailoredSections:
    """Drop blank nested rows from LLM output."""
    skill_groups = [
        SkillGroup(
            category=_clean(group.category),
            skills=[_clean(skill) for skill in group.skills if _clean(skill)],
        )
        for group in sections.skill_groups
        if _clean(group.category) and any(_clean(skill) for skill in group.skills)
    ]
    experience = [
        TailoredExperienceItem(
            role=_clean(item.role),
            company=_clean(item.company),
            start_date=_clean(item.start_date),
            end_date=_clean(item.end_date),
            location=_clean(item.location),
            bullets=[_clean(bullet) for bullet in item.bullets if _clean(bullet)],
        )
        for item in sections.experience
        if _clean(item.role) or _clean(item.company) or any(_clean(b) for b in item.bullets)
    ]
    projects = [
        TailoredProjectItem(
            name=_clean(item.name),
            url=_clean(item.url),
            bullets=[_clean(bullet) for bullet in item.bullets if _clean(bullet)],
            technologies=[_clean(tech) for tech in item.technologies if _clean(tech)],
        )
        for item in sections.projects
        if _clean(item.name) or any(_clean(b) for b in item.bullets)
    ]
    return LLMTailoredSections(
        headline=_clean(sections.headline),
        summary=_clean(sections.summary),
        skill_groups=skill_groups,
        experience=experience,
        projects=projects,
    )


def prune_tailored_content(content: TailoredResumeContent) -> TailoredResumeContent:
    """Drop blank nested rows so empty LaTeX sections can be skipped safely."""
    education = [
        TailoredEducationItem(
            degree=_clean(item.degree),
            institution=_clean(item.institution),
            start_date=_clean(item.start_date),
            end_date=_clean(item.end_date),
            details=_clean(item.details),
        )
        for item in content.education
        if any(
            _clean(part)
            for part in (
                item.degree,
                item.institution,
                item.start_date,
                item.end_date,
                item.details,
            )
        )
    ]
    certifications = [
        TailoredCertificationItem(
            name=_clean(item.name),
            issuer=_clean(item.issuer),
            date=_clean(item.date),
            credential_url=_clean(item.credential_url),
        )
        for item in content.certifications
        if _clean(item.name) or _clean(item.issuer)
    ]
    llm = prune_llm_sections(
        LLMTailoredSections(
            headline=content.headline,
            summary=content.summary,
            skill_groups=content.skill_groups,
            experience=content.experience,
            projects=content.projects,
        )
    )
    return TailoredResumeContent(
        name=_clean(content.name),
        headline=llm.headline,
        email=_clean(content.email),
        phone_number=_clean(content.phone_number),
        location=_clean(content.location),
        linkedin=_clean(content.linkedin),
        summary=llm.summary,
        education=education,
        certifications=certifications,
        skill_groups=llm.skill_groups,
        experience=llm.experience,
        projects=llm.projects,
    )
