import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotAuthenticated(AppError):
    status_code = 401
    code = "not_authenticated"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class ProviderUnavailable(AppError):
    status_code = 503
    code = "ai_unavailable"

    def __init__(self, message: str, *, failures: list[str] | None = None):
        super().__init__(message)
        self.failures = failures or []


class CollegeAPIError(AppError):
    status_code = 502
    code = "college_api_error"

    def __init__(self, message: str, *, upstream_status: int | None = None, upstream_code: str | None = None):
        super().__init__(message)
        self.upstream_status = upstream_status
        self.upstream_code = upstream_code


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", [])[1:])
        message = f"Invalid {field}: {first.get('msg', 'bad input')}" if field else "Invalid request"
        return JSONResponse(_body("validation_error", message), status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exc)
        return JSONResponse(_body("internal_error", "Something went wrong. Please try again."), status_code=500)
