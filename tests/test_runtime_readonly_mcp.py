"""Opt-in actual Worker JSON-RPC/transport to local app with production read-only SQL.

The CPython fetch adapter is the only Worker transport substitution. The app
replaces authentication/accounting with synthetic local boundaries, explicitly.
"""
import asyncio
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import urlparse

import pytest
import entry
from recruiting_contract import CONTRACT


@pytest.mark.skipif(os.getenv("GEORGI_RUNTIME_MCP") != "1", reason="Explicit authorized read-only runtime target required")
def test_actual_v3_flow_against_readonly_sql(monkeypatch):
    source = json.loads(Path(os.environ["GEORGI_RUNTIME_CASES_JSON"]).read_text(encoding="utf-8-sig"))
    calls, records = [], []

    async def fetch(url, options):
        target = urlparse(url)
        assert target.hostname == "127.0.0.1" and target.port == 56437
        assert target.path.startswith("/api/v3/recruiting/")
        assert options["headers"]["X-Recruiting-Contract"] == CONTRACT["contract_hash"]
        calls.append({"url": url, "contract_hash": options["headers"]["X-Recruiting-Contract"]})
        req = urllib.request.Request(url, data=options["body"].encode(), headers=options["headers"], method="POST")
        try:
            response = urllib.request.urlopen(req, timeout=45)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read(200001)
        assert len(raw) <= 200000
        class Response:
            status = response.status
            async def text(self):
                return raw.decode("utf-8")
        return Response()

    monkeypatch.setattr(entry, "fetch", fetch)
    monkeypatch.setattr(entry, "_api_base_override", "http://127.0.0.1:56437/api/v2")

    async def run():
        discovery = await entry._handle_jsonrpc({"id": 1, "method": "tools/list"}, "synthetic-readonly-key", "recruiting_v3")
        assert "find_hiring_outlook" in {t["name"] for t in discovery["result"]["tools"]}
        for case in source["records"]:
            arguments = case["input"]
            tool = "find_hiring_outlook" if case["id"] == "europe-outlook" else case["tool"]
            if tool == "find_hiring_outlook":
                arguments["criteria"]["outlook"]["mode"] = "signals"
            response = await entry._handle_jsonrpc({"id": len(records)+2, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}, "synthetic-readonly-key", "recruiting_v3")
            records.append({"case": case["id"], "request_status": "reconstructed_not_original", "tool": tool, "response": response})
        Path(os.environ["GEORGI_RUNTIME_WORKER_OUTPUT"]).write_text(json.dumps({"scope": "Actual local v3 dispatcher and HTTP transport; CPython fetch adapter; app synthetic auth/billing and real production read-only SQL", "production_api_calls": 0, "provider_calls": 0, "contract_hash": CONTRACT["contract_hash"], "calls": calls, "records": records}, indent=2), encoding="utf-8")
        assert len(calls) == len(records) == 6
        for record in records:
            assert "error" not in record["response"], record
            payload = json.loads(record["response"]["result"]["content"][0]["text"])
            assert payload.get("semantic_version") == CONTRACT["semantic_version"], record
            assert payload.get("api_usage", {}).get("creditsUsed") == 0, record
            assert all(group in payload for group in ("matches", "prospects", "alternatives", "review_items")), record
    try:
        asyncio.run(run())
    finally:
        req = urllib.request.Request("http://127.0.0.1:56437/__finish", data=b"", headers={"authorization": "Bearer synthetic-readonly-key"}, method="POST")
        with urllib.request.urlopen(req, timeout=5):
            pass
