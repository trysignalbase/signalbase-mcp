"""Real recruiting dispatcher/transport with only the HTTP fetch stubbed."""
import asyncio
import copy
import json

import pytest
import entry
from recruiting_contract import CONTRACT, REQUEST_CONTRACT


ROUTES = [
    ("recruiting_v3", "search_companies"),
    ("recruiting_v3_request", "search_companies"),
    ("recruiting_v3", "preview_recruiting_search"),
    ("recruiting_v3_request", "preview_recruiting_search"),
]


def dispatch(monkeypatch, status, body, profile="recruiting_v3", tool="search_companies", raw=False):
    calls = []
    original = copy.deepcopy(body)
    class Response:
        async def text(self):
            return body if raw else json.dumps(body)
    response = Response()
    response.status = status
    response.ok = 200 <= status < 300
    async def fetch(url, options):
        calls.append((url, options))
        return response
    monkeypatch.setattr(entry, "fetch", fetch)
    monkeypatch.setattr(entry, "_api_base_override", "https://app.example.test/api/v2")
    arguments = {"request": "Find employers", "operation_id": "http-error-operation-123"}
    if profile != "recruiting_v3_request" or tool == "preview_recruiting_search":
        arguments["criteria"] = {"company": {"hq": ["US"]}}
    result = asyncio.run(entry._handle_jsonrpc({"id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}, "stub-key", profile))["result"]
    payload = json.loads(result["content"][0]["text"])
    assert body == original
    assert len(calls) == 1  # No transport retry is introduced.
    request_route = profile == "recruiting_v3_request" and tool != "preview_recruiting_search"
    assert calls[0][0] == "https://app.example.test/api/v3/recruiting/" + ("request/" if request_route else "") + tool.replace("_", "-")
    assert calls[0][1]["headers"]["X-Recruiting-Contract"] == (REQUEST_CONTRACT if request_route else CONTRACT)["contract_hash"]
    assert calls[0][1]["headers"]["Idempotency-Key"] == payload["operation_id"] == "http-error-operation-123"
    return result, payload


@pytest.mark.parametrize("status", [400, 401, 422, 429, 500, 503])
@pytest.mark.parametrize("profile,tool", ROUTES)
def test_generic_http_errors_are_not_successful_tools(monkeypatch, status, profile, tool):
    body = {"error": "upstream rejection", "details": {"retryable": False}}
    result, payload = dispatch(monkeypatch, status, body, profile, tool)
    assert result["isError"] is True
    assert payload["execution_status"] == "failed"
    assert payload["http_error"] == {"status": status, "body": body}
    assert payload["error"] == body["error"]
    assert payload["usage"]["credits_known"] is False
    assert "credits_used" not in payload["usage"]


@pytest.mark.parametrize("credits", [0, 1])
def test_structured_http_error_preserves_failure_payload_envelope_and_known_meta(monkeypatch, credits):
    body = {"success": False, "error": "original wrapper", "data": {"execution_status": "failed", "errors": [{"code": "bounded_failure", "phase": "search"}], "usage": {"credits_used": credits}}, "meta": {"creditsUsed": credits, "replayed": True, "operationId": "app-ledger-id"}}
    result, payload = dispatch(monkeypatch, 503, body)
    assert result["isError"] is True
    assert payload["errors"] == body["data"]["errors"]
    assert payload["usage"] == body["data"]["usage"]
    assert payload["api_usage"] == body["meta"]
    assert payload["http_error"]["body"] == body


@pytest.mark.parametrize("execution_status", ["succeeded", "partial_failure"])
@pytest.mark.parametrize("profile,tool", ROUTES)
def test_success_and_partial_http_200_keep_records_and_usage_unchanged(monkeypatch, execution_status, profile, tool):
    data = {"execution_status": execution_status, "matches": [{"id": "retained", "source": "https://fixture.invalid/source"}], "errors": [] if execution_status == "succeeded" else [{"code": "one_branch_failed"}], "coverage": {"complete": execution_status == "succeeded"}}
    meta = {"creditsUsed": 1}
    result, payload = dispatch(monkeypatch, 200, {"success": True, "data": data, "meta": meta}, profile, tool)
    assert result["isError"] is False
    assert payload == {**data, "operation_id": "http-error-operation-123", "api_usage": meta}


def test_http_200_existing_failure_stays_failed(monkeypatch):
    data = {"execution_status": "failed", "errors": [{"code": "query_failed"}], "usage": {"credits_used": 0}}
    result, payload = dispatch(monkeypatch, 200, {"success": False, "data": data, "meta": {"creditsUsed": 0}})
    assert result["isError"] is True
    assert payload == {**data, "operation_id": "http-error-operation-123", "api_usage": {"creditsUsed": 0}}


def test_non_json_http_failure_keeps_status_and_unknown_cost(monkeypatch):
    result, payload = dispatch(monkeypatch, 502, "upstream unavailable", raw=True)
    assert result["isError"] is True
    assert payload["http_error"] == {"status": 502, "body": {"raw": "upstream unavailable"}}
    assert payload["usage"]["credits_known"] is False


def test_partial_records_survive_a_genuine_http_error(monkeypatch):
    data = {"execution_status": "partial_failure", "matches": [{"id": "retained"}], "errors": [{"code": "one_branch_failed"}]}
    result, payload = dispatch(monkeypatch, 503, {"success": False, "data": data, "meta": {"creditsUsed": 1}})
    assert result["isError"] is True  # HTTP failure, not a claim that no records exist.
    assert payload["execution_status"] == "partial_failure"
    assert payload["matches"] == data["matches"]
    assert payload["api_usage"]["creditsUsed"] == 1
