import asyncio
import json
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from credential_security import (
    CredentialError,
    redact_text,
    request_credentials,
    sanitize,
)

KEY_A = "ff_live_" + "a" * 32
KEY_B = "ff_live_" + "b" * 32
CONNECTOR = f"https://app.test/api/mcp/v3/recruiting/c/{KEY_A}?token=opaque-token"


@pytest.mark.parametrize(
    "value",
    [
        CONNECTOR,
        quote(CONNECTOR, safe=""),
        quote(quote(CONNECTOR, safe=""), safe=""),
        f"Authorization: Bearer {KEY_A}",
        "postgresql://user:privatepassword@fixture.test/db",
    ],
)
def test_redacts_url_header_and_exception_text(value):
    safe = redact_text(value)
    assert (
        KEY_A not in safe
        and "opaque-token" not in safe
        and "privatepassword" not in safe
    )
    assert "REDACTED" in safe


def test_nested_diagnostics_exports_cycles_and_valid_json():
    value = {
        "endpoint": CONNECTOR,
        "headers": {
            "Authorization": "Bearer opaque",
            "X-API-INTERNAL": "internal-value",
        },
        "config": [{"api_key": "api-value", "token": "token-value"}],
        "error": RuntimeError(CONNECTOR),
        "serialized": json.dumps({"token": "serialized-value"}),
    }
    safe = json.dumps(sanitize(value))
    for secret in (
        KEY_A,
        "opaque-token",
        "Bearer opaque",
        "internal-value",
        "api-value",
        "token-value",
        "serialized-value",
    ):
        assert secret not in safe
    assert value["config"][0]["api_key"] == "api-value"
    raw = json.dumps({"url": quote(CONNECTOR + '&name="quoted"', safe="")})
    assert "REDACTED" in json.loads(redact_text(raw))["url"]
    shared = {"name": "Fixture", "id": 1}
    assert sanitize({"a": shared, "b": shared}) == {"a": shared, "b": shared}
    shared["self"] = shared
    assert "Circular" in json.dumps(sanitize(shared))


@pytest.mark.parametrize("authorization", [KEY_A, "Bearer " + KEY_A, "bearer " + KEY_A])
def test_header_legacy_matching_and_encoded_paths(authorization):
    assert request_credentials(authorization, "/v3/recruiting") == (
        KEY_A,
        "/v3/recruiting",
    )
    assert request_credentials(
        authorization, "/v3/recruiting/c/" + KEY_A.replace("_", "%5F")
    ) == (KEY_A, "/v3/recruiting")
    assert request_credentials(None, "/v3/c/" + KEY_A) == (KEY_A, "/v3")


def test_conflicts_and_malformed_paths_never_select_another_authority():
    with pytest.raises(CredentialError) as conflict:
        request_credentials("Bearer " + KEY_B, "/v3/c/" + KEY_A)
    assert conflict.value.status == 400
    for path in ("/v3/c/bad", "/v3/c/" + KEY_A + "%2Fextra", "/unknown/c/" + KEY_A):
        with pytest.raises(CredentialError):
            request_credentials(None, path)
    assert request_credentials(None, "/v3") == ("", "/v3")  # public discovery unchanged


def request(path, method="tools/list", key=None, params=None):
    class Request:
        url = "https://worker.test" + path
        headers = {} if key is None else {"Authorization": key}

        async def text(self):
            return json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
            )

    value = Request()
    value.method = "POST"
    return value


@pytest.fixture
def http_entry(entry_module, monkeypatch):
    class Response:
        @staticmethod
        def new(body, options):
            return SimpleNamespace(body=body, status=options["status"])

    monkeypatch.setattr(entry_module, "Response", Response)
    return entry_module


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/v2",
        "/v2/brief",
        "/v2/recruiting",
        "/v3",
        "/v3/recruiting",
        "/v3/recruiting/request",
        "/v3/monitoring",
    ],
)
def test_every_profile_discovery_preserved_for_header_and_keyed_paths(http_entry, path):
    async def run():
        for method in ("initialize", "tools/list"):
            header = await http_entry.on_fetch(
                request(path, method, "Bearer " + KEY_A), None
            )
            legacy = await http_entry.on_fetch(
                request(path + "/c/" + KEY_A, method), None
            )
            public = await http_entry.on_fetch(request(path, method), None)
            assert header.status == legacy.status == public.status == 200
            assert (
                json.loads(header.body)
                == json.loads(legacy.body)
                == json.loads(public.body)
            )

    asyncio.run(run())


def test_actual_worker_transport_uses_request_key_and_rejects_conflicts_before_fetch(
    http_entry, monkeypatch
):
    calls = []

    async def fetch(url, options):
        key = options["headers"]["Authorization"].removeprefix("Bearer ")
        calls.append({"url": url, "key": key})
        await asyncio.sleep(0)

        class Result:
            async def text(self):
                if key not in (KEY_A, KEY_B):
                    return json.dumps({"success": False, "error": "invalid API key"})
                return json.dumps(
                    {
                        "success": True,
                        "data": {
                            "execution_status": "succeeded",
                            "matches": [{"team": "a" if key == KEY_A else "b"}],
                            "debug": "Authorization: Bearer " + key,
                        },
                        "meta": {"creditsUsed": 0},
                    }
                )

        return Result()

    monkeypatch.setattr(http_entry, "fetch", fetch)
    params = {
        "name": "search_companies",
        "arguments": {
            "request": "Find fixture companies",
            "criteria": {"company": {"domains": ["fixture.test"]}},
            "verify_sources": False,
        },
    }

    async def run():
        responses = await asyncio.gather(
            *(
                http_entry.on_fetch(
                    request("/v3/recruiting", "tools/call", "Bearer " + key, params),
                    SimpleNamespace(API_BASE="http://fixture.test/api/v2"),
                )
                for key in (KEY_A, KEY_B)
            )
        )
        payloads = [
            json.loads(json.loads(response.body)["result"]["content"][0]["text"])
            for response in responses
        ]
        assert [payload["matches"][0]["team"] for payload in payloads] == ["a", "b"]
        assert [call["key"] for call in calls] == [KEY_A, KEY_B]
        assert KEY_A not in str(payloads) and KEY_B not in str(payloads)
        before = len(calls)
        conflict = await http_entry.on_fetch(
            request(
                "/v3/recruiting/c/" + KEY_A, "tools/call", "Bearer " + KEY_B, params
            ),
            None,
        )
        missing = await http_entry.on_fetch(
            request("/v3/recruiting", "tools/call", params=params), None
        )
        assert conflict.status == 400 and len(calls) == before
        assert "API key required" in missing.body
        invalid = await http_entry.on_fetch(
            request("/v3/recruiting", "tools/call", "Bearer invalid", params),
            SimpleNamespace(API_BASE="http://fixture.test/api/v2"),
        )
        assert json.loads(invalid.body)["result"]["isError"]

    asyncio.run(run())


def test_controlled_output_helpers_never_export_secret(http_entry):
    assert KEY_A not in http_entry._json_response({"error": CONNECTOR}).body
    assert KEY_A not in json.dumps(http_entry._error_result(CONNECTOR))
    assert KEY_A not in json.dumps(
        http_entry._success_result({"config": {"token": KEY_A}})
    )


def test_environment_credentials_do_not_redact_continuation_tokens():
    assert sanitize(
        {
            "env": {
                "SIGNALBASE_API_KEY": "opaque-api",
                "SERVICE_ACCESS_TOKEN": "opaque-access",
                "SERVICE_SECRET_KEY": "opaque-secret",
            },
            "continuation_token": "next-page",
            "max_tokens": 100,
        }
    ) == {
        "env": {
            "SIGNALBASE_API_KEY": "[REDACTED]",
            "SERVICE_ACCESS_TOKEN": "[REDACTED]",
            "SERVICE_SECRET_KEY": "[REDACTED]",
        },
        "continuation_token": "next-page",
        "max_tokens": 100,
    }
