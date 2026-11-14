from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import routes_assistant, routes_auth, routes_misc
from app.container import build_services
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = await build_services(settings)
        yield
        await app.state.services.aclose()

    app = FastAPI(title="KIT Voice Assistant", version="1.0.0", lifespan=lifespan)
    register_error_handlers(app)

    if not settings.is_production:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response

    app.include_router(routes_auth.router)
    app.include_router(routes_assistant.router)
    app.include_router(routes_misc.router)
    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    if not (STATIC_DIR / "index.html").exists():
        return
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):  # type: ignore[no-untyped-def]
        if path.startswith("api/"):
            return JSONResponse({"error": {"code": "not_found", "message": "Not found"}}, status_code=404)
        candidate = (STATIC_DIR / path).resolve()
        if path and candidate.is_file() and STATIC_DIR in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")


app = create_app()
