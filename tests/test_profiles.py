import asyncio
import copy
import json
from types import SimpleNamespace

import pytest
import entry


def rpc(method, args=None, profile="classic"):
    return asyncio.run(entry._handle_jsonrpc({"id": 1, "method": method, "params": args or {}}, "key", profile))


def test_hr_discovery_has_distinct_identity_defaults_and_prompt():
    classic = rpc("initialize")["result"]
    hr = rpc("initialize", profile="hr")["result"]
    assert classic["serverInfo"]["name"] == "signalbase-mcp"
    assert hr["serverInfo"] == {"name": "signalbase-hr-mcp", "version": "2.0.0"}
    assert "HR and recruiting" in hr["instructions"]
    tools = rpc("tools/list", profile="hr")["result"]["tools"]
    props = next(t for t in tools if t["name"] == "search_hiring_signals")["inputSchema"]["properties"]
    assert props["verbose"]["default"] is False
    assert props["group_by_company"]["default"] is True
    assert props["filter_version"]["default"] == 2
    # Discovery cannot mutate the classic schemas.
    original = next(t for t in entry.TOOLS if t["name"] == "search_hiring_signals")["inputSchema"]["properties"]
    assert original["verbose"]["default"] is True
    assert original["group_by_company"]["default"] is False
    assert "default" not in original["filter_version"]
    hr_prompts = [p["name"] for p in rpc("prompts/list", profile="hr")["result"]["prompts"]]
    assert "recruiting-market" in hr_prompts
    assert "likely-first-hire" in hr_prompts
    assert "recruiting-market" not in [p["name"] for p in rpc("prompts/list")["result"]["prompts"]]
    assert "engineers" in rpc("prompts/get", {"name": "recruiting-market", "arguments": {"role": "engineers", "geography": "EU"}}, "hr")["result"]["messages"][0]["content"]["text"]


def test_hr_outlook_context_contains_supplied_floors_and_safety_rules():
    instructions = rpc("initialize", profile="hr")["result"]["instructions"]
    for expected in ("New VP | 20% | 30% | 36%", "New Head of | 15% | 23% | 28%", "New C-level | 7% | 11% | 13%", "Series A | 5% | 8% | 10%", "Seed | 3% | 4% | 5%"):
        assert expected in instructions
    assert "Never add rates" in instructions
    assert "not a particular role" in instructions
    prompt = rpc("prompts/get", {"name": "likely-first-hire", "arguments": {"geography": "US", "horizon": "30", "role": "engineer"}}, "hr")
    text = prompt["result"]["messages"][0]["content"]["text"]
    assert "within 30 days" in text
    assert "require separate role-specific evidence" in text


@pytest.mark.parametrize("suffix,hr", [("", False), ("/v2", True), ("/v2/", True), ("/?next=/v2", False)])
def test_fetch_routes_profiles_without_changing_auth(monkeypatch, suffix, hr):
    calls = []
    payload = {"data": [{"companyName": "Example", "title": "BDR", "companyLogo": "logo", "descriptionText": "x" * 500}], "meta": {"endpoint": "signals.hiring"}}

    async def api(endpoint, params, key):
        calls.append((params, key))
        return copy.deepcopy(payload)

    async def body():
        return json.dumps({"id": 9, "method": "tools/call", "params": {"name": "search_hiring_signals", "arguments": {"role": "bdr or engineers"}}})

    monkeypatch.setattr(entry, "_call_api", api)
    monkeypatch.setattr(entry, "_json_response", lambda value, status=200: value)
    request = SimpleNamespace(url="https://mcp.example" + suffix, method="POST", headers={"Authorization": "Bearer same-key"}, text=body)
    result = asyncio.run(entry.on_fetch(request, None))
    data = json.loads(result["result"]["content"][0]["text"])
    assert calls[0][1] == "same-key"
    assert calls[0][0]["role_logic"] == "or"
    assert len(data["data"]) == 1
    if hr:
        assert calls[0][0]["filter_version"] == 2
        assert calls[0][0]["include_expired"] is False
        assert "companyLogo" not in data["data"][0]
        assert data["companiesTotal"] == 1
    else:
        assert "filter_version" not in calls[0][0]
        assert "include_expired" not in calls[0][0]
        assert data == payload


def test_recruiting_path_routes_to_versioned_profile(monkeypatch):
    async def body():
        return json.dumps({"id": 9, "method": "initialize"})
    monkeypatch.setattr(entry, "_json_response", lambda value, status=200: value)
    request = SimpleNamespace(
        url="https://mcp.example/v2/recruiting",
        method="POST",
        headers={"Authorization": "Bearer same-key"},
        text=body,
    )
    result = asyncio.run(entry.on_fetch(request, None))
    assert result["result"]["serverInfo"] == {"name": "signalbase-recruiting", "version": "2.1.0"}


@pytest.mark.parametrize("history", [{"dateTo": "2025-03-31"}, {"date_preset": "last_year"}])
def test_hr_history_and_explicit_overrides(history):
    params, _, _ = entry._prepare_tool_args(history, "search_hiring_signals", "hr")
    assert "include_expired" not in params
    params, verbose, options = entry._prepare_tool_args({**history, "include_expired": False, "verbose": True, "group_by_company": False, "by_country": False}, "search_hiring_signals", "hr")
    assert params["include_expired"] is False
    assert verbose is True
    assert options == {"group_by_company": False, "by_country": False}


def test_hr_freshness_respects_date_preset_precedence():
    params, _, _ = entry._prepare_tool_args({"date_preset": "last_30d", "dateTo": "2025-03-31"}, "search_hiring_signals", "hr")
    assert params["include_expired"] is False


def test_concurrent_hr_and_classic_requests_do_not_share_defaults(monkeypatch):
    captured = []

    async def api(endpoint, params, key):
        captured.append((key, dict(params)))
        await asyncio.sleep(0)
        return {"data": [{"companyName": "Example", "companyLogo": "logo"}], "meta": {"endpoint": "signals.hiring"}}

    monkeypatch.setattr(entry, "_call_api", api)
    body = {"id": 1, "method": "tools/call", "params": {"name": "search_hiring_signals"}}

    async def both():
        return await asyncio.gather(entry._handle_jsonrpc(body, "hr", "hr"), entry._handle_jsonrpc(body, "classic"))

    hr, classic = asyncio.run(both())
    assert dict(captured)["classic"] == {}
    assert dict(captured)["hr"] == {"filter_version": 2, "include_expired": False}
    assert "companyLogo" in json.loads(classic["result"]["content"][0]["text"])["data"][0]
    assert "companyLogo" not in json.loads(hr["result"]["content"][0]["text"])["data"][0]


def test_compact_mode_never_decodes_urls_or_identifiers():
    url = "https://example.com/job?a=1&copy;=2"
    result = entry._trim_response({"data": [{"jobUrl": url, "id": "x&copy;y", "title": "Sales &amp; Marketing"}]})
    assert result["data"][0] == {"jobUrl": url, "id": "x&copy;y", "title": "Sales & Marketing"}


def test_slow_country_probe_preserves_combined_count(monkeypatch):
    async def stalled(*args):
        await asyncio.sleep(60)

    monkeypatch.setattr(entry, "_call_api", stalled)
    monkeypatch.setattr(entry, "BREAKDOWN_TIMEOUT_SECONDS", 0.001)
    result = asyncio.run(entry._with_country_breakdown("/signals/hiring", {"countries": "US,GB", "count": True}, "key", {"pagination": {"totalCount": 42}}))
    assert result["pagination"]["totalCount"] == 42
    assert result["byCountry"] == {"US": None, "GB": None}
    assert "failed" in result["byCountryNote"]


@pytest.mark.parametrize("count", [False, "false", "yes", "TRUE", 1])
def test_non_free_count_values_cannot_trigger_extra_requests(count):
    assert entry._country_breakdown_plan({"countries": "US,GB", "count": count}) is None
