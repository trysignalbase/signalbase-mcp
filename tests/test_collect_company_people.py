import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import entry


def test_v3_collection_is_distinct_from_read_only_search():
    for profile in ("v3", "recruiting_v3", "recruiting_v3_request", "monitoring_v3"):
        tools = {tool["name"]: tool for tool in entry._tools_for_profile(profile)}
        assert tools["search_people"]["annotations"]["readOnlyHint"] is True
        assert tools["collect_company_people"]["annotations"]["readOnlyHint"] is False
        assert tools["collect_company_people"]["annotations"]["destructiveHint"] is False
        assert set(tools["collect_company_people"]["inputSchema"]["properties"]) == {"company_domain", "company_linkedin_url", "title", "limit"}


def test_collection_forwards_explicit_scoped_refresh_without_extra_endpoint(monkeypatch):
    seen = []
    async def api_call(endpoint, params, key):
        seen.append((endpoint, params))
        return {"success": True, "data": [], "meta": {"creditsUsed": 1}}
    monkeypatch.setattr(entry, "_call_api", api_call)
    response = asyncio.run(entry._handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "collect_company_people", "arguments": {"company_domain": "example.com", "title": "QA Manager"}}}, "stub-key", "recruiting_v3"))
    assert not response["result"].get("isError")
    assert len(seen) == 1
    endpoint, params = seen[0]
    assert endpoint == "/people"
    assert params["refresh_missing"] is True
    assert params["page"] == 1 and params["count"] is False
    assert params["title"] == "QA Manager"


def test_read_search_cannot_request_collection_and_collection_cannot_add_filters(monkeypatch):
    async def no_call(*args, **kwargs):
        raise AssertionError("Unexpected upstream call")
    monkeypatch.setattr(entry, "_call_api", no_call)
    for name, arguments in (("search_people", {"refresh_missing": True, "company_domain": "example.com"}), ("collect_company_people", {"company_domain": "example.com", "title": "QA Manager", "country": "DE"})):
        response = asyncio.run(entry._handle_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments}}, "stub-key", "recruiting_v3"))
        assert response["result"]["isError"] is True


def test_classic_read_search_cannot_dispatch_hidden_refresh(monkeypatch):
    async def no_call(*args, **kwargs):
        raise AssertionError("Unexpected upstream call")
    monkeypatch.setattr(entry, "_call_api", no_call)
    response = asyncio.run(entry._handle_jsonrpc({"id": 3, "method": "tools/call", "params": {"name": "search_people", "arguments": {"company_domain": "example.com", "refresh_missing": True}}}, "stub-key", "classic"))
    assert response["result"]["isError"] is True
    assert response["result"]["_meta"]["usage"]["api_calls"] == 0


def test_collection_failure_does_not_invent_zero_credit_settlement(monkeypatch):
    async def api_call(*args):
        return {"error": True, "status": 500, "body": {"error": "Uncertain upstream result"}}
    monkeypatch.setattr(entry, "_call_api", api_call)
    response = asyncio.run(entry._handle_jsonrpc({"id": 4, "method": "tools/call", "params": {"name": "collect_company_people", "arguments": {"company_domain": "example.com", "title": "QA Manager"}}}, "stub-key", "recruiting_v3"))
    usage = response["result"]["_meta"]["usage"]
    assert usage["credits_used"] is None and usage["credits_known"] is False
