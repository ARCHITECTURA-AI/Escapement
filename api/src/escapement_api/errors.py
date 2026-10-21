from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class APIError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers or {}


def not_found(what: str = "Not found") -> APIError:
    return APIError(404, "NOT_FOUND", what)


def forbidden(message: str = "You do not have access to this.") -> APIError:
    return APIError(403, "FORBIDDEN", message)


def unauthorized(message: str = "Sign in or pass an API key.") -> APIError:
    return APIError(401, "UNAUTHORIZED", message)


async def api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        status_code=exc.status,
        headers=exc.headers,
    )


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [{"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg", "")} for e in exc.errors()]
    return JSONResponse(
        {
            "error": {
                "code": "INVALID_REQUEST",
                "message": "The request body does not match the endpoint schema.",
                "details": {"errors": errors},
            }
        },
        status_code=422,
    )
