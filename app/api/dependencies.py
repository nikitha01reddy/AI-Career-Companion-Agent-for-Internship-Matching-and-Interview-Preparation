"""Dependency providers for document and matching workflows."""

from fastapi import Depends
from langchain_ollama import ChatOllama
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.career_agent import CareerAgent
from app.agents.career_tools import CareerTools
from app.agents.cover_letter_agent import CoverLetterAgent
from app.agents.cover_letter_tailoring_agent import CoverLetterTailoringAgent
from app.agents.interview_prep_agent import InterviewPrepAgent
from app.agents.job_retrieval_agent import JobRetrievalAgent
from app.agents.orchestrator import MatchingOrchestrator
from app.agents.resume_agent import ResumeAgent
from app.agents.resume_tailoring_agent import ResumeTailoringAgent
from app.agents.skill_gap_agent import SkillGapAgent
from app.core.config import Settings, get_settings
from app.database.connection import get_db
from app.database.repositories.conversation_repository import ConversationRepository
from app.database.repositories.job_repository import JobRepository
from app.database.repositories.user_detail_repository import UserDetailRepository
from app.database.repositories.user_repository import UserRepository
from app.llm.client import OllamaStructuredExtractionClient
from app.rag.retriever import InternshipRetriever
from app.services.career_context_service import CareerContextService
from app.services.conversation_service import ConversationService
from app.services.cover_letter_tailoring_service import CoverLetterTailoringService
from app.services.interview_prep_service import InterviewPrepService
from app.services.job_scrape_service import JobScrapeService
from app.services.profile_service import ProfileService
from app.services.resume_tailoring_service import ResumeTailoringService
from app.services.skill_gap_service import SkillGapService
from app.services.user_detail_service import UserDetailService
from app.utils.file_utils import DocumentFileService


def get_user_detail_service(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserDetailService:
    """Provide the parsed-document service."""
    extraction_client = OllamaStructuredExtractionClient(
        model=settings.ollama_chat_model,
        base_url=settings.ollama_base_url,
    )
    return UserDetailService(
        repository=UserDetailRepository(db),
        file_service=DocumentFileService(
            settings.upload_dir,
            settings.max_upload_size_mb,
        ),
        resume_agent=ResumeAgent(extraction_client),
        cover_letter_agent=CoverLetterAgent(extraction_client),
    )


def get_profile_service(db: AsyncSession = Depends(get_db)) -> ProfileService:
    """Provide the user profile summary service."""
    return ProfileService(UserRepository(db))


def get_matching_orchestrator(
    db: AsyncSession = Depends(get_db),
) -> MatchingOrchestrator:
    """Provide the multi-agent matching orchestrator."""
    return MatchingOrchestrator(
        user_repository=UserRepository(db),
        detail_repository=UserDetailRepository(db),
        retrieval_agent=JobRetrievalAgent(InternshipRetriever()),
    )


def get_resume_tailoring_service(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    detail_service: UserDetailService = Depends(get_user_detail_service),
) -> ResumeTailoringService:
    """Provide the resume-tailoring workflow service."""
    extraction_client = OllamaStructuredExtractionClient(
        model=settings.ollama_chat_model,
        base_url=settings.ollama_base_url,
    )
    return ResumeTailoringService(
        settings=settings,
        users=UserRepository(db),
        details=UserDetailRepository(db),
        jobs=JobRepository(db),
        detail_service=detail_service,
        agent=ResumeTailoringAgent(extraction_client),
    )


def get_cover_letter_tailoring_service(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    detail_service: UserDetailService = Depends(get_user_detail_service),
) -> CoverLetterTailoringService:
    """Provide the cover-letter-tailoring workflow service."""
    extraction_client = OllamaStructuredExtractionClient(
        model=settings.ollama_chat_model,
        base_url=settings.ollama_base_url,
    )
    return CoverLetterTailoringService(
        settings=settings,
        users=UserRepository(db),
        details=UserDetailRepository(db),
        jobs=JobRepository(db),
        detail_service=detail_service,
        agent=CoverLetterTailoringAgent(extraction_client),
    )


def get_skill_gap_service(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    detail_service: UserDetailService = Depends(get_user_detail_service),
) -> SkillGapService:
    """Provide the skill-gap analysis workflow service."""
    extraction_client = OllamaStructuredExtractionClient(
        model=settings.ollama_chat_model,
        base_url=settings.ollama_base_url,
    )
    return SkillGapService(
        details=UserDetailRepository(db),
        jobs=JobRepository(db),
        detail_service=detail_service,
        agent=SkillGapAgent(extraction_client),
    )


def get_job_scrape_service() -> JobScrapeService:
    """Provide the mock scrape + parallel persist service."""
    return JobScrapeService()


def get_career_context_service(
    db: AsyncSession = Depends(get_db),
) -> CareerContextService:
    """Provide the candidate career-context builder."""
    return CareerContextService(
        users=UserRepository(db),
        details=UserDetailRepository(db),
    )


def get_career_agent(
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
) -> CareerAgent:
    """Provide the LangGraph conversational career agent."""
    extraction_client = OllamaStructuredExtractionClient(
        model=settings.ollama_chat_model,
        base_url=settings.ollama_base_url,
    )
    chat_model = ChatOllama(
        model=settings.ollama_chat_model,
        base_url=settings.ollama_base_url,
        temperature=0,
    )
    tools = CareerTools(
        retriever=InternshipRetriever(),
        matching=MatchingOrchestrator(
            user_repository=UserRepository(db),
            detail_repository=UserDetailRepository(db),
            retrieval_agent=JobRetrievalAgent(InternshipRetriever()),
        ),
        skill_gap=get_skill_gap_service(db, settings),
        interview_prep=get_interview_prep_service(db, settings),
        details=UserDetailRepository(db),
    )
    return CareerAgent(
        chat_model=chat_model,
        extraction_client=extraction_client,
        tools=tools,
    )


def get_conversation_service(
    db: AsyncSession = Depends(get_db),
    context_service: CareerContextService = Depends(get_career_context_service),
    agent: CareerAgent = Depends(get_career_agent),
) -> ConversationService:
    """Provide the chat workflow service."""
    return ConversationService(
        conversations=ConversationRepository(db),
        context_service=context_service,
        agent=agent,
    )


def get_interview_prep_service(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> InterviewPrepService:
    """Provide the interview-preparation workflow service."""
    extraction_client = OllamaStructuredExtractionClient(
        model=settings.ollama_chat_model,
        base_url=settings.ollama_base_url,
    )
    return InterviewPrepService(
        jobs=JobRepository(db),
        agent=InterviewPrepAgent(extraction_client),
    )
