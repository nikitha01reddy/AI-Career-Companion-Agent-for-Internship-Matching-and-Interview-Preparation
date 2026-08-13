"""Resume tailoring workflow: resolve inputs → LLM → LaTeX → PDF."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.agents.resume_tailoring_agent import ResumeTailoringAgent
from app.core.config import Settings
from app.core.exceptions import (
    InvalidDocumentSelectionError,
    LatexCompileError,
    LatexCompilerMissingError,
    LatexRenderError,
    ResourceAccessDeniedError,
    ResourceNotFoundError,
)
from app.database.repositories.job_repository import JobRepository
from app.database.repositories.user_detail_repository import UserDetailRepository
from app.database.repositories.user_repository import UserRepository
from app.models.job import Job
from app.models.user import User
from app.models.user_detail import UserDetail
from app.schemas.resume_tailoring import (
    LLMTailoredSections,
    SkillGroup,
    TailoredCertificationItem,
    TailoredEducationItem,
    TailoredExperienceItem,
    TailoredProjectItem,
    TailoredResumeContent,
    TailorResumeContext,
    prune_tailored_content,
)
from app.schemas.user_detail import DocumentType, ResumeData
from app.services.user_detail_service import UserDetailService
from app.utils.latex_utils import escape_latex, sanitize_url


@dataclass(frozen=True)
class TailoredResumeArtifacts:
    """Generated resume artifacts for one tailor request."""

    resume_id: UUID
    content: TailoredResumeContent
    tex_path: Path
    pdf_path: Path


def split_skill_values(values: Iterable[str]) -> list[str]:
    """Split comma-joined skill lines into atomic skills, respecting parentheses."""
    atomic: list[str] = []
    for value in values:
        buffer: list[str] = []
        depth = 0
        for char in value:
            if char in "([":
                depth += 1
            elif char in ")]":
                depth = max(0, depth - 1)
            if char == "," and depth == 0:
                atomic.append("".join(buffer))
                buffer = []
                continue
            buffer.append(char)
        atomic.append("".join(buffer))
    seen: dict[str, str] = {}
    for skill in atomic:
        cleaned = skill.strip()
        if cleaned:
            seen.setdefault(cleaned.casefold(), cleaned)
    return list(seen.values())


def _description_to_bullets(description: str) -> list[str]:
    """Turn a project description paragraph into seed bullets."""
    cleaned = description.strip()
    if not cleaned:
        return []
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned)]
    return [sentence for sentence in sentences if sentence]


def _keep_supported_skills(groups: list[SkillGroup], resume: ResumeData) -> list[SkillGroup]:
    """Drop skills the source resume never claimed (e.g. copied from the job post)."""
    supported = " | ".join(split_skill_values(resume.skills)).casefold()
    if not supported:
        return groups

    filtered: list[SkillGroup] = []
    for group in groups:
        kept = [
            skill
            for skill in group.skills
            if re.search(rf"\b{re.escape(skill.strip().casefold())}\b", supported)
        ]
        if kept:
            filtered.append(SkillGroup(category=group.category, skills=kept))
    return filtered


def _restore_missing_experience_bullets(
    items: list[TailoredExperienceItem],
    resume: ResumeData,
) -> list[TailoredExperienceItem]:
    """Fall back to source responsibilities when the LLM returned no bullets."""
    by_role = {
        (item.role.strip().casefold(), item.company.strip().casefold()): item
        for item in resume.experience
    }
    restored: list[TailoredExperienceItem] = []
    for item in items:
        if item.bullets:
            restored.append(item)
            continue
        source = by_role.get((item.role.strip().casefold(), item.company.strip().casefold()))
        bullets = list(source.responsibilities) if source else []
        restored.append(item.model_copy(update={"bullets": bullets}))
    return restored


def _restore_missing_project_bullets(
    items: list[TailoredProjectItem],
    resume: ResumeData,
) -> list[TailoredProjectItem]:
    """Fall back to the source description when the LLM returned no bullets."""
    by_name = {item.name.strip().casefold(): item for item in resume.projects}
    restored: list[TailoredProjectItem] = []
    for item in items:
        if item.bullets:
            restored.append(item)
            continue
        source = by_name.get(item.name.strip().casefold())
        bullets = _description_to_bullets(source.description) if source else []
        restored.append(item.model_copy(update={"bullets": bullets}))
    return restored


class ResumeTailoringService:
    """Coordinate auth identity, resume/job resolution, LLM, and PDF generation."""

    def __init__(
        self,
        *,
        settings: Settings,
        users: UserRepository,
        details: UserDetailRepository,
        jobs: JobRepository,
        detail_service: UserDetailService,
        agent: ResumeTailoringAgent,
    ) -> None:
        self._settings = settings
        self._users = users
        self._details = details
        self._jobs = jobs
        self._detail_service = detail_service
        self._agent = agent

    async def tailor(
        self,
        *,
        user_id: UUID,
        instructions: str,
        resume_file_name: str | None = None,
        resume_content: bytes | None = None,
        user_detail_id: UUID | None = None,
        job_id: UUID | None = None,
    ) -> TailoredResumeArtifacts:
        """Generate a tailored resume PDF for the authenticated user."""
        cleaned_instructions = instructions.strip()
        if not cleaned_instructions:
            raise ValueError("instructions must not be blank")

        has_upload = resume_content is not None and bool((resume_file_name or "").strip())
        if has_upload == (user_detail_id is not None):
            raise ValueError("Provide exactly one of resume file or user_detail_id")

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("User not found")

        detail = await self._resolve_resume(
            user_id=user_id,
            resume_file_name=resume_file_name,
            resume_content=resume_content,
            user_detail_id=user_detail_id,
            has_upload=has_upload,
        )
        job = await self._resolve_job(job_id) if job_id is not None else None
        resume_data = self._detail_service.resume_data_from_detail(detail)

        context = self._build_context(user, resume_data, cleaned_instructions, job)
        llm_sections = await self._agent.tailor(context)
        tailored = prune_tailored_content(self._merge_resume(user, resume_data, llm_sections))

        resume_id = uuid4()
        return await asyncio.to_thread(self._render_and_compile, user_id, resume_id, tailored)

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
            raise InvalidDocumentSelectionError("Only a parsed resume can be tailored")
        return detail

    async def _resolve_job(self, job_id: UUID) -> Job:
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            raise ResourceNotFoundError("Job not found")
        return job

    @staticmethod
    def _build_context(
        user: User,
        resume: ResumeData,
        instructions: str,
        job: Job | None,
    ) -> TailorResumeContext:
        profile = user.profile
        job_payload = None
        if job is not None:
            job_payload = {
                "id": str(job.id),
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "description": job.description,
                "required_skills": job.required_skills,
                "salary": job.salary,
                "type": job.job_type,
                "duration": job.duration,
            }
        profile_skills = list(profile.skills) if profile and profile.skills else []
        return TailorResumeContext(
            instructions=instructions,
            source_headline=resume.headline,
            profile_skills=profile_skills,
            location_preference=profile.location_preference if profile else None,
            experience=[
                {
                    "role": item.role,
                    "company": item.company,
                    "start_date": item.start_date,
                    "end_date": item.end_date,
                    # Seed the LLM's `bullets` field so it rewrites rather than returning [].
                    "bullets": list(item.responsibilities),
                }
                for item in resume.experience
            ],
            projects=[
                {
                    "name": item.name,
                    "url": item.url,
                    "technologies": list(item.technologies),
                    "bullets": _description_to_bullets(item.description),
                }
                for item in resume.projects
            ],
            skills=split_skill_values([*profile_skills, *resume.skills]),
            profile_summary=resume.profile_summary,
            job=job_payload,
        )

    @staticmethod
    def _merge_resume(
        user: User,
        resume: ResumeData,
        llm: LLMTailoredSections,
    ) -> TailoredResumeContent:
        """Keep identity/education/certs from source; take rewritten sections from LLM."""
        location = ""
        if user.profile and user.profile.location_preference:
            location = user.profile.location_preference.strip()
        headline = llm.headline.strip() or resume.headline.strip()
        return TailoredResumeContent(
            name=user.name.strip(),
            email=user.email.strip(),
            phone_number=resume.phone_number.strip(),
            linkedin=resume.linkedin.strip(),
            location=location,
            headline=headline,
            summary=llm.summary,
            education=[
                TailoredEducationItem(
                    degree=item.degree,
                    institution=item.institution,
                    start_date=item.start_date,
                    end_date=item.end_date,
                    details=item.details,
                )
                for item in resume.education
            ],
            certifications=[
                TailoredCertificationItem(
                    name=item.name,
                    issuer=item.issuer,
                    date=item.date,
                    credential_url=item.credential_url,
                )
                for item in resume.certifications
            ],
            skill_groups=_keep_supported_skills(llm.skill_groups, resume),
            experience=_restore_missing_experience_bullets(llm.experience, resume),
            projects=_restore_missing_project_bullets(llm.projects, resume),
        )

    def _render_and_compile(
        self,
        user_id: UUID,
        resume_id: UUID,
        content: TailoredResumeContent,
    ) -> TailoredResumeArtifacts:
        output_dir = self._settings.tailored_resume_dir / str(user_id) / str(resume_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        tex_path = output_dir / "resume.tex"
        pdf_path = output_dir / "resume.pdf"
        json_path = output_dir / "resume.json"

        latex = self._render_latex(content)
        tex_path.write_text(latex, encoding="utf-8")
        json_path.write_text(
            json.dumps(content.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._compile_pdf(tex_path, pdf_path)
        return TailoredResumeArtifacts(
            resume_id=resume_id,
            content=content,
            tex_path=tex_path,
            pdf_path=pdf_path,
        )

    def _render_latex(self, content: TailoredResumeContent) -> str:
        template_path = self._settings.resume_template_path
        if not template_path.is_file():
            raise LatexRenderError(f"Resume template not found: {template_path}")

        env = Environment(
            loader=FileSystemLoader(str(template_path.parent)),
            autoescape=select_autoescape(enabled_extensions=()),
            variable_start_string="((",
            variable_end_string="))",
            block_start_string="((*",
            block_end_string="*))",
            comment_start_string="((#",
            comment_end_string="#))",
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = env.get_template(template_path.name)
        try:
            return template.render(**self._template_context(content))
        except Exception as exc:  # noqa: BLE001 - surface as domain error
            raise LatexRenderError("Failed to render resume LaTeX template") from exc

    @staticmethod
    def _template_context(content: TailoredResumeContent) -> dict[str, object]:
        """Escape all user text and attach raw URLs for \\href targets."""
        projects = []
        for item in content.projects:
            url_raw = sanitize_url(item.url)
            projects.append(
                {
                    "name": escape_latex(item.name),
                    "url": escape_latex(url_raw),
                    "url_raw": url_raw,
                    "bullets": [escape_latex(bullet) for bullet in item.bullets],
                    "technologies": [escape_latex(tech) for tech in item.technologies],
                }
            )
        return {
            "name": escape_latex(content.name),
            "headline": escape_latex(content.headline),
            "email": escape_latex(content.email),
            "email_raw": content.email,
            "phone_number": escape_latex(content.phone_number),
            "location": escape_latex(content.location),
            "linkedin": escape_latex(content.linkedin),
            "linkedin_raw": sanitize_url(content.linkedin),
            "summary": escape_latex(content.summary),
            "education": [
                {
                    "degree": escape_latex(item.degree),
                    "institution": escape_latex(item.institution),
                    "start_date": escape_latex(item.start_date),
                    "end_date": escape_latex(item.end_date),
                    "details": escape_latex(item.details),
                }
                for item in content.education
            ],
            "certifications": [
                {
                    "name": escape_latex(item.name),
                    "issuer": escape_latex(item.issuer),
                    "date": escape_latex(item.date),
                    "credential_url": escape_latex(sanitize_url(item.credential_url)),
                    "credential_url_raw": sanitize_url(item.credential_url),
                }
                for item in content.certifications
            ],
            "skill_groups": [
                {
                    "category": escape_latex(group.category),
                    "skills": [escape_latex(skill) for skill in group.skills],
                }
                for group in content.skill_groups
            ],
            "experience": [
                {
                    "role": escape_latex(item.role),
                    "company": escape_latex(item.company),
                    "start_date": escape_latex(item.start_date),
                    "end_date": escape_latex(item.end_date),
                    "location": escape_latex(item.location),
                    "bullets": [escape_latex(bullet) for bullet in item.bullets],
                }
                for item in content.experience
            ],
            "projects": projects,
        }

    def _compile_pdf(self, tex_path: Path, pdf_path: Path) -> None:
        compiler = self._settings.latex_compiler_path
        if shutil.which(compiler) is None and not Path(compiler).is_file():
            raise LatexCompilerMissingError(
                f"LaTeX compiler '{compiler}' was not found. Install TeX Live / MiKTeX "
                "or set LATEX_COMPILER_PATH."
            )

        with tempfile.TemporaryDirectory(prefix="resume_pdf_") as temp_dir:
            work_dir = Path(temp_dir)
            work_tex = work_dir / "resume.tex"
            work_tex.write_text(tex_path.read_text(encoding="utf-8"), encoding="utf-8")
            try:
                # Run inside work_dir with a relative filename: TeX would otherwise read
                # backslashes in an absolute Windows path as control sequences. DEVNULL
                # stdin keeps a failed run from blocking on TeX's interactive prompt.
                completed = subprocess.run(
                    [compiler, "-interaction=nonstopmode", "-halt-on-error", work_tex.name],
                    cwd=work_dir,
                    check=False,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=self._settings.latex_compile_timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise LatexCompileError("LaTeX compilation timed out") from exc

            generated = work_dir / "resume.pdf"
            if completed.returncode != 0 or not generated.is_file():
                snippet = (completed.stderr or completed.stdout or "")[-800:]
                raise LatexCompileError(f"LaTeX compilation failed: {snippet}")
            pdf_path.write_bytes(generated.read_bytes())
