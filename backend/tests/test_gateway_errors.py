from __future__ import annotations

import json

from app.gateway.errors import gateway_error_response


def test_gateway_error_response_keeps_detail_and_adds_traceable_contract() -> None:
    response = gateway_error_response(
        503,
        {
            "code": "map_snapshot_unavailable",
            "message": "Map snapshot is not ready",
            "retryable": True,
        },
        trace_id="trace-test-1",
    )

    body = json.loads(response.body)
    assert body["detail"] == {
        "code": "map_snapshot_unavailable",
        "message": "Map snapshot is not ready",
        "retryable": True,
    }
    assert body["error"] == {
        "code": "map_snapshot_unavailable",
        "message": "Map snapshot is not ready",
        "trace_id": "trace-test-1",
        "retryable": True,
    }
    assert response.headers["X-Trace-Id"] == "trace-test-1"


def test_gateway_error_response_derives_defaults_for_ordinary_details() -> None:
    response = gateway_error_response(404, "Record not found", trace_id="trace-test-2")

    body = json.loads(response.body)
    assert body["detail"] == "Record not found"
    assert body["error"] == {
        "code": "not_found",
        "message": "Record not found",
        "trace_id": "trace-test-2",
        "retryable": False,
    }
