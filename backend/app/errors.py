"""A single error shape for the whole API: {"detail": str, "code": str}.

`AppError` covers deliberate, application-raised errors (see the handler
below). The other handlers make sure FastAPI/Starlette's own error
paths -- pydantic validation failures, unmatched routes, wrong methods, and
any bare `HTTPException` -- conform to the same shape instead of bypassing
it. `integrity_error_handler` does the same for the one path that reaches
past the application entirely: a database constraint the request violated."""

from __future__ import annotations

import re
from http import HTTPStatus

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
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


def _null_column(exc: IntegrityError) -> str | None:
    """Pull the column out of "NOT NULL constraint failed: table.column"."""
    match = re.search(r"NOT NULL constraint failed: \w+\.(\w+)", str(exc.orig))
    return match.group(1) if match else None


async def integrity_error_handler(
    _request: Request, exc: IntegrityError
) -> JSONResponse:
    """The database's own constraints, spoken in the API's error shape.

    One handler rather than a guard per column, deliberately. Every route
    still validates what it can, but the constraints are the only check that
    cannot be raced or forgotten: `exclude_unset` lets an explicit JSON null
    through to a NOT NULL column, and any SELECT-then-INSERT uniqueness check
    (see `add_meal`) can lose to a concurrent writer between the two
    statements. Before this handler those surfaced as bare 500s with no
    `code`, breaking the contract every other error path keeps.

    The kind of constraint decides the status: a null in the request body is
    the caller's malformed input (422), while everything else -- uniqueness,
    foreign keys, checks -- is a conflict with data already in the database
    (409). `sqlite_errorname` is the driver's own structured discriminator
    (Python 3.11+); if it is ever absent we fall back to the conflict
    reading, which is the safer of the two to be wrong about.
    """
    if getattr(exc.orig, "sqlite_errorname", "") == "SQLITE_CONSTRAINT_NOTNULL":
        column = _null_column(exc)
        detail = (
            f"{column} may not be null" if column else "A required field was null"
        )
        return JSONResponse(
            status_code=422,
            content={"detail": detail, "code": "null_not_allowed"},
        )
    return JSONResponse(
        status_code=409,
        content={
            "detail": "That change conflicts with data already in the database",
            "code": "constraint_violation",
        },
    )
