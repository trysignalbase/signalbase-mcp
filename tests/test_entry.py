"""Unit tests for src/entry.py (pure-Python parts; JS runtime is stubbed in conftest)."""

import asyncio
import json

import pytest

import entry  # loaded by conftest.py from src/entry.py


def _rpc(method, params=None, api_key="test-key", req_id=1):
    body = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        body["params"] = params
    return asyncio.run(entry._handle_jsonrpc(body, api_key))


def _tool(name):
    return next(t for t in entry.TOOLS if t["name"] == name)


def _props(name):
    return _tool(name)["inputSchema"]["properties"]


# ──────────────────────────────────────────────────────────────
# _build_query_string / _url_encode
# ──────────────────────────────────────────────────────────────

def test_build_query_string_bools_none_and_lists():
    qs = entry._build_query_string({
        "count": True,
        "include_expired": False,
        "skip": None,
        "countries": ["SE", "NO"],
        "limit": 50,
    })
    assert qs == "count=true&include_expired=false&countries=SE%2CNO&limit=50"


def test_build_query_string_empty():
    assert entry._build_query_string({}) == ""
    assert entry._build_query_string({"a": None}) == ""


def test_url_encode():
    assert entry._url_encode("abc-_.~09") == "abc-_.~09"
    assert entry._url_encode("a b") == "a%20b"
    assert entry._url_encode("a&b=c+d|e,f") == "a%26b%3Dc%2Bd%7Ce%2Cf"
    assert entry._url_encode("é") == "%C3%A9"


# ──────────────────────────────────────────────────────────────
# tools/call pre-processing: verbose stripped, lists joined
# ──────────────────────────────────────────────────────────────

def test_prepare_tool_args_pops_verbose_and_joins_lists():
    params, verbose = entry._prepare_tool_args({
        "verbose": True,
        "countries": ["SE", "NO", "DK"],
        "company_domain": ("a.com", "b.com"),
        "limit": 10,
    })
    assert verbose is True
    assert "verbose" not in params
    assert params == {"countries": "SE,NO,DK", "company_domain": "a.com,b.com", "limit": 10}


def test_prepare_tool_args_verbose_string_and_default():
    assert entry._prepare_tool_args({"verbose": "true"})[1] is True
    assert entry._prepare_tool_args({"verbose": "false"})[1] is False
    assert entry._prepare_tool_args({})[1] is False
    assert entry._prepare_tool_args(None) == ({}, False)


def test_tools_call_strips_verbose_before_call_api(monkeypatch):
    captured = {}

    async def fake_call_api(endpoint, params, api_key):
        captured["endpoint"] = endpoint
        captured["params"] = params
        captured["api_key"] = api_key
        return {"success": True, "data": [{"companyName": "X", "companyLogo": "http://logo"}]}

    monkeypatch.setattr(entry, "_call_api", fake_call_api)

    resp = _rpc("tools/call", {
        "name": "search_hiring_signals",
        "arguments": {"verbose": True, "countries": ["SE", "NO"], "count": True},
    })

    assert captured["endpoint"] == "/signals/hiring"
    assert captured["api_key"] == "test-key"
    assert "verbose" not in captured["params"]
    assert captured["params"]["countries"] == "SE,NO"
    assert captured["params"]["count"] is True
    # verbose=true → untrimmed, indented payload
    text = resp["result"]["content"][0]["text"]
    assert "\n" in text
    payload = json.loads(text)
    assert "_meta" not in payload
    assert payload["data"][0]["companyLogo"] == "http://logo"


def test_tools_call_default_is_trimmed_compact(monkeypatch):
    async def fake_call_api(endpoint, params, api_key):
        return {"success": True, "data": [{"companyName": "X", "companyLogo": "http://logo"}]}

    monkeypatch.setattr(entry, "_call_api", fake_call_api)
    resp = _rpc("tools/call", {"name": "search_funding_signals", "arguments": {"limit": 1}})
    text = resp["result"]["content"][0]["text"]
    assert "\n" not in text
    payload = json.loads(text)
    assert payload["_meta"] == {"trimmed": True, "hint": "pass verbose=true for full text"}
    assert "companyLogo" not in payload["data"][0]


def test_tools_call_api_error_is_surfaced(monkeypatch):
    async def fake_call_api(endpoint, params, api_key):
        return {"error": True, "status": 400, "body": {"error": "Unknown query parameter: foo"}}

    monkeypatch.setattr(entry, "_call_api", fake_call_api)
    resp = _rpc("tools/call", {"name": "search_companies", "arguments": {"foo": 1}})
    assert resp["result"]["isError"] is True
    assert "HTTP 400" in resp["result"]["content"][0]["text"]
    assert "Unknown query parameter" in resp["result"]["content"][0]["text"]


def test_tools_call_without_api_key():
    resp = _rpc("tools/call", {"name": "search_companies", "arguments": {}}, api_key="")
    assert resp["result"]["isError"] is True
    assert "No API key" in resp["result"]["content"][0]["text"]


# ──────────────────────────────────────────────────────────────
# _trim_response
# ──────────────────────────────────────────────────────────────

def test_trim_response_truncates_drops_and_keeps():
    long_text = "x" * 500
    data = {
        "success": True,
        "data": [{
            "descriptionText": long_text,
            "companyDescription": long_text,
            "description": long_text,
            "postContent": long_text,
            "personHeadline": long_text,
            "shortDescription": "short",
            "companyLogo": "http://l1",
            "companyLogoUrl": "http://l2",
            "logoUrl": "http://l3",
            "logo_url": "http://l4",
            "image": "http://l5",
            "jobUrl": "https://www.linkedin.com/jobs/view/1",
            "sources": ["https://a", "https://b"],
            "companyLinkedin": "https://www.linkedin.com/company/x",
            "personLinkedinUrl": "https://www.linkedin.com/in/y",
            "companyWebsite": "https://x.com",
            "validThrough": "2026-12-31",
            "nested": {"logoUrl": "http://l6", "description": long_text},
        }],
        "pagination": {"totalCount": 1},
    }
    out = entry._trim_response(data)
    row = out["data"][0]
    for f in ("descriptionText", "companyDescription", "description", "postContent", "personHeadline"):
        assert len(row[f]) == 301
        assert row[f].endswith("…")
        assert row[f][:300] == "x" * 300
    assert row["shortDescription"] == "short"
    for f in ("companyLogo", "companyLogoUrl", "logoUrl", "logo_url", "image"):
        assert f not in row
    assert row["jobUrl"] == "https://www.linkedin.com/jobs/view/1"
    assert row["sources"] == ["https://a", "https://b"]
    assert row["companyLinkedin"] == "https://www.linkedin.com/company/x"
    assert row["personLinkedinUrl"] == "https://www.linkedin.com/in/y"
    assert row["companyWebsite"] == "https://x.com"
    assert row["validThrough"] == "2026-12-31"
    assert "logoUrl" not in row["nested"]
    assert row["nested"]["description"].endswith("…")
    assert out["pagination"] == {"totalCount": 1}
    assert out["_meta"] == {"trimmed": True, "hint": "pass verbose=true for full text"}
    # original untouched
    assert data["data"][0]["companyLogo"] == "http://l1"


def test_trim_response_short_text_untouched():
    out = entry._trim_response({"data": [{"description": "x" * 300}]})
    assert out["data"][0]["description"] == "x" * 300


def test_success_result_modes():
    data = {"data": [{"description": "y" * 400, "logoUrl": "z"}]}
    compact = entry._success_result(data)["content"][0]["text"]
    verbose = entry._success_result(data, verbose=True)["content"][0]["text"]
    assert "\n" not in compact and "_meta" in compact and "logoUrl" not in compact
    assert "\n" in verbose and "_meta" not in verbose and "logoUrl" in verbose
    assert len(compact) < len(verbose)


# ──────────────────────────────────────────────────────────────
# tools/list schema
# ──────────────────────────────────────────────────────────────

def test_tools_list_returns_six_tools():
    resp = _rpc("tools/list")
    names = [t["name"] for t in resp["result"]["tools"]]
    assert names == [
        "search_funding_signals", "search_acquisition_signals",
        "search_job_change_signals", "search_hiring_signals",
        "search_investors", "search_companies",
    ]


def test_tools_list_is_json_serialisable():
    json.dumps({"tools": entry.TOOLS})


def test_subcategories_has_no_enum_and_lists_values():
    for tool in ("search_funding_signals", "search_acquisition_signals",
                 "search_hiring_signals", "search_companies"):
        prop = _props(tool)["subcategories"]
        assert "enum" not in prop, tool
        assert prop["type"] == "string"
        assert "ai" in prop["description"] and "fintech" in prop["description"]


def test_every_tool_has_count_and_verbose():
    for t in entry.TOOLS:
        props = t["inputSchema"]["properties"]
        assert props["count"]["type"] == "boolean", t["name"]
        assert props["verbose"]["type"] == "boolean", t["name"]
        assert "free" in props["count"]["description"].lower()


def test_funding_schema_new_keys():
    p = _props("search_funding_signals")
    for k in ("employee_count_min", "employee_count_max", "founded_year_min", "founded_year_max",
              "company_domain", "company_linkedin_url", "exclude_countries", "amount_min",
              "amount_max", "round", "count", "verbose"):
        assert k in p, k
    assert p["employee_count_max"]["type"] == "integer"
    assert "50" in p["company_domain"]["description"]
    assert "NORDICS" in p["countries"]["description"] and "DACH" in p["countries"]["description"]


def test_acquisitions_schema_new_keys():
    p = _props("search_acquisition_signals")
    for k in ("employee_count_min", "employee_count_max", "company_domain",
              "company_linkedin_url", "exclude_countries", "count", "verbose"):
        assert k in p, k
    assert "round" not in p


def test_job_changes_schema_new_keys():
    p = _props("search_job_change_signals")
    for k in ("countries", "exclude_countries", "company_domain", "company_linkedin_url",
              "person_linkedin_url", "new_role", "dateFrom", "dateTo", "date_preset",
              "sort_by", "sort_order", "count", "verbose"):
        assert k in p, k
    assert "personLinkedinUrl" not in p


def test_hiring_schema_new_keys():
    p = _props("search_hiring_signals")
    for k in ("job_countries", "company_countries", "exclude_countries", "company_domain",
              "company_linkedin_url", "company_name", "include_expired", "team_size",
              "count", "verbose"):
        assert k in p, k
    assert p["include_expired"]["type"] == "boolean"
    assert p["include_expired"]["default"] is False
    assert "HQ" in p["countries"]["description"]
    assert "1-10" in p["team_size"]["description"]
    assert p["limit"]["maximum"] == 100


def test_investors_and_companies_schema_new_keys():
    inv = _props("search_investors")
    for k in ("exclude_countries", "type", "headquarters", "ticket_size_min",
              "ticket_size_max", "count", "verbose"):
        assert k in inv, k
    comp = _props("search_companies")
    for k in ("exclude_countries", "categories", "subcategories", "domain", "linkedin_url",
              "employee_count_min", "employee_count_max", "count", "verbose"):
        assert k in comp, k


# ──────────────────────────────────────────────────────────────
# initialize / ping / errors / prompts
# ──────────────────────────────────────────────────────────────

def test_initialize():
    resp = _rpc("initialize", {"protocolVersion": "2025-03-26"})
    result = resp["result"]
    assert result["protocolVersion"] == entry.PROTOCOL_VERSION
    assert result["serverInfo"] == {"name": "signalbase-mcp", "version": "1.1.0"}
    assert "count=true` is free" in result["instructions"] or "count=true is free" in result["instructions"].replace("`", "")
    assert "boolean as string" not in result["instructions"].lower()
    assert "84%" in result["instructions"]
    assert "include_expired" in result["instructions"]


def test_ping():
    resp = _rpc("ping")
    assert resp == {"jsonrpc": "2.0", "id": 1, "result": {}}


def test_notifications_initialized_returns_none():
    assert _rpc("notifications/initialized") is None


def test_unknown_method():
    resp = _rpc("no/such")
    assert resp["error"]["code"] == -32601


def test_unknown_tool():
    resp = _rpc("tools/call", {"name": "nope", "arguments": {}})
    assert resp["error"]["code"] == -32602


def test_unknown_prompt():
    resp = _rpc("prompts/get", {"name": "nope"})
    assert resp["error"]["code"] == -32602


def test_prompts_list_has_funded_and_hiring():
    resp = _rpc("prompts/list")
    names = [p["name"] for p in resp["result"]["prompts"]]
    assert "funded-and-hiring" in names
    prompt = next(p for p in resp["result"]["prompts"] if p["name"] == "funded-and-hiring")
    arg_names = [a["name"] for a in prompt["arguments"]]
    assert arg_names == ["geography", "max_employees", "department", "window"]
    assert all(a["required"] is False for a in prompt["arguments"])


def test_prompts_get_funded_and_hiring_defaults():
    resp = _rpc("prompts/get", {"name": "funded-and-hiring", "arguments": {}})
    text = resp["result"]["messages"][0]["content"]["text"]
    assert resp["result"]["messages"][0]["role"] == "user"
    assert "countries=EU" in text
    assert "employee_count_max=10" in text
    assert "date_preset=last_90d" in text
    assert "departments=sales" in text
    assert "count=true" in text
    assert "company_domain=<up to 50" in text
    assert "limit=100" in text and "sort_by=date_posted" in text
    assert "company_countries=EU" in text
    assert "team_size=1-10" in text
    assert "jobUrl" in text and "validThrough" in text


def test_prompts_get_funded_and_hiring_custom_args():
    resp = _rpc("prompts/get", {"name": "funded-and-hiring", "arguments": {
        "geography": "NORDICS", "max_employees": "50", "department": "engineering", "window": "last_30d",
    }})
    text = resp["result"]["messages"][0]["content"]["text"]
    assert "countries=NORDICS" in text
    assert "employee_count_max=50" in text
    assert "date_preset=last_30d" in text
    assert "departments=engineering" in text
    assert "team_size=1-10,11-50" in text


def test_team_size_for_max():
    assert entry._team_size_for_max(10) == "1-10"
    assert entry._team_size_for_max("50") == "1-10,11-50"
    assert entry._team_size_for_max(200) == "1-10,11-50,51-200"
    assert entry._team_size_for_max(5000) == "1-10,11-50,51-200,201-1000,1000-plus"
    assert entry._team_size_for_max("abc") == "1-10"


class _Env:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_api_base_override_from_env():
    assert entry._resolve_api_base(None) == entry.API_BASE
    assert entry._resolve_api_base(_Env()) == entry.API_BASE
    assert (
        entry._resolve_api_base(_Env(API_BASE="http://localhost:3000/api/v2/"))
        == "http://localhost:3000/api/v2"
    )
