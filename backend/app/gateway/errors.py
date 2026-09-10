"""Shared Gateway error envelope.

The legacy ``detail`` field remains in every response for compatibility. New
clients should read ``error`` for a stable code, trace ID, and retry guidance.
"""

from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse

from deerflow.trace_context import TRACE_ID_HEADER, generate_trace_id, get_current_trace_id


def _default_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "not_authenticated",
        403: "permission_denied",
        404: "not_found",
        409: "conflict",
        413: "payload_too_large",
        422: "validation_error",
        429: "rate_limited",
    }.get(status_code, "service_unavailable" if status_code >= 500 else "request_failed")


def _detail_message(detail: Any, status_code: int) -> str:
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        return detail["message"]
    if isinstance(detail, str):
        return detail
    if status_code == 422:
        return "Request validation failed"
    return "The request could not be completed"


def gateway_error_response(
    status_code: int,
    detail: Any,
    *,
    retryable: bool | None = None,
    trace_id: str | None = None,
) -> JSONResponse:
    """Return the compatible detail plus the canonical machine-readable error."""
    trace_id = trace_id or get_current_trace_id() or generate_trace_id()
    detail_mapping = detail if isinstance(detail, dict) else {}
    code = detail_mapping.get("code")
    if not isinstance(code, str) or not code:
        code = _default_code(status_code)
    if retryable is None:
        retryable = detail_mapping.get("retryable")
    if not isinstance(retryable, bool):
        retryable = status_code >= 500 or status_code in {408, 409, 429}
    error = {
        "code": code,
        "message": _detail_message(detail, status_code),
        "trace_id": trace_id,
        "retryable": retryable,
    }
    return JSONResponse(
        status_code=status_code,
        content={"detail": jsonable_encoder(detail), "error": error},
        headers={TRACE_ID_HEADER: trace_id},
    )
