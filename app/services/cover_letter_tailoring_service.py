"""Cover-letter tailoring workflow: resolve inputs → LLM → LaTeX → PDF."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.agents.cover_letter_tailoring_agent import CoverLetterTailoringAgent
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
from app.schemas.cover_letter_tailoring import (
    LLMTailoredCoverLetterSections,
    TailoredCoverLetterContent,
    TailorCoverLetterContext,
    prune_tailored_content,
)
from app.schemas.user_detail import CoverLetterData, DocumentType
from app.services.user_detail_service import UserDetailService
from app.utils.latex_utils import escape_latex, sanitize_url


@dataclass(frozen=True)
class TailoredCoverLetterArtifacts:
    """Generated cover-letter artifacts for one tailor request."""

    cover_letter_id: UUID
    content: TailoredCoverLetterContent
    tex_path: Path
    pdf_path: Path


_CITY_STATE_ZIP_RE = re.compile(
    r"^(?P<city>.+?),\s*(?P<state>[A-Za-z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)$"
)
_LINKEDIN_SLUG_RE = re.compile(r"linkedin\.com/in/([^/?#]+)", re.IGNORECASE)


def split_company_address(address: str | None) -> tuple[str, str, str, str]:
    """Split a free-form company address into street and city/state/zip."""
    if not address or not address.strip():
        return "", "", "", ""

    lines = [line.strip() for line in address.splitlines() if line.strip()]
    if not lines:
        return "", "", "", ""
    if len(lines) == 1:
        return lines[0], "", "", ""

    street = lines[0]
    match = _CITY_STATE_ZIP_RE.match(lines[-1])
    if match:
        return (
            street,
            match.group("city").strip(),
            match.group("state").strip(),
            match.group("zip").strip(),
        )
    return street, lines[-1], "", ""


def linkedin_slug(value: str) -> str:
    """Return a LinkedIn profile slug suitable for /in/{slug} links."""
    cleaned = value.strip()
    if not cleaned:
        return ""
    match = _LINKEDIN_SLUG_RE.search(cleaned)
    if match:
        return match.group(1).strip("/")
    return cleaned.strip("/")


def split_signature(signature: str, applicant_name: str) -> tuple[str, str]:
    """Split a sign-off line from the printed name."""
    cleaned = signature.strip()
    if not cleaned:
        return "Sincerely", applicant_name

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if len(lines) >= 2:
        return lines[0].rstrip(","), lines[-1]
    if cleaned.casefold() == applicant_name.casefold():
        return "Sincerely", applicant_name
    return cleaned.rstrip(","), applicant_name


def _restore_missing_body_paragraphs(
    paragraphs: list[str],
    source: CoverLetterData,
) -> list[str]:
    """Fall back to source body paragraphs when the LLM returned none."""
    if paragraphs:
        return paragraphs
    return [paragraph for paragraph in source.body_paragraphs if paragraph.strip()]


class CoverLetterTailoringService:
    """Coordinate auth identity, cover-letter/job resolution, LLM, and PDF generation."""

    def __init__(
        self,
        *,
        settings: Settings,
        users: UserRepository,
        details: UserDetailRepository,
        jobs: JobRepository,
        detail_service: UserDetailService,
        agent: CoverLetterTailoringAgent,
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
        cover_letter_file_name: str | None = None,
        cover_letter_content: bytes | None = None,
        user_detail_id: UUID | None = None,
        job_id: UUID | None = None,
    ) -> TailoredCoverLetterArtifacts:
        """Generate a tailored cover-letter PDF for the authenticated user."""
        cleaned_instructions = instructions.strip()
        if not cleaned_instructions:
            raise ValueError("instructions must not be blank")

        has_upload = cover_letter_content is not None and bool(
            (cover_letter_file_name or "").strip()
        )
        if has_upload == (user_detail_id is not None):
            raise ValueError("Provide exactly one of cover letter file or user_detail_id")

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("User not found")

        detail = await self._resolve_cover_letter(
            user_id=user_id,
            cover_letter_file_name=cover_letter_file_name,
            cover_letter_content=cover_letter_content,
            user_detail_id=user_detail_id,
            has_upload=has_upload,
        )
        job = await self._resolve_job(job_id) if job_id is not None else None
        cover_letter = self._detail_service.cover_letter_data_from_detail(detail)

        context = self._build_context(cover_letter, cleaned_instructions, job)
        llm_sections = await self._agent.tailor(context)
        tailored = prune_tailored_content(self._merge_cover_letter(user, cover_letter, job, llm_sections))

        cover_letter_id = uuid4()
        return await asyncio.to_thread(
            self._render_and_compile,
            user_id,
            cover_letter_id,
            tailored,
        )

    async def _resolve_cover_letter(
        self,
        *,
        user_id: UUID,
        cover_letter_file_name: str | None,
        cover_letter_content: bytes | None,
        user_detail_id: UUID | None,
        has_upload: bool,
    ) -> UserDetail:
        if has_upload:
            assert cover_letter_content is not None
            parsed = await self._detail_service.parse_cover_letter(
                user_id,
                cover_letter_file_name or "cover_letter.pdf",
                cover_letter_content,
            )
            detail = await self._details.get_by_id(parsed.id)
            if detail is None:
                raise ResourceNotFoundError("Parsed cover letter not found")
            return detail

        assert user_detail_id is not None
        detail = await self._details.get_by_id(user_detail_id)
        if detail is None:
            raise ResourceNotFoundError("User detail not found")
        if detail.user_id != user_id:
            raise ResourceAccessDeniedError("The selected document does not belong to this user")
        if detail.document_type != DocumentType.COVER_LETTER.value:
            raise InvalidDocumentSelectionError("Only a parsed cover letter can be tailored")
        return detail

    async def _resolve_job(self, job_id: UUID) -> Job:
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            raise ResourceNotFoundError("Job not found")
        return job

    @staticmethod
    def _build_context(
        cover_letter: CoverLetterData,
        instructions: str,
        job: Job | None,
    ) -> TailorCoverLetterContext:
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
        return TailorCoverLetterContext(
            instructions=instructions,
            source_salutation=cover_letter.salutation,
            opening_paragraph=cover_letter.opening_paragraph,
            body_paragraphs=list(cover_letter.body_paragraphs),
            why_this_company=cover_letter.why_this_company,
            closing_paragraph=cover_letter.closing_paragraph,
            source_signature=cover_letter.signature,
            job=job_payload,
        )

    @staticmethod
    def _merge_cover_letter(
        user: User,
        cover_letter: CoverLetterData,
        job: Job | None,
        llm: LLMTailoredCoverLetterSections,
    ) -> TailoredCoverLetterContent:
        """Keep identity/header from auth + source/job; take rewritten sections from LLM."""
        applicant_name = user.name.strip()
        hiring_manager = (cover_letter.hiring_manager_name or "").strip()
        company_name = cover_letter.company_name.strip()
        company_address = cover_letter.company_address
        job_title = cover_letter.job_title.strip()

        if job is not None:
            company_name = job.company.strip() or company_name
            job_title = job.title.strip() or job_title
            if job.location.strip():
                company_address = job.location.strip()

        street, city, state, zip_code = split_company_address(company_address)
        closer, signature_name = split_signature(
            llm.signature or cover_letter.signature,
            applicant_name,
        )
        body_paragraphs = _restore_missing_body_paragraphs(llm.body_paragraphs, cover_letter)

        return TailoredCoverLetterContent(
            applicant_name=applicant_name,
            email=user.email.strip(),
            phone_number=cover_letter.phone_number.strip(),
            location=(cover_letter.address or "").strip(),
            letter_date=cover_letter.date.strip(),
            hiring_manager_name=hiring_manager,
            company_name=company_name,
            company_street=street,
            company_city=city,
            company_state=state,
            company_zip=zip_code,
            job_title=job_title,
            salutation=llm.salutation.strip() or cover_letter.salutation.strip(),
            opening_paragraph=llm.opening_paragraph.strip() or cover_letter.opening_paragraph.strip(),
            body_paragraphs=body_paragraphs,
            why_this_company=llm.why_this_company.strip() or cover_letter.why_this_company.strip(),
            closing_paragraph=llm.closing_paragraph.strip() or cover_letter.closing_paragraph.strip(),
            closer=closer,
            signature_name=signature_name,
        )

    def _render_and_compile(
        self,
        user_id: UUID,
        cover_letter_id: UUID,
        content: TailoredCoverLetterContent,
    ) -> TailoredCoverLetterArtifacts:
        output_dir = self._settings.tailored_cover_letter_dir / str(user_id) / str(cover_letter_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        tex_path = output_dir / "cover_letter.tex"
        pdf_path = output_dir / "cover_letter.pdf"
        json_path = output_dir / "cover_letter.json"

        latex = self._render_latex(content)
        tex_path.write_text(latex, encoding="utf-8")
        json_path.write_text(
            json.dumps(content.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._compile_pdf(tex_path, pdf_path)
        return TailoredCoverLetterArtifacts(
            cover_letter_id=cover_letter_id,
            content=content,
            tex_path=tex_path,
            pdf_path=pdf_path,
        )

    def _render_latex(self, content: TailoredCoverLetterContent) -> str:
        template_path = self._settings.cover_letter_template_path
        if not template_path.is_file():
            raise LatexRenderError(f"Cover letter template not found: {template_path}")

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
            raise LatexRenderError("Failed to render cover letter LaTeX template") from exc

    @staticmethod
    def _template_context(content: TailoredCoverLetterContent) -> dict[str, object]:
        """Escape all user text and attach raw values for href targets."""
        slug = linkedin_slug(content.linkedin)
        slug_raw = sanitize_url(f"https://linkedin.com/in/{slug}") if slug else ""
        phone_raw = re.sub(r"[^\d+]", "", content.phone_number)
        return {
            "applicant_name": escape_latex(content.applicant_name),
            "email": escape_latex(content.email),
            "email_raw": content.email,
            "phone_number": escape_latex(content.phone_number),
            "phone_raw": phone_raw,
            "location": escape_latex(content.location),
            "linkedin_slug": escape_latex(slug),
            "linkedin_slug_raw": slug_raw,
            "letter_date": escape_latex(content.letter_date),
            "hiring_manager_name": escape_latex(content.hiring_manager_name),
            "company_name": escape_latex(content.company_name),
            "company_street": escape_latex(content.company_street),
            "company_city": escape_latex(content.company_city),
            "company_state": escape_latex(content.company_state),
            "company_zip": escape_latex(content.company_zip),
            "job_title": escape_latex(content.job_title),
            "salutation": escape_latex(content.salutation),
            "opening_paragraph": escape_latex(content.opening_paragraph),
            "body_paragraphs": [escape_latex(paragraph) for paragraph in content.body_paragraphs],
            "why_this_company": escape_latex(content.why_this_company),
            "closing_paragraph": escape_latex(content.closing_paragraph),
            "closer": escape_latex(content.closer),
            "signature_name": escape_latex(content.signature_name),
        }

    def _compile_pdf(self, tex_path: Path, pdf_path: Path) -> None:
        compiler = self._settings.latex_compiler_path
        if shutil.which(compiler) is None and not Path(compiler).is_file():
            raise LatexCompilerMissingError(
                f"LaTeX compiler '{compiler}' was not found. Install TeX Live / MiKTeX "
                "or set LATEX_COMPILER_PATH."
            )

        with tempfile.TemporaryDirectory(prefix="cover_letter_pdf_") as temp_dir:
            work_dir = Path(temp_dir)
            work_tex = work_dir / "cover_letter.tex"
            work_tex.write_text(tex_path.read_text(encoding="utf-8"), encoding="utf-8")
            try:
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

            generated = work_dir / "cover_letter.pdf"
            if completed.returncode != 0 or not generated.is_file():
                snippet = (completed.stderr or completed.stdout or "")[-800:]
                raise LatexCompileError(f"LaTeX compilation failed: {snippet}")
            pdf_path.write_bytes(generated.read_bytes())
