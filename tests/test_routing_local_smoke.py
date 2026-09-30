"""Opt-in JSON-RPC -> real Worker API transport -> disposable app smoke.

Only the Cloudflare JS fetch primitive is adapted to CPython HTTP; dispatch,
contract header, serialization and app handlers run unchanged.
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


@pytest.mark.skipif(os.getenv("GEORGI_ROUTING_SMOKE") != "1", reason="Explicit disposable app opt-in")
def test_generated_routing_posting_through_mcp(monkeypatch):
    root = Path(os.environ["GEORGI_ROUTING_ARTIFACTS"])
    request = json.loads((root / "search-request.json").read_text(encoding="utf-8"))
    calls = []

    async def fetch(url, options):
        parsed = urlparse(url)
        assert parsed.hostname == "127.0.0.1" and parsed.port == 56435
        assert parsed.path == "/api/v3/recruiting/search-companies"
        calls.append({"url": url, "contract_hash": options["headers"]["X-Recruiting-Contract"]})
        req = urllib.request.Request(url, data=options["body"].encode(), headers=options["headers"], method="POST")
        with urllib.request.urlopen(req, timeout=40) as response:
            body = response.read(4_000_001).decode()
        class Response:
            async def text(self):
                return body
        return Response()

    monkeypatch.setattr(entry, "fetch", fetch)
    monkeypatch.setattr(entry, "_api_base_override", "http://127.0.0.1:56435/api/v2")

    async def run():
        listed = await entry._handle_jsonrpc({"jsonrpc":"2.0","id":1,"method":"tools/list"}, "synthetic-routing-key", "recruiting_v3")
        assert any(t["name"] == "search_companies" for t in listed["result"]["tools"])
        response = await entry._handle_jsonrpc({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search_companies","arguments":request}}, "synthetic-routing-key", "recruiting_v3")
        assert response["result"]["isError"] is False, response
        payload = json.loads(response["result"]["content"][0]["text"])
        assert len(payload["matches"]) == 1, payload
        assert payload["matches"][0]["domain"] == "routing.test", payload
        assert any(job["title"] == "Senior Software Engineer" for job in payload["matches"][0]["jobs"])
        (root / "worker-mcp-smoke.json").write_text(json.dumps({"scope":"local JSON-RPC dispatcher and real Worker HTTP transport; Cloudflare fetch shim only","production_calls":0,"calls":calls,"response":response},indent=2),encoding="utf-8")
    asyncio.run(run())
