import hashlib
import secrets
import uuid
from typing import Annotated

from fastapi import Depends, Request, Response

from app.container import Services
from app.core.errors import NotAuthenticated
from app.core.principal import Principal, Role, public_principal

SESSION_COOKIE = "kit_session"
VISITOR_COOKIE = "kit_visitor"


def get_services(request: Request) -> Services:
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(get_services)]


def hash_session_id(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def principal_to_dict(p: Principal) -> dict:
    return {
        "role": p.role.value,
        "owner_key": p.owner_key,
        "user_id": p.user_id,
        "login_id": p.login_id,
        "name": p.name,
        "college_token": p.college_token,
        "profile": p.profile,
    }


def principal_from_dict(d: dict) -> Principal:
    return Principal(
        Role(d["role"]),
        d["owner_key"],
        d.get("user_id"),
        d.get("login_id"),
        d.get("name"),
        d.get("college_token"),
        d.get("profile") or {},
    )


def set_cookie(response: Response, services: Services, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name, value, max_age=max_age, httponly=True, secure=services.settings.is_production, samesite="lax", path="/"
    )


async def current_principal(request: Request, response: Response, services: ServicesDep) -> Principal:
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        stored = await services.sessions.get(hash_session_id(raw))
        if stored:
            return principal_from_dict(stored)
        response.delete_cookie(SESSION_COOKIE, path="/")
    visitor = request.cookies.get(VISITOR_COOKIE)
    try:
        visitor = uuid.UUID(visitor or "").hex
    except ValueError:
        visitor = uuid.uuid4().hex
        set_cookie(response, services, VISITOR_COOKIE, visitor, 60 * 60 * 24 * 30)
    return public_principal(visitor)


PrincipalDep = Annotated[Principal, Depends(current_principal)]


async def require_signed_in(principal: PrincipalDep) -> Principal:
    if not principal.is_authenticated:
        raise NotAuthenticated("Please log in first.")
    return principal


async def rate_limited_principal(principal: PrincipalDep, services: ServicesDep) -> Principal:
    services.rate_limiter.check(principal.owner_key)
    return principal


LimitedPrincipalDep = Annotated[Principal, Depends(rate_limited_principal)]
