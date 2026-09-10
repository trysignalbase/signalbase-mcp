"""The 1.0 tool-call contract: full JSON payload and exactly one upstream call."""
import asyncio
import copy
import json

import pytest
import entry


@pytest.mark.parametrize("name", list(entry.TOOL_ENDPOINTS))
@pytest.mark.parametrize("args", [
    {}, {"countries": "US,GB", "count": True},
    {"countries": "Narnia", "dateFrom": "2025-01-01", "dateTo": "2025-03-31"},
])
def test_original_calls_keep_complete_payload_and_one_request(monkeypatch, name, args):
    payload = {
        "success": True,
        "data": [{
            "companyName": "R&amp;D — Example", "companyLogo": "https://example.com/logo.png",
            "descriptionText": "long description " * 100,
            "companyCategories": '["Software", "Software"]',
            "companyWebsite": "https://example.com/", "companyLinkedin": "linkedin.com/company/example",
            "investors": [{"id": "original-investor-id", "name": "Investor"}],
            "sources": [{"url": f"https://example.com/{i}", "isPrimary": i == 4} for i in range(5)],
            "title": "BDR", "jobUrl": "https://example.com/job?a=1&copy;=2",
            "validThrough": "2025-01-01",
        }],
        "pagination": {"totalCount": 1},
        "meta": {"endpoint": entry.TOOL_ENDPOINTS[name].strip("/").replace("/", ".")},
    }
    original = copy.deepcopy(payload)
    calls = []

    async def api(endpoint, params, key):
        calls.append((endpoint, copy.deepcopy(params), key))
        return payload

    monkeypatch.setattr(entry, "_call_api", api)
    result = asyncio.run(entry._handle_jsonrpc({
        "jsonrpc": "2.0", "id": 7, "method": "tools/call",
        "params": {"name": name, "arguments": args},
    }, "test-key"))
    # Exact serialization from d2eb99a's _success_result, not just selected fields.
    assert result == {"jsonrpc": "2.0", "id": 7, "result": {
        "content": [{"type": "text", "text": json.dumps(original, indent=2, default=str)}],
    }}
    assert calls == [(entry.TOOL_ENDPOINTS[name], args, "test-key")]
    assert payload == original


def test_original_person_url_argument_is_advertised_and_forwarded():
    tool = next(t for t in entry.TOOLS if t["name"] == "search_job_change_signals")
    assert tool["inputSchema"]["properties"]["personLinkedinUrl"]["type"] == "string"
    args = {"personLinkedinUrl": "https://linkedin.com/in/example"}
    assert entry._prepare_tool_args(args, tool["name"])[0] == args


def test_opt_ins_are_independent_and_worker_flags_do_not_leak():
    params, verbose, opts = entry._prepare_tool_args({
        "filter_version": 2, "include_expired": False,
        "verbose": False, "by_country": True, "group_by_company": True,
    }, "search_hiring_signals")
    assert params == {"filter_version": 2, "include_expired": False}
    assert verbose is False
    assert opts == {"by_country": True, "group_by_company": True}


def test_grouping_does_not_require_trimming_or_remove_rows():
    payload = {"data": [{"companyName": "Example", "title": "BDR", "companyLogo": "logo"}],
               "meta": {"endpoint": "signals.hiring"}}
    result = json.loads(entry._success_result(payload, group_by_company=True)["content"][0]["text"])
    assert result["data"] == payload["data"]
    assert result["companiesTotal"] == 1
    assert "companies" not in payload


def test_country_breakdowns_are_explicit_on_every_tool():
    for tool in entry.TOOLS:
        assert tool["inputSchema"]["properties"]["by_country"]["default"] is False
