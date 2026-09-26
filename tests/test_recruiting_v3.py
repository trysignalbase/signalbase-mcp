import asyncio
import json
import pytest
import entry
from recruiting_v3 import tools, validate
from recruiting_contract import CONTRACT

def test_json_response_preserves_large_schema_numbers_without_js_serialization(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Response body must not pass Python integers through JS JSON.stringify")
    monkeypatch.setattr(entry.JSON, "stringify", forbidden)
    value = {"maximum": 1000000000000000, "company": "Société", "valid": True}
    response = entry._json_response(value)
    assert json.loads(response[0][0]) == value


def rpc(method, params=None):
    return asyncio.run(entry._handle_jsonrpc({"id": 1, "method": method, "params": params or {}}, "stub-key", "recruiting_v3"))


def test_generated_discovery_has_entity_tools_and_scoped_title_lookup():
    # The profile also serves the monitoring tools (see test_monitoring_v3), so
    # assert its own five are intact rather than that nothing else is present.
    names = {t["name"] for t in rpc("tools/list")["result"]["tools"]}
    assert {"search_companies", "search_appointments", "search_investor_activity", "get_evidence", "get_recruiting_options"} <= names
    assert not (names - {"search_companies", "search_appointments", "search_investor_activity", "get_evidence", "get_recruiting_options"} - {t["name"] for t in entry._monitoring_tools()})
    assert rpc("initialize")["result"]["serverInfo"]["name"] == "signalbase-recruiting-v3"
    resource = rpc("resources/read", {"uri": "signalbase://recruiting/v3/guide"})
    assert "examples" in resource["result"]["contents"][0]["text"]


@pytest.mark.parametrize("example", CONTRACT["examples"])
def test_documented_calls_validate_against_real_discovery(example):
    descriptor = next(t for t in tools() if t["name"] == example["name"])
    validate(example["arguments"], descriptor["inputSchema"])


def test_transport_keeps_nested_criteria_and_result_evidence(monkeypatch):
    calls = []
    async def call(name, arguments, key, operation_id):
        calls.append((name, arguments, key, operation_id))
        return {"success": True, "data": {"execution_status": "succeeded", "alternatives": [{"name": "Synthetic company", "missing": ["role title"], "id": "synthetic"}]}, "meta": {"creditsUsed": 1}}
    monkeypatch.setattr(entry, "_call_recruiting_v3", call)
    args = CONTRACT["examples"][0]["arguments"]
    result = rpc("tools/call", {"name": "search_companies", "arguments": args})["result"]
    assert not result["isError"]
    assert calls[0][1] == args
    assert json.loads(result["content"][0]["text"])["alternatives"][0]["id"] == "synthetic"


def test_invalid_nested_calls_are_rejected_before_io(monkeypatch):
    async def call(*args):
        raise AssertionError("Must not call API")
    monkeypatch.setattr(entry, "_call_recruiting_v3", call)
    result = rpc("tools/call", {"name": "search_companies", "arguments": {"request": "BDRs", "criteria": {"hiring": {"roles": [5]}}}})
    assert result["error"]["code"] == -32602


def test_transport_failure_has_reusable_operation_id_and_unknown_cost(monkeypatch):
    async def call(*args):
        raise TimeoutError()
    monkeypatch.setattr(entry, "_call_recruiting_v3", call)
    result = rpc("tools/call", {"name": "search_companies", "arguments": CONTRACT["examples"][0]["arguments"]})["result"]
    payload = json.loads(result["content"][0]["text"])
    assert result["isError"] and payload["operation_id"]
    assert payload["usage"]["credits_known"] is False


def test_request_profile_accepts_original_request_without_business_filters(monkeypatch):
    calls=[]
    async def call(name,args,key,operation_id,request_adapter=False):
        calls.append((args,request_adapter))
        return {"success":True,"data":{"execution_status":"succeeded","matches":[{"id":"fixture"}]}}
    monkeypatch.setattr(entry,"_call_recruiting_v3",call)
    response=asyncio.run(entry._handle_jsonrpc({"id":3,"method":"tools/call","params":{"name":"search_companies","arguments":{"request":"Small companies hiring SDRs in Dubai"}}},"stub-key","recruiting_v3_request"))
    assert not response["result"]["isError"]
    assert calls==[({"request":"Small companies hiring SDRs in Dubai"},True)]


def test_new_criteria_cannot_be_added_to_the_request_profile():
    response=asyncio.run(entry._handle_jsonrpc({"id":3,"method":"tools/call","params":{"name":"search_companies","arguments":{"request":"Find employers","criteria":{}}}},"stub-key","recruiting_v3_request"))
    assert response["error"]["code"]==-32602


def test_bound_violations_name_the_limit_and_the_given_size():
    evidence = next(tool for tool in tools() if tool["name"] == "get_evidence")
    records = [{"kind": "company", "id": f"00000000-0000-4000-8000-{i:012d}"} for i in range(11)]
    with pytest.raises(ValueError) as excinfo:
        validate({"records": records}, evidence["inputSchema"])
    message = str(excinfo.value)
    assert "arguments.records" in message and "11 items given" in message
    assert "at most 10" in message and "Split the list" in message
    search = next(tool for tool in tools() if tool["name"] == "search_companies")
    with pytest.raises(ValueError) as excinfo:
        validate({"request": "x" * 4001, "criteria": {"hiring": {}}}, search["inputSchema"])
    assert "characters given" in str(excinfo.value) and "at most" in str(excinfo.value)
