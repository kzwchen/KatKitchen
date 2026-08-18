"""A single error shape for the whole API: {"detail": str, "code": str}.

`AppError` covers deliberate, application-raised errors (see the handler
below). The other two handlers make sure FastAPI/Starlette's own error
paths -- pydantic validation failures, unmatched routes, wrong methods, and
any bare `HTTPException` -- conform to the same shape instead of bypassing
it."""

from __future__ import annotations

import re
from http import HTTPStatus

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
    )


async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    messages = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()))
        message = error.get("msg", "Invalid value")
        messages.append(f"{location}: {message}" if location else message)
    detail = "; ".join(messages) if messages else "Invalid request"
    return JSONResponse(
        status_code=422,
        content={"detail": detail, "code": "validation_error"},
    )


def _code_from_status(status_code: int) -> str:
    """Derive a snake_case code from an HTTP status, e.g. 404 -> not_found,
    405 -> method_not_allowed. Falls back to "http_error" for codes with no
    known phrase."""
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        return "http_error"
    code = re.sub(r"[^a-zA-Z0-9]+", "_", phrase).strip("_").lower()
    return code or "http_error"


async def http_exception_handler(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail, "code": _code_from_status(exc.status_code)},
        headers=getattr(exc, "headers", None),
    )
