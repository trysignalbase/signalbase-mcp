import asyncio
import json
import pytest
import entry


@pytest.mark.parametrize("name,args", [
    ("search_investor_activity", {"request": "YC investors with cheques up to $500K", "criteria": {}, "investor_names": ["YC"], "ticket_size": {"max_usd": 500000, "unknown": "review"}}),
    ("search_acquisitions", {"request": "Acquired companies now hiring SDRs", "party": "target", "criteria": {"hiring": {"roles": ["SDR"]}}, "announced": {"within_days": 60}}),
])
def test_sourcing_criteria_survive_worker_transport(monkeypatch, name, args):
    calls = []
    async def call(tool, arguments, key, operation_id):
        calls.append((tool, arguments))
        return {"success": True, "data": {"execution_status": "succeeded", "matches": []}, "meta": {"creditsUsed": 1}}
    monkeypatch.setattr(entry, "_call_recruiting_v3", call)
    result = asyncio.run(entry._handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}, "synthetic-fixture-key", "recruiting_v3"))
    assert not result["result"]["isError"]
    assert calls == [(name, args)]
    assert json.loads(result["result"]["content"][0]["text"])["execution_status"] == "succeeded"
