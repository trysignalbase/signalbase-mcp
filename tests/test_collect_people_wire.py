"""Real collection dispatcher/serializer; only fetch is stubbed."""
import asyncio
import json
from urllib.parse import urlsplit, parse_qs
import pytest
import entry

PROFILES = ["v3", "recruiting_v3", "recruiting_v3_request", "monitoring_v3"]

def wire(monkeypatch, profile, status, body, arguments=None, authenticated=True):
    calls = []
    class Response:
        ok = 200 <= status < 300
        async def text(self):
            return json.dumps(body)
    response = Response()
    response.status = status
    async def fetch(url, options):
        calls.append((url, options))
        return response
    monkeypatch.setattr(entry, "fetch", fetch)
    monkeypatch.setattr(entry, "_api_base_override", "https://fixture.test/api/v2")
    result = asyncio.run(entry._handle_jsonrpc({"id": 1, "method": "tools/call", "params": {"name": "collect_company_people", "arguments": arguments if arguments is not None else {"company_domain": "example.com", "title": "QA Manager"}}}, "synthetic-key" if authenticated else None, profile))["result"]
    return result, calls

@pytest.mark.parametrize("profile", PROFILES)
def test_real_wire_bool_serialization_and_refresh_coverage(monkeypatch, profile):
    coverage = {"refresh": {"requested": True, "state": "unavailable", "on_demand": {"provider_attempted": False, "completeness": "not_established", "reason": "provider_unavailable"}}}
    body = {"success": True, "data": [], "coverage": coverage, "contact_review_items": [{"reason": "uncertain employer"}], "meta": {"creditsUsed": 1}}
    result, calls = wire(monkeypatch, profile, 200, body)
    assert not result.get("isError") and len(calls) == 1
    url, options = calls[0]
    assert urlsplit(url).path == "/api/v2/people"
    assert parse_qs(urlsplit(url).query)["refresh_missing"] == ["true"]
    assert parse_qs(urlsplit(url).query)["count"] == ["false"]
    assert parse_qs(urlsplit(url).query)["page"] == ["1"]
    assert options["method"] == "GET"
    payload = json.loads(result["content"][0]["text"])
    assert payload["coverage"] == coverage
    assert payload["contact_review_items"] == body["contact_review_items"]

@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("status", [400, 402, 429, 500, 503])
def test_real_http_rejection_is_error_unknown_settlement(monkeypatch, profile, status):
    result, calls = wire(monkeypatch, profile, status, {"success": False, "error": "rejected before a usable answer"})
    assert len(calls) == 1 and result["isError"] is True
    assert f"HTTP {status}" in result["content"][0]["text"]
    assert result["_meta"]["usage"] == {"api_calls": 1, "credits_used": None, "credits_known": False}

@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("arguments,authenticated", [(["invalid"], True), ({"company_domain": "example.com", "title": "QA Manager"}, False), ({"company_domain": "example.com", "title": "QA Manager", "country": "DE"}, True)])
def test_predispatch_rejections_are_zero_calls(monkeypatch, profile, arguments, authenticated):
    result, calls = wire(monkeypatch, profile, 200, {}, arguments, authenticated)
    assert not calls and result["isError"] is True
    assert result["_meta"]["usage"] == {"api_calls": 0, "credits_used": 0}
