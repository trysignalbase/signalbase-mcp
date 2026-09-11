import asyncio
import json

import pytest
import entry


def envelope(rows=None, total=None, more=False, paid=True):
    rows = rows or []
    return {"success": True, "data": rows, "pagination": {"totalCount": len(rows) if total is None else total, "hasNextPage": more}, "meta": {"creditsUsed": int(paid)}}


def call(name, arguments):
    response = asyncio.run(entry._handle_jsonrpc({"id": 3, "method": "tools/call", "params": {"name": name, "arguments": arguments}}, "key", "hr"))
    result = response["result"]
    assert not result.get("isError"), result
    return json.loads(result["content"][0]["text"])


def test_workflows_are_hr_only():
    classic = {t["name"] for t in entry._tools_for_profile("classic")}
    hr = {t["name"] for t in entry._tools_for_profile("hr")}
    assert hr - classic == {"find_hiring_companies", "find_funded_hiring_companies", "find_hiring_outlook", "research_investor_activity"}
    response = asyncio.run(entry._handle_jsonrpc({"id": 1, "method": "tools/call", "params": {"name": "find_hiring_companies"}}, "key"))
    assert response["error"]["code"] == -32602


def test_funded_hiring_is_one_joined_query_and_keeps_evidence(monkeypatch):
    calls = []
    funding = {"signalId": "f1", "roundType": "seed", "sources": ["https://a.com/news"]}

    async def api(endpoint, params, key):
        calls.append((endpoint, params))
        return envelope([
            {"id": "j1", "companyId": "c1", "companyName": "A", "companyWebsite": "https://a.com/?tracking=1", "title": "BDR", "jobUrl": "https://a.com/jobs/1", "matchedFunding": [funding]},
            {"id": "j2", "companyId": "c1", "companyName": "A", "companyWebsite": "a.com", "title": "SDR", "jobUrl": "https://a.com/jobs/2", "matchedFunding": [funding]},
        ])
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_funded_hiring_companies", {"role": "bdr", "job_locations": ["US", "Dubai"], "funding_within_days": 90, "posting_age_days_min": 31, "required_evidence": ["founder_led_sales"], "as_of": "2026-09-10T12:00:00Z"})
    assert len(calls) == 1 and calls[0][0] == "/signals/hiring"
    params = calls[0][1]
    assert json.loads(params["job_locations"]) == ["US", "Dubai"]
    assert params["dateTo"] == "2026-08-10"
    assert params["funding_date_from"] == "2026-06-12"
    assert params["include_expired"] is False
    assert len(result["companies"]) == 1 and len(result["companies"][0]["postings"]) == 2
    assert result["companies"][0]["funding"] == [funding]
    assert result["companies"][0]["domain"] == "a.com"
    assert result["status"] == "partial"
    assert result["unverified_requirements"][0]["status"] == "unknown"
    assert result["usage"]["credits_used"] == 1


def test_exact_company_count_is_separate_from_posting_count(monkeypatch):
    calls = []
    async def api(endpoint, params, key):
        calls.append(params)
        return envelope(total=8 if params.get("count_companies") else 10, paid=False)
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_hiring_companies", {"headcount_max": 9, "count": True, "job_locations": ["US", "Dubai"]})
    assert result["totals"] == {"postings": 10, "companies": 8}
    assert result["usage"]["credits_used"] == 0
    assert all(p["team_size"] == "1-9" for p in calls)


def test_later_or_capped_pages_are_not_claimed_complete(monkeypatch):
    async def api(endpoint, params, key):
        return envelope([{"id": "j1", "companyId": "c1", "companyName": "A"}], total=500, more=params["page"] < 3)
    monkeypatch.setattr(entry, "_call_api", api)
    first = call("find_hiring_companies", {"max_pages": 1})
    assert first["status"] == "partial" and first["coverage"]["next_page"] == 2
    last = call("find_hiring_companies", {"page": 3})
    assert last["status"] == "partial" and not last["coverage"]["complete_for_indexed_filters"]


def test_later_page_failure_keeps_paid_results_and_continuation(monkeypatch):
    async def api(endpoint, params, key):
        if params["page"] == 2:
            return {"error": True, "status": 503, "body": {"error": "Unavailable"}}
        return envelope([{"id": "j1", "companyId": "c1", "companyName": "A"}], total=500, more=True)
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_hiring_companies", {"max_pages": 2})
    assert result["status"] == "partial"
    assert result["companies"][0]["company"] == "A"
    assert result["coverage"]["next_page"] == 2
    assert result["usage"]["credits_used"] == 1
    assert result["errors"]


def test_unavailable_hq_city_does_not_turn_into_job_location(monkeypatch):
    async def api(*args):
        raise AssertionError("Should not spend a request on an unsupported HQ-city cohort")
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_funded_hiring_companies", {"company_hq_city": "San Francisco Bay Area", "role": "engineers"})
    assert result["status"] == "unsupported" and result["usage"]["api_calls"] == 0


def test_unsupported_hq_city_offers_labelled_alternatives_without_running_them(monkeypatch):
    async def api(*args):
        raise AssertionError("Alternatives are suggestions; nothing may run")
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_hiring_outlook", {"company_hq_city": "San Francisco Bay Area", "role": "engineers", "funding_rounds": ["Seed"], "as_of": "2026-09-10"})
    assert result["status"] == "unsupported" and result["candidates"] == []
    hiring, outlook = result["alternatives"]
    assert hiring["tool"] == "find_funded_hiring_companies"
    assert hiring["arguments"]["job_locations"] == ["San Francisco Bay Area"]
    assert hiring["arguments"]["funding_within_days"] == 365
    assert "not HQ evidence" in hiring["answers"]
    assert outlook["tool"] == "find_hiring_outlook" and outlook["arguments"]["company_countries"] == ["US"]
    assert "company_hq_city" not in outlook["arguments"]
    # Every suggested call must itself be valid for its tool.
    for alternative in result["alternatives"]:
        props = next(t for t in entry.HR_WORKFLOW_TOOLS if t["name"] == alternative["tool"])["inputSchema"]["properties"]
        assert set(alternative["arguments"]) <= set(props)
    unknown_city = call("find_hiring_companies", {"company_hq_city": "Lisbon"})
    assert unknown_city["alternatives"] == []


def test_count_on_a_tool_without_count_mode_explains_itself(monkeypatch):
    async def api(endpoint, params, key):
        return envelope()
    monkeypatch.setattr(entry, "_call_api", api)
    # count=false is the default behaviour and runs normally.
    assert call("find_hiring_outlook", {"count": False, "funding_rounds": ["Seed"], "as_of": "2026-09-10"})["status"] == "partial"
    response = asyncio.run(entry._handle_jsonrpc({"id": 1, "method": "tools/call", "params": {"name": "find_hiring_outlook", "arguments": {"count": True, "countries": ["US"]}}}, "key", "hr"))
    text = response["result"]["content"][0]["text"]
    assert response["result"]["isError"]
    assert "no count mode" in text and "company_countries" in text and "Accepted:" in text


def test_investor_workflow_hints_name_its_own_arguments():
    response = asyncio.run(entry._handle_jsonrpc({"id": 1, "method": "tools/call", "params": {"name": "research_investor_activity", "arguments": {"city": "Toronto", "countries": ["US"]}}}, "key", "hr"))
    text = response["result"]["content"][0]["text"]
    assert "investor_headquarters" in text and "funded companies' HQ" in text
    assert "job_locations" not in text.split("Accepted:")[0]


def test_count_failure_keeps_the_posting_total(monkeypatch):
    async def api(endpoint, params, key):
        if params.get("count_companies"):
            return {"error": True, "status": 503, "body": {"error": "Unavailable"}}
        return envelope(total=10, paid=False)
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_hiring_companies", {"count": True})
    assert result["totals"] == {"postings": 10, "companies": None}
    assert result["status"] == "partial" and result["errors"]


def test_outlook_postings_check_runs_through_today(monkeypatch):
    calls = []
    async def api(endpoint, params, key):
        calls.append((endpoint, params))
        if endpoint == "/signals/funding":
            return envelope([{"companyName": "A", "companyWebsite": "a.com", "roundType": "seed", "announcedDate": "2026-09-01", "signalId": "t"}])
        return envelope(total=0, paid=False)
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_hiring_outlook", {"funding_rounds": ["Seed"], "as_of": "2026-09-10"})
    history = [p for e, p in calls if e == "/signals/hiring" and p.get("include_expired") is True]
    assert history[0]["dateFrom"] == "2026-06-03" and history[0]["dateTo"] == "2026-09-10"
    assert result["candidates"][0]["quiet_evidence"]["postings_from_lookback_start_to_today"] == 0


def test_count_string_cannot_accidentally_spend_credits(monkeypatch):
    async def api(*args):
        raise AssertionError("Invalid boolean must not reach API")
    monkeypatch.setattr(entry, "_call_api", api)
    result = asyncio.run(entry._handle_jsonrpc({"id": 1, "method": "tools/call", "params": {"name": "find_hiring_companies", "arguments": {"count": "true"}}}, "key", "hr"))
    assert result["result"]["isError"]


def test_gtm_engineer_does_not_collapse_into_sales_department():
    exact = entry._resolve_role("GTM engineers")
    assert "departments" not in exact and "gtm engineer" in exact["positions"]
    broad = entry._resolve_role("GTM")
    assert set(broad["departments"].split(",")) == {"sales", "marketing", "customer_success", "growth"}


def test_funding_window_on_plain_hiring_tool_is_not_ignored():
    params = entry._wf_hiring_params({"funding_within_days": 30, "as_of": "2026-09-10"})
    assert params["funding_date_from"] == "2026-08-11"
    assert params["funding_date_to"] == "2026-09-10T00:00:00+00:00"


def test_outlook_checks_both_histories_and_does_not_add_benchmarks(monkeypatch):
    calls = []
    async def api(endpoint, params, key):
        calls.append((endpoint, params))
        if endpoint == "/signals/funding":
            return envelope([{"companyName": "A", "companyWebsite": "a.com", "companyEmployeeCount": 5, "roundType": "seed", "announcedDate": "2026-09-01", "signalId": "seed"}, {"companyName": "B", "companyWebsite": "b.com", "roundType": "series a", "announcedDate": "2026-09-01", "signalId": "series-a"}])
        if endpoint == "/signals/job-changes" and not params.get("count"):
            return envelope([{"companyName": "A", "companyWebsite": "a.com", "companyEmployeeCount": 5, "newRole": "VP Engineering", "startDate": "2026-09-05", "signalId": "vp"}])
        if endpoint == "/companies":
            return envelope(total=1, paid=False)
        active_b = params.get("company_domain") == "b.com" and params.get("include_expired") is False
        return envelope(total=2 if active_b else 0, paid=False)
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_hiring_outlook", {"as_of": "2026-09-10T12:00:00Z", "company_countries": ["US"], "role": "engineer", "max_companies": 2})
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["benchmark"]["floor"] == .36
    assert candidate["benchmark"]["individual_probability"] is False
    assert candidate["unverified_requirements"][0]["status"] == "unknown"
    assert result["excluded_examples"][0]["domain"] == "b.com"
    assert any(e == "/signals/job-changes" and p.get("count") for e, p in calls)
    assert result["usage"]["credits_used"] == 2


def test_outlook_continuation_keeps_unchecked_candidates_on_same_source_page(monkeypatch):
    async def api(endpoint, params, key):
        if endpoint == "/signals/funding":
            return envelope([{"companyName": str(i), "companyWebsite": f"c{i}.com", "roundType": "seed", "announcedDate": "2026-09-01"} for i in range(5)], more=True)
        return envelope(total=0, paid=False)
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_hiring_outlook", {"funding_rounds": ["Seed"], "max_api_calls": 5, "as_of": "2026-09-10"})
    assert result["coverage"]["next_candidate_offset"] == 1
    assert result["coverage"]["next_source_page"] is None


def test_outlook_rejects_an_already_observed_post_trigger_hire(monkeypatch):
    async def api(endpoint, params, key):
        if endpoint == "/signals/funding":
            return envelope([{"companyName": "A", "companyWebsite": "a.com", "roundType": "seed", "announcedDate": "2026-09-01", "signalId": "trigger"}])
        if endpoint == "/signals/job-changes" and params.get("dateFrom") == "2026-09-01":
            assert params["exclude_signal_ids"] == "trigger"
            return envelope(total=1, paid=False)
        return envelope(total=0, paid=False)
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_hiring_outlook", {"funding_rounds": ["Seed"], "as_of": "2026-09-10"})
    assert not result["candidates"]
    assert result["excluded_examples"][0]["evidence"]["post_trigger_announced_joins_excluding_triggers"] == 1


def test_other_leadership_triggers_still_count_as_observed_outcomes(monkeypatch):
    async def api(endpoint, params, key):
        if endpoint == "/signals/funding":
            return envelope()
        if endpoint == "/signals/job-changes" and not params.get("count"):
            return envelope([
                {"companyName": "A", "companyWebsite": "a.com", "newRole": "VP Sales", "startDate": "2026-09-01", "signalId": "vp"},
                {"companyName": "A", "companyWebsite": "a.com", "newRole": "Head of Engineering", "startDate": "2026-09-05", "signalId": "head"},
            ])
        if params.get("exclude_signal_ids"):
            assert params["exclude_signal_ids"] == "vp"
            return envelope(total=1, paid=False)
        return envelope(total=0, paid=False)
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_hiring_outlook", {"as_of": "2026-09-10"})
    assert result["candidates"] == []


def test_investor_activity_uses_existing_round_edges_and_reports_paging(monkeypatch):
    calls = []
    async def api(endpoint, params, key):
        calls.append((endpoint, params))
        if endpoint == "/signals/investors":
            return envelope([{"name": "Toronto VC"}])
        return envelope([{"companyName": "Company", "investors": [{"name": "Toronto VC"}]}], more=True)
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("research_investor_activity", {"investor_headquarters": "Toronto", "company_countries": ["US"], "max_pages": 1, "as_of": "2026-09-10"})
    assert calls[1][1]["investors"] == "Toronto VC" and calls[1][1]["amount_min"] == 10000000
    assert result["status"] == "partial" and result["coverage"]["next_funding_page"] == 2


def test_headquarters_match_is_not_reported_as_round_participation(monkeypatch):
    async def api(endpoint, params, key):
        if endpoint == "/signals/investors":
            return envelope([{"name": "Impression Ventures", "headquarters": "Toronto"}, {"name": "Framework Venture Partners"}, {"name": "Smith, Jones & Co"}])
        return envelope([
            {"companyName": "401GO", "companyWebsite": "401go.com", "roundType": "Series B", "amount": 33000000, "sources": [{"url": "https://news/401go"}],
             "investors": [{"name": "impression ventures", "isLead": True}, {"name": "Centana"}]},
        ])
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("research_investor_activity", {"investor_headquarters": "Toronto", "as_of": "2026-09-10"})
    [match] = result["investors_with_matching_rounds"]
    assert match["investor"] == "Impression Ventures"
    assert match["matching_rounds"][0]["company"] == "401GO" and match["matching_rounds"][0]["lead"] is True
    assert match["matching_rounds"][0]["sources"] == ["https://news/401go"]
    assert result["investors_without_matching_rounds"] == ["Framework Venture Partners"]
    assert result["investors_not_checked"] == ["Smith, Jones & Co"]
    assert result["summary"].startswith("1 of 2 checked investors")
    assert result["coverage"]["investors_with_matching_rounds"] == 1


def test_investor_workflow_has_no_hidden_city_or_country_defaults(monkeypatch):
    calls = []
    async def api(endpoint, params, key):
        calls.append((endpoint, params))
        if endpoint == "/signals/investors":
            return envelope([{"name": "Berlin VC"}])
        return envelope()
    monkeypatch.setattr(entry, "_call_api", api)
    missing = asyncio.run(entry._handle_jsonrpc({"id": 1, "method": "tools/call", "params": {"name": "research_investor_activity", "arguments": {}}}, "key", "hr"))
    assert missing["result"]["isError"] and "investor_headquarters is required" in missing["result"]["content"][0]["text"]
    assert calls == []
    tool = next(t for t in entry.HR_WORKFLOW_TOOLS if t["name"] == "research_investor_activity")
    assert tool["inputSchema"]["required"] == ["investor_headquarters"]
    result = call("research_investor_activity", {"investor_headquarters": "Berlin", "round_amount_min": 0, "as_of": "2026-09-10"})
    funding = calls[1][1]
    assert calls[0][1]["headquarters"] == "Berlin"
    assert "countries" not in funding and "currency" not in funding and "amount_min" not in funding
    assert result["coverage"]["amount_filter"] == "none"
    floor = call("research_investor_activity", {"investor_headquarters": "Berlin", "as_of": "2026-09-10"})
    assert calls[-1][1]["currency"] == "USD" and "USD-denominated" in floor["coverage"]["amount_filter"]


def test_workflow_results_are_compact_json(monkeypatch):
    async def api(endpoint, params, key):
        return envelope(total=1, paid=False)
    monkeypatch.setattr(entry, "_call_api", api)
    response = asyncio.run(entry._handle_jsonrpc({"id": 1, "method": "tools/call", "params": {"name": "find_hiring_companies", "arguments": {"count": True}}}, "key", "hr"))
    text = response["result"]["content"][0]["text"]
    assert "\n" not in text and '": ' not in text
    assert json.loads(text)["totals"]["postings"] == 1


def test_positive_count_names_the_follow_up_call(monkeypatch):
    async def api(endpoint, params, key):
        return envelope(total=3, paid=False)
    monkeypatch.setattr(entry, "_call_api", api)
    assert "find_funded_hiring_companies again" in call("find_funded_hiring_companies", {"count": True})["next_step"]
    async def empty(endpoint, params, key):
        return envelope(total=0, paid=False)
    monkeypatch.setattr(entry, "_call_api", empty)
    assert "next_step" not in call("find_hiring_companies", {"count": True})


def test_hiring_workflow_defaults_to_one_page_of_fifty(monkeypatch):
    calls = []
    async def api(endpoint, params, key):
        calls.append(params)
        return envelope([{"id": "j1", "companyId": "c1", "companyName": "A"}], total=500, more=True)
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_hiring_companies", {})
    assert len(calls) == 1 and calls[0]["limit"] == 50
    assert result["usage"]["credits_used"] == 1 and result["coverage"]["next_page"] == 2


def test_outlook_trigger_sources_are_capped_urls():
    row = {"companyName": "A", "companyWebsite": "a.com", "newRole": "VP Sales", "startDate": "2026-09-01",
           "sources": [{"url": f"https://s/{i}", "isPrimary": False, "content": "x" * 500} for i in range(6)]}
    trigger = entry._wf_trigger(row, "job_change", entry._wf_date("2026-09-10"), 90)
    assert trigger["sources"] == ["https://s/0", "https://s/1", "https://s/2"]
