import asyncio
import json
import pytest
import entry
from monitoring_v3 import tools
from mcp_schema import validate
from monitoring_contract import CONTRACT

WRITE_TOOLS = {"create_monitor", "update_monitor", "add_monitor_targets", "remove_monitor_targets"}


def rpc(method, params=None, profile="monitoring_v3"):
    return asyncio.run(entry._handle_jsonrpc({"id": 1, "method": method, "params": params or {}}, "stub-key", profile))


def test_discovery_exposes_the_agreed_tool_set_and_its_own_server_name():
    assert {t["name"] for t in rpc("tools/list")["result"]["tools"]} == {
        "create_monitor", "list_monitors", "get_monitor", "update_monitor",
        "add_monitor_targets", "list_monitor_targets", "remove_monitor_targets"}
    assert rpc("initialize")["result"]["serverInfo"]["name"] == "signalbase-monitoring-v3"


def test_no_tool_deletes_a_monitor_or_touches_a_webhook():
    # Pausing is the reversible stop; webhook secrets must never reach a transcript.
    blob = json.dumps(CONTRACT)
    assert "delete_monitor" not in blob
    for tool in tools():
        assert "webhook" not in json.dumps(tool["inputSchema"]).lower(), tool["name"]
        assert "delete" not in tool["name"]


def test_write_tools_are_advertised_as_writes():
    for tool in tools():
        expected = tool["name"] not in WRITE_TOOLS
        assert tool["annotations"]["readOnlyHint"] is expected, tool["name"]
        # Nothing here is destructive: no monitor is ever deleted.
        assert tool["annotations"]["destructiveHint"] is False


@pytest.mark.parametrize("example", CONTRACT["examples"])
def test_documented_calls_validate_against_real_discovery(example):
    descriptor = next(t for t in tools() if t["name"] == example["name"])
    validate(example["arguments"], descriptor["inputSchema"])


def test_bad_arguments_are_rejected_before_any_write(monkeypatch):
    async def call(*args):
        raise AssertionError("Must not reach the API")
    monkeypatch.setattr(entry, "_call_monitoring_v3", call)
    for arguments in [
        {"name": "x"},                                   # missing signal_types
        {"name": "x", "signal_types": []},               # empty selection
        {"name": "x", "signal_types": ["funding"]},      # not a real signal type
        {"name": "x", "signal_types": ["hiring"], "webhook_url": "https://e.co/h"},  # not accepted here
    ]:
        assert "error" in rpc("tools/call", {"name": "create_monitor", "arguments": arguments})


def test_target_batches_are_capped_below_the_rest_limit(monkeypatch):
    async def call(*args):
        raise AssertionError("Must not reach the API")
    monkeypatch.setattr(entry, "_call_monitoring_v3", call)
    over = {"monitor_id": "mon-1", "targets": [f"d{i}.com" for i in range(101)]}
    assert "error" in rpc("tools/call", {"name": "add_monitor_targets", "arguments": over})
    under = {"monitor_id": "mon-1", "targets": [f"d{i}.com" for i in range(100)]}
    descriptor = next(t for t in tools() if t["name"] == "add_monitor_targets")
    validate(under, descriptor["inputSchema"])


def test_successful_call_forwards_arguments_and_returns_the_payload(monkeypatch):
    calls = []
    async def call(name, arguments, key, operation_id):
        calls.append((name, arguments, key, operation_id))
        return {"success": True, "data": {"execution_status": "succeeded", "monitor": {"id": "mon-1", "name": "Key accounts"}}, "meta": {"creditsUsed": 0}}
    monkeypatch.setattr(entry, "_call_monitoring_v3", call)
    args = {"name": "Key accounts", "signal_types": ["funding_round", "hiring"]}
    result = rpc("tools/call", {"name": "create_monitor", "arguments": args})["result"]
    assert not result["isError"]
    assert calls[0][0] == "create_monitor" and calls[0][1] == args
    payload = json.loads(result["content"][0]["text"])
    assert payload["monitor"]["id"] == "mon-1"
    assert payload["operation_id"] == calls[0][3]


def test_caller_supplied_operation_id_is_used_and_never_forwarded_as_an_argument(monkeypatch):
    # The id is transport metadata (an Idempotency-Key header), not a tool argument.
    seen = {}
    async def call(name, arguments, key, operation_id):
        seen.update(arguments=arguments, operation_id=operation_id)
        return {"success": True, "data": {"execution_status": "succeeded"}, "meta": {}}
    monkeypatch.setattr(entry, "_call_monitoring_v3", call)
    rpc("tools/call", {"name": "list_monitors", "arguments": {"operation_id": "retry-abc12345"}})
    assert seen["operation_id"] == "retry-abc12345"
    assert "operation_id" not in seen["arguments"]


def test_transport_failure_tells_the_agent_to_retry_with_the_same_id(monkeypatch):
    # A lost response on a write is ambiguous; a fresh id would double-apply it.
    async def call(name, arguments, key, operation_id):
        raise RuntimeError("socket closed")
    monkeypatch.setattr(entry, "_call_monitoring_v3", call)
    result = rpc("tools/call", {"name": "create_monitor", "arguments": {"name": "x", "signal_types": ["hiring"]}})["result"]
    assert result["isError"]
    payload = json.loads(result["content"][0]["text"])
    assert payload["execution_status"] == "failed"
    assert "same operation_id" in payload["error"]
    assert payload["operation_id"]


def test_app_errors_surface_their_message_not_a_generic(monkeypatch):
    async def call(name, arguments, key, operation_id):
        return {"success": False, "error": "Monitor not found", "code": "not_found"}
    monkeypatch.setattr(entry, "_call_monitoring_v3", call)
    result = rpc("tools/call", {"name": "get_monitor", "arguments": {"monitor_id": "nope"}})["result"]
    assert result["isError"]
    payload = json.loads(result["content"][0]["text"])
    assert payload["error"] == "Monitor not found" and payload["code"] == "not_found"


def test_unknown_tool_and_method_are_rejected():
    assert "error" in rpc("tools/call", {"name": "delete_monitor", "arguments": {}})
    assert "error" in rpc("nonsense")


def test_guide_resource_carries_concepts_and_examples():
    listed = rpc("resources/list")["result"]["resources"]
    assert listed[0]["uri"] == "signalbase://monitoring/v3/guide"
    text = rpc("resources/read", {"uri": listed[0]["uri"]})["result"]["contents"][0]["text"]
    assert "target_status" in text and "examples" in json.loads(text)
    assert "error" in rpc("resources/read", {"uri": "signalbase://monitoring/v3/nope"})


@pytest.mark.parametrize("path,expected", [
    ("/v3/monitoring", "monitoring_v3"),
    ("/v3/recruiting", "recruiting_v3"),
    ("/v3/recruiting/request", "recruiting_v3_request"),
    ("/v2", "hr"),
    ("", "classic"),
])
def test_monitoring_path_routes_without_disturbing_existing_profiles(monkeypatch, path, expected):
    seen = {}
    async def handler(body, api_key, profile="classic"):
        seen["profile"] = profile
        return {"jsonrpc": "2.0", "id": 1, "result": {}}
    monkeypatch.setattr(entry, "_handle_jsonrpc", handler)

    class Req:
        method = "POST"
        url = f"https://mcp.example{path}"
        headers = type("H", (), {"get": staticmethod(lambda name: "Bearer ff_live_key" if name == "Authorization" else None)})()
        async def text(self):
            return json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    asyncio.run(entry.on_fetch(Req(), None))
    assert seen["profile"] == expected


MONITORING_TOOL_NAMES = {
    "create_monitor",
    "list_monitors",
    "get_monitor",
    "update_monitor",
    "add_monitor_targets",
    "list_monitor_targets",
    "remove_monitor_targets",
}


def test_monitoring_tools_are_served_on_the_chosen_search_profiles():
    # /v2 and /v3/recruiting carry the monitoring tools too, so a customer with
    # one of those connectors does not have to add a second one for monitoring.
    for profile in ("hr", "recruiting_v3"):
        names = {t["name"] for t in rpc("tools/list", profile=profile)["result"]["tools"]}
        assert MONITORING_TOOL_NAMES <= names, profile


def test_host_profiles_append_monitoring_guidance_without_replacing_their_own():
    import entry
    for profile, base, people in (
        ("hr", entry.HR_INSTRUCTIONS, "find_recent_appointments and search_job_change_signals"),
        ("recruiting_v3", None, "search_appointments"),
    ):
        text = rpc("initialize", profile=profile)["result"]["instructions"]
        if base is not None:
            # The profile's own instructions survive verbatim, as a prefix.
            assert text.startswith(base)
        # The four rules that are not already in the tool descriptions.
        assert "before the first write of a conversation" in text
        assert "does not replay signals" in text
        assert "report what each one resolved to" in text
        assert "never tell a user it has failed" in text
        # People data is available on this same connector, so point at it.
        assert people in text
        # Excluded on purpose: the standalone profile's search/monitor boundary.
        assert "not to look things up" not in text


def test_standalone_monitoring_keeps_its_own_instructions():
    text = rpc("initialize", profile="monitoring_v3")["result"]["instructions"]
    assert "not to look things up" in text
    assert "find_recent_appointments" not in text


def test_monitoring_does_not_leak_into_the_other_profiles():
    # Everything else keeps exactly the tools it had: the classic server, the
    # two v2 sub-profiles, and the v3 request adapter.
    for profile in ("classic", "hr_brief", "hr_recruiting", "recruiting_v3_request"):
        names = {t["name"] for t in rpc("tools/list", profile=profile)["result"]["tools"]}
        assert not (names & MONITORING_TOOL_NAMES), profile


def test_hosting_profiles_keep_their_own_search_tools_and_identity():
    # Additive only: the search tools and the server identity are unchanged.
    hr = rpc("tools/list", profile="hr")["result"]["tools"]
    assert {"search_companies", "find_hiring_companies"} <= {t["name"] for t in hr}
    init = rpc("initialize", profile="hr")["result"]
    assert init["serverInfo"]["name"] == "signalbase-hr-mcp"
    v3 = rpc("tools/list", profile="recruiting_v3")["result"]["tools"]
    assert {"search_companies", "get_evidence"} <= {t["name"] for t in v3}
