"""Prevent tools/list from advertising REST arguments the companion app rejects."""
import json
from pathlib import Path
import entry


def test_every_advertised_raw_tool_argument_has_an_api_or_worker_handler():
    contract = json.loads((Path(__file__).parent / "fixtures" / "api-contract.json").read_text("utf8"))
    routes = {r["path"].removeprefix("/api/v2"): set(r["query_parameters"]) for r in contract["routes"]}
    worker_only = {"role", "headcount_min", "headcount_max", "country_scope", "verbose", "group_by_company", "by_country", "sector"}
    for profile in ("classic", "hr"):
        for tool in entry._tools_for_profile(profile):
            endpoint = entry.TOOL_ENDPOINTS.get(tool["name"])
            if endpoint:
                assert set(tool["inputSchema"]["properties"]) <= routes[endpoint] | worker_only, tool["name"]


def test_hiring_workflow_params_match_exported_api_contract():
    contract = json.loads((Path(__file__).parent / "fixtures" / "api-contract.json").read_text("utf8"))
    route = next(r for r in contract["routes"] if r["path"] == "/api/v2/signals/hiring")
    params = entry._wf_hiring_params({
        "role": "bdr or engineers", "job_locations": ["US", "Dubai"],
        "company_countries": ["EU"], "exclude_company_countries": ["PL"],
        "headcount_max": 9, "posting_age_days_min": 31, "min_distinct_role_titles": 2,
        "funding_investor_type": "vc", "funding_rounds": ["Seed"],
        "work_mode": "remote", "description_keywords": "founder", "as_of": "2026-09-10",
    }, funded=True)
    assert set(params) <= set(route["query_parameters"])
