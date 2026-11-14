import time
from typing import Any

from fastapi import APIRouter

from app.api.deps import PrincipalDep, ServicesDep
from app.api.schemas import ConversationDetailOut, ConversationOut, MessageOut
from app.core.errors import NotFound

router = APIRouter(prefix="/api", tags=["misc"])

_HOME_TTL = 300
_home_cache: dict[str, Any] = {"at": 0.0, "data": None}


@router.get("/health")
async def health(services: ServicesDep) -> dict[str, Any]:
    return {"status": "ok", "llm_chain": services.llm.provider_names, "documents": len(services.knowledge.documents)}


@router.get("/public/home")
async def home(services: ServicesDep) -> dict[str, Any]:
    if _home_cache["data"] is None or time.monotonic() - _home_cache["at"] > _HOME_TTL:
        _home_cache["data"] = {"college": await services.college.college(), "courses": await services.college.courses()}
        _home_cache["at"] = time.monotonic()
    return _home_cache["data"]


@router.get("/history", response_model=list[ConversationOut])
async def history(principal: PrincipalDep, services: ServicesDep) -> list[ConversationOut]:
    rows = await services.conversations.list_for_owner(principal.owner_key)
    return [ConversationOut(id=c.id, title=c.title, created_at=c.created_at, updated_at=c.updated_at) for c in rows]


@router.get("/history/{conversation_id}", response_model=ConversationDetailOut)
async def conversation(conversation_id: str, principal: PrincipalDep, services: ServicesDep) -> ConversationDetailOut:
    found = await services.conversations.get_owned(principal.owner_key, conversation_id)
    if found is None:
        raise NotFound("Conversation not found.")
    c, messages = found
    return ConversationDetailOut(
        id=c.id,
        title=c.title,
        created_at=c.created_at,
        updated_at=c.updated_at,
        messages=[MessageOut(id=m.id, role=m.role, content=m.content, created_at=m.created_at) for m in messages],
    )
