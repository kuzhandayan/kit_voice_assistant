import asyncio
import logging
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.core.ratelimit import RateLimiter
from app.db.database import create_engine, create_session_factory, init_db
from app.db.repository import ConversationRepository, PendingActionRepository, SessionRepository
from app.services.agent.orchestrator import Agent
from app.services.agent.tools.registry import ToolRegistry
from app.services.college.client import CollegeClient
from app.services.college.clock import CollegeClock
from app.services.conversation import ConversationService
from app.services.knowledge.base import KnowledgeBase
from app.services.llm.router import LLMRouter
from app.services.speech.stt import SpeechToText
from app.services.speech.tts import TextToSpeech

logger = logging.getLogger(__name__)


@dataclass
class Services:
    settings: Settings
    engine: AsyncEngine
    http: httpx.AsyncClient
    college: CollegeClient
    clock: CollegeClock
    knowledge: KnowledgeBase
    sessions: SessionRepository
    conversations: ConversationRepository
    conversation_service: ConversationService
    stt: SpeechToText
    tts: TextToSpeech
    llm: LLMRouter
    rate_limiter: RateLimiter

    async def aclose(self) -> None:
        await self.college.aclose()
        await self.http.aclose()
        await self.engine.dispose()


async def build_services(settings: Settings) -> Services:
    engine = create_engine(settings.database_url)
    await init_db(engine)
    factory = create_session_factory(engine)
    http = httpx.AsyncClient(timeout=15)
    college = CollegeClient(
        settings.college_api_base_url, settings.college_participant_key, settings.college_api_timeout_seconds
    )
    clock = CollegeClock(college, settings.timezone)
    knowledge = KnowledgeBase(college, clock, settings.documents_refresh_seconds)
    conversations = ConversationRepository(factory)
    llm = LLMRouter.from_settings(settings)
    agent = Agent(llm, ToolRegistry(PendingActionRepository(factory)), settings.max_agent_steps)
    logger.info("LLM chain: %s", llm.provider_names or "none configured")
    services = Services(
        settings=settings,
        engine=engine,
        http=http,
        college=college,
        clock=clock,
        knowledge=knowledge,
        sessions=SessionRepository(factory),
        conversations=conversations,
        conversation_service=ConversationService(agent, conversations, college, clock, knowledge),
        stt=SpeechToText(settings, http),
        tts=TextToSpeech(settings, http),
        llm=llm,
        rate_limiter=RateLimiter(settings.rate_limit_per_minute),
    )
    asyncio.create_task(knowledge.refresh(force=True))
    return services
