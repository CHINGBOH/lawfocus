import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("lawfocus.api")


def _error_body(trace_id: str, code: str, message: str, details: dict | None = None) -> dict:
    return {"code": code, "message": message, "trace_id": trace_id, "details": details}


def _trace_id(request: Request) -> str:
    """Prefer the per-request id set by `assign_trace_id` middleware (main.py)
    so it matches whatever an AuditEvent for this same request recorded."""
    return getattr(request.state, "trace_id", None) or str(uuid.uuid4())


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        trace_id = _trace_id(request)
        if isinstance(exc.detail, dict):
            code = exc.detail.get("code", "ERROR")
            message = exc.detail.get("message", "request failed")
            details = exc.detail.get("details")
        else:
            code = "ERROR"
            message = str(exc.detail)
            details = None
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(trace_id, code, message, details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        trace_id = _trace_id(request)
        # Drop pydantic's "input" echo — it can replay a submitted password/secret
        # field verbatim back to the client on a type/format failure.
        redacted_errors = [{k: v for k, v in error.items() if k != "input"} for error in exc.errors()]
        return JSONResponse(
            status_code=422,
            content=_error_body(
                trace_id, "VALIDATION_ERROR", "request failed validation", {"errors": redacted_errors}
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        trace_id = _trace_id(request)
        logger.exception("unhandled error trace_id=%s", trace_id)
        return JSONResponse(
            status_code=500,
            content=_error_body(trace_id, "INTERNAL_ERROR", "an internal error occurred"),
        )
