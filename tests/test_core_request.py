import asyncio
import json

import pytest
import entry
from recruiting_contract import CONTRACT, REQUEST_CONTRACT
from recruiting_v3 import tools


def rpc(method, params=None, profile="v3"):
    return asyncio.run(entry._handle_jsonrpc({"id": 1, "method": method, "params": params or {}}, "fixture-key", profile))


def test_core_schema_guide_and_retained_union():
    core = {t["name"]: t for t in rpc("tools/list")["result"]["tools"]}
    request = {t["name"]: t for t in tools(True)}
    assert core == {**request, **{t["name"]: t for t in [entry._v3_people_tool(), entry._v3_collect_people_tool(), *entry._monitoring_tools(), *entry._agent_tools()]}}
    assert rpc("initialize")["result"]["serverInfo"] == {"name": "signalbase-v3", "version": "2.1.0"}
    guide = json.loads(rpc("resources/read", {"uri": "signalbase://recruiting/v3/guide"})["result"]["contents"][0]["text"])
    assert guide["examples"] == REQUEST_CONTRACT["examples"]
    assert len(rpc("resources/list")["result"]["resources"]) == 3
    for alias in ("recruiting_v3", "monitoring_v3"):
        actual = {t["name"]: t for t in rpc("tools/list", profile=alias)["result"]["tools"]}
        for tool in tools(False):
            assert actual[tool["name"]] == tool


@pytest.mark.parametrize("name", ["search_companies", "find_hiring_outlook", "search_appointments", "search_acquisitions", "search_investor_activity"])
def test_core_search_uses_actual_request_transport_and_preserves_retry_identity(monkeypatch, name):
    calls = []
    class Response:
        status = 200
        async def text(self):
            return json.dumps({"success": True, "data": {"execution_status": "succeeded", "matches": []}, "meta": {"creditsUsed": 1}})
    async def fetch(url, options):
        calls.append((url, options))
        return Response()
    monkeypatch.setattr(entry, "fetch", fetch)
    monkeypatch.setattr(entry, "_api_base_override", "https://fixture.test/api/v2")
    args = {"request": "Find companies headquartered in Hungary", "limit": 1, "verify_sources": False, "operation_id": "core-fixture-operation"}
    result = rpc("tools/call", {"name": name, "arguments": args})
    assert not result["result"]["isError"]
    url, options = calls.pop()
    assert url == "https://fixture.test/api/v3/recruiting/request/" + name.replace("_", "-")
    assert options["headers"]["X-Recruiting-Contract"] == REQUEST_CONTRACT["contract_hash"]
    assert options["headers"]["Idempotency-Key"] == args["operation_id"]
    assert json.loads(options["body"]) == {k: v for k, v in args.items() if k != "operation_id"}


def test_cached_structured_core_call_fails_before_transport(monkeypatch):
    async def forbidden(*args):
        raise AssertionError("Stale schema must never reach paid transport")
    monkeypatch.setattr(entry, "fetch", forbidden)
    result = rpc("tools/call", {"name": "search_companies", "arguments": {**CONTRACT["examples"][0]["arguments"], "operation_id": "old-uncertain-operation"}})
    assert result["error"]["code"] == -32602
    assert "same operation_id" in result["error"]["message"]
