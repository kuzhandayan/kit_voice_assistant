from fastapi import APIRouter, Request, Response

from app.api.deps import (
    SESSION_COOKIE,
    PrincipalDep,
    ServicesDep,
    hash_session_id,
    new_session_id,
    principal_to_dict,
    set_cookie,
)
from app.api.schemas import LoginIn, MeOut
from app.core.errors import AppError, CollegeAPIError, NotAuthenticated
from app.core.principal import Principal, role_from_college

router = APIRouter(prefix="/api/auth", tags=["auth"])

PROFILE_KEYS = ("department", "class_id", "class_code", "programme", "year_of_study")


@router.post("/login", response_model=MeOut)
async def login(body: LoginIn, request: Request, response: Response, services: ServicesDep) -> MeOut:
    services.rate_limiter.check(f"login:{request.client.host if request.client else 'unknown'}")
    try:
        data = await services.college.login(body.login_id.strip(), body.password)
    except CollegeAPIError as exc:
        if exc.upstream_status in {400, 401, 403, 404, 422}:
            raise NotAuthenticated("Invalid login ID or password.") from exc
        raise
    user = data["user"]
    role = role_from_college(user.get("role", ""))
    if role is None:
        raise AppError("This account type is not supported.", status_code=403, code="forbidden")
    principal = Principal(
        role=role,
        owner_key=f"user:{user['id']}",
        user_id=int(user["id"]),
        login_id=user.get("login_id"),
        name=user.get("full_name"),
        college_token=data["access_token"],
        profile={k: user.get(k) for k in PROFILE_KEYS},
    )
    ttl = min(
        int(data.get("expires_in") or services.settings.session_ttl_seconds), services.settings.session_ttl_seconds
    )
    raw = new_session_id()
    await services.sessions.create(hash_session_id(raw), principal_to_dict(principal), ttl)
    set_cookie(response, services, SESSION_COOKIE, raw, ttl)
    return MeOut(**principal.public_view())


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, services: ServicesDep) -> Response:
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        await services.sessions.delete(hash_session_id(raw))
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
async def me(principal: PrincipalDep) -> MeOut:
    return MeOut(**principal.public_view())
