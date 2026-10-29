import asyncio
import json
import pytest
import entry
from agents_contract import CONTRACT
from agents_v3 import handle, tools


def rpc(method, params=None, profile="v3"):
    return asyncio.run(entry._handle_jsonrpc({"id": 1, "method": method, "params": params or {}}, "fixture-key", profile))


@pytest.mark.parametrize("profile", ["v3", "recruiting_v3", "recruiting_v3_request", "monitoring_v3"])
def test_agents_discovered_with_existing_tools_and_guide(profile):
    found = {t["name"]: t for t in rpc("tools/list", profile=profile)["result"]["tools"]}
    for tool in tools():
        assert found[tool["name"]] == tool
        write = tool["name"] not in {"list_research_agents", "get_research_agent"}
        assert tool["annotations"]["readOnlyHint"] is not write
        assert ("operation_id" in tool["inputSchema"].get("required", [])) is write
    guides = rpc("resources/list", profile=profile)["result"]["resources"]
    assert any(r["uri"] == "signalbase://agents/v3/guide" for r in guides)
    assert guides[0]["uri"] == ("signalbase://monitoring/v3/guide" if profile == "monitoring_v3" else "signalbase://recruiting/v3/guide")
    guide = rpc("resources/read", {"uri": "signalbase://agents/v3/guide"}, profile)["result"]["contents"][0]
    assert json.loads(guide["text"])["semantic_version"] == "1.0.0"
    assert "create_research_agent" in rpc("initialize", profile=profile)["result"]["instructions"]


def test_legacy_profiles_do_not_acquire_agent_write_tools():
    for profile in ["classic", "hr", "hr_brief", "hr_recruiting"]:
        names = {t["name"] for t in rpc("tools/list", profile=profile)["result"]["tools"]}
        assert not names.intersection(t["name"] for t in tools())


def test_write_identity_required_before_transport_and_no_key_leak():
    called = []
    async def call(*args):
        called.append(args)
        raise RuntimeError("secret")
    body = {"id": 1, "method": "tools/call", "params": {"name": "create_research_agent", "arguments": {"prompt": "Find companies headquartered in Hungary", "cadence": "week"}}}
    response = asyncio.run(handle(body, "fixture-key", call))
    assert response["error"]["code"] == -32602
    assert not called
    body["params"]["arguments"]["operation_id"] = "caller-stable-creation-01"
    response = asyncio.run(handle(body, "fixture-key", call))
    value = json.loads(response["result"]["content"][0]["text"])
    assert value["operation_id"] == "caller-stable-creation-01"
    assert "same operation_id" in value["error"]
    assert "secret" not in json.dumps(value)
    assert "operation_id" not in called[0][1]
    assert body["params"]["arguments"]["operation_id"] == "caller-stable-creation-01"


@pytest.mark.parametrize("name,args", [
    ("create_research_agent", {"prompt": "Find companies headquartered in Hungary", "cadence": "week"}),
    ("list_research_agents", {}),
    ("get_research_agent", {"id": "one"}),
    ("update_research_agent", {"id": "one", "revision": 1, "cadence": "24_hours"}),
    ("set_research_agent_paused", {"id": "one", "revision": 1, "paused": True}),
    ("run_research_agent", {"id": "one"}),
])
def test_actual_http_adapter_preserves_identity_and_contract(monkeypatch, name, args):
    calls = []
    class Response:
        status = 200
        async def text(self):
            return json.dumps({"success": True, "data": {"execution_status": "succeeded", "state": "queued"}, "meta": {"creditsUsed": 0}})
    async def fetch(url, options):
        calls.append((url, options))
        return Response()
    monkeypatch.setattr(entry, "fetch", fetch)
    monkeypatch.setattr(entry, "_api_base_override", "https://fixture.test/api/v2")
    result = rpc("tools/call", {"name": name, "arguments": {**args, "operation_id": "caller-stable-request-01"}})
    assert not result["result"]["isError"]
    url, options = calls[0]
    assert url == "https://fixture.test/api/v3/agents/" + name.replace("_", "-")
    assert options["headers"]["Idempotency-Key"] == "caller-stable-request-01"
    assert options["headers"]["X-Agents-Contract"] == CONTRACT["contract_hash"]
    assert "operation_id" not in json.loads(options["body"])
    assert json.loads(result["result"]["content"][0]["text"])["api_usage"]["creditsUsed"] == 0
