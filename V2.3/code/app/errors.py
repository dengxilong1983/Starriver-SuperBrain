from __future__ import annotations
from typing import Any, Dict, Optional
from enum import IntEnum
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

try:
    # Best effort import to log metrics; keep optional to avoid hard dependency
    from .routes.v2_3.observability import logs as obs_logs, metrics as obs_metrics  # type: ignore
except Exception:  # pragma: no cover - optional
    obs_logs = None
    obs_metrics = None


class ErrorCode(IntEnum):
    # 4xx
    VALIDATION_ERROR = 40000
    INVALID_ARGUMENT = 40001
    UNAUTHORIZED = 40101
    FORBIDDEN = 40301
    NOT_FOUND = 40401
    CONFLICT = 40901
    LOCKED = 42301
    RATE_LIMITED = 42901
    # 5xx
    INTERNAL = 50000
    SERVICE_UNAVAILABLE = 50301


DEFAULT_CODE_BY_STATUS: Dict[int, ErrorCode] = {
    400: ErrorCode.INVALID_ARGUMENT,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,  # FastAPI validation
    423: ErrorCode.LOCKED,
    429: ErrorCode.RATE_LIMITED,
    500: ErrorCode.INTERNAL,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}


class ErrorResponse(JSONResponse):
    """JSONResponse with standard error body and x-trace-id header."""

    def __init__(self, *, status_code: int, code: int, message: str, trace_id: str, details: Optional[Dict[str, Any]] = None) -> None:
        content = {
            "code": int(code),
            "message": message,
            "trace_id": trace_id,
        }
        if details:
            content["details"] = details
        headers = {"x-trace-id": trace_id}
        super().__init__(status_code=status_code, content=content, headers=headers)


def _ensure_trace_id(request: Request) -> str:
    # Prefer middleware-injected trace_id; fallback to header; else new one
    return getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id") or str(uuid4())


def _log_error(level: str, message: str, *, trace_id: str, module: str, extra: Optional[Dict[str, Any]] = None) -> None:
    if obs_logs is None:
        return
    try:
        obs_logs.add(level, message, module=module, tags=[trace_id], extra={"trace_id": trace_id, **(extra or {})})
    except Exception:
        pass


def _inc_metric(name: str, value: int = 1) -> None:
    if obs_metrics is None:
        return
    try:
        obs_metrics.inc(name, value)
    except Exception:
        pass


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    trace_id = _ensure_trace_id(request)
    status = exc.status_code or 500

    # Extract message and details
    message = ""
    details: Dict[str, Any] = {}
    code: int = int(DEFAULT_CODE_BY_STATUS.get(status, ErrorCode.INTERNAL))

    if isinstance(exc.detail, dict):
        d = dict(exc.detail)
        # Read explicit code/message if provided
        msg = d.pop("message", None)
        if isinstance(msg, str) and msg:
            message = msg
        # Prefer explicit code if present
        c = d.pop("code", None)
        if isinstance(c, int):
            code = c
        # Do not duplicate trace_id field in details
        d.pop("trace_id", None)
        details = d
    elif isinstance(exc.detail, str):
        message = exc.detail

    if not message:
        message = exc.__class__.__name__

    _log_error("WARN" if status < 500 else "ERROR", f"HTTPException {status}: {message}", trace_id=trace_id, module="errors", extra={"status": status, "code": code})
    _inc_metric("http_exceptions_total", 1)

    return ErrorResponse(status_code=status, code=code, message=message, trace_id=trace_id, details=details or None)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    trace_id = _ensure_trace_id(request)
    # FastAPI defaults to 422; keep it but use unified code
    status = 422
    code = int(ErrorCode.VALIDATION_ERROR)
    try:
        # exc.errors() is a list of error objects
        details = {"errors": exc.errors()}
    except Exception:
        details = {"errors": [str(exc)]}

    _log_error("WARN", "Validation error", trace_id=trace_id, module="errors")
    _inc_metric("request_validation_total", 1)

    return ErrorResponse(status_code=status, code=code, message="validation error", trace_id=trace_id, details=details)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    trace_id = _ensure_trace_id(request)
    status = 500
    code = int(ErrorCode.INTERNAL)

    _log_error("ERROR", f"Unhandled exception: {exc}", trace_id=trace_id, module="errors")
    _inc_metric("unhandled_exceptions_total", 1)

    return ErrorResponse(status_code=status, code=code, message="internal error", trace_id=trace_id, details={"type": exc.__class__.__name__})


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers and ensure consistent error responses."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)