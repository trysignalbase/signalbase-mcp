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
    assert params["open_as_of"] == "2026-09-10T12:00:00+00:00"
    assert len(result["companies"]) == 1 and len(result["companies"][0]["postings"]) == 2
    assert result["companies"][0]["funding"] == [funding]
    assert result["companies"][0]["domain"] == "a.com"
    assert result["status"] == "complete"
    assert result["query_status"] == "complete"
    assert result["match_status"] == "partial_evidence"
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
            return {"error": True, "status": 503, "body": {"error": "Unavailable", "meta": {"creditsUsed": 1}}}
        return envelope([{"id": "j1", "companyId": "c1", "companyName": "A"}], total=500, more=True)
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_hiring_companies", {"max_pages": 2})
    assert result["status"] == "partial"
    assert result["companies"][0]["company"] == "A"
    assert result["coverage"]["next_page"] == 2
    assert result["usage"]["credits_used"] == 2
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
    empty = call("find_hiring_outlook", {"count": False, "funding_rounds": ["Seed"], "as_of": "2026-09-10"})
    assert empty["query_status"] == "complete" and empty["match_status"] == "no_match_at_reference_time"
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
    current = [p for e, p in calls if e == "/signals/hiring" and p.get("include_expired") is False]
    assert current[0]["open_as_of"] == "2026-09-10T00:00:00+00:00"
    assert current[0]["dateTo"] == "2026-09-10"
    assert result["candidates"][0]["quiet_evidence"]["postings_from_lookback_start_to_today"] == 0
    assert "not a historical index snapshot" in result["coverage"]["as_of_semantics"]


def test_count_string_cannot_accidentally_spend_credits(monkeypatch):
    async def api(*args):
        raise AssertionError("Invalid boolean must not reach API")
    monkeypatch.setattr(entry, "_call_api", api)
    result = asyncio.run(entry._handle_jsonrpc({"id": 1, "method": "tools/call", "params": {"name": "find_hiring_companies", "arguments": {"count": "true"}}}, "key", "hr"))
    assert result["result"]["isError"]


def test_array_item_enums_are_validated_before_paid_calls(monkeypatch):
    calls = []

    async def api(*args):
        calls.append(args)
        return envelope([{"name": "Should Not Be Fetched"}])

    monkeypatch.setattr(entry, "_call_api", api)
    response = asyncio.run(entry._handle_jsonrpc({"id": 1, "method": "tools/call", "params": {
        "name": "research_investor_activity",
        "arguments": {"investor_headquarters": "Toronto", "required_evidence": ["typo"]},
    }}, "key", "hr"))
    assert response["result"]["isError"]
    assert "required_evidence" in response["result"]["content"][0]["text"]
    assert response["result"]["_meta"]["usage"] == {"api_calls": 0, "credits_used": 0}
    assert calls == []


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


def test_investor_activity_rejects_rounds_with_conflicting_window_dates(monkeypatch):
    async def api(endpoint, params, key):
        if endpoint == "/signals/investors":
            return envelope([{"name": "Example Ventures", "headquarters": "Toronto"}])
        return envelope([{
            "companyName": "Conflicted", "companyWebsite": "conflicted.example",
            "roundType": "Seed", "announcedDate": "2026-08-13",
            "occurredAt": "2024-10-02T05:41:23Z",
            "investors": [{"name": "Example Ventures", "isLead": False}],
            "sources": [{"url": "https://news/conflict", "publishedAt": "2024-10-02"}],
        }])

    monkeypatch.setattr(entry, "_call_api", api)
    result = call("research_investor_activity", {
        "investor_headquarters": "Toronto", "funding_within_days": 365,
        "as_of": "2026-09-10",
    })
    assert result["investors_with_matching_rounds"] == []
    assert result["rejected_rounds"][0]["company"] == "Conflicted"
    assert "do not all support" in result["rejected_rounds"][0]["reason"]


def test_investor_failure_does_not_claim_no_matches(monkeypatch):
    async def api(endpoint, params, key):
        if endpoint == "/signals/investors":
            return envelope([{"name": "Example Ventures", "headquarters": "Toronto"}])
        return {"error": True, "status": 503, "body": {"error": "Unavailable"}}

    monkeypatch.setattr(entry, "_call_api", api)
    result = call("research_investor_activity", {"investor_headquarters": "Toronto", "as_of": "2026-09-10"})
    assert result["query_status"] == "partial" and result["match_status"] == "unknown"


def test_headquarters_match_is_not_reported_as_round_participation(monkeypatch):
    async def api(endpoint, params, key):
        if endpoint == "/signals/investors":
            return envelope([{"name": "Impression Ventures", "headquarters": "Toronto"}, {"name": "Framework Venture Partners"}, {"name": "Smith, Jones & Co"}])
        return envelope([
            {"companyName": "401GO", "companyWebsite": "401go.com", "roundType": "Series B", "amount": 33000000, "sources": [{"url": "https://news.example/401GO-Raises-%2433M-Series-B-Led-by-Centana-Growth-Partners-to-Drive-Growth", "title": None, "publishedAt": "2025-12-09"}],
             "investors": [{"name": "impression ventures", "isLead": True}, {"name": "Centana"}]},
        ])
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("research_investor_activity", {"investor_headquarters": "Toronto", "as_of": "2026-09-10"})
    [match] = result["investors_with_matching_rounds"]
    assert match["investor"] == "Impression Ventures"
    round_evidence = match["matching_rounds"][0]
    assert round_evidence["company"] == "401GO" and round_evidence["lead"] is None
    assert round_evidence["stored_lead_flag"] is True
    assert round_evidence["lead_status"] == "contradicted_by_source_title"
    assert round_evidence["source_named_lead"] == "Centana Growth Partners"
    assert "Centana-Growth-Partners" in round_evidence["sources"][0]["url"]
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
    assert "structuredContent" not in response["result"]
    tool = next(tool for tool in entry.HR_WORKFLOW_TOOLS if tool["name"] == "find_hiring_companies")
    assert "outputSchema" not in tool


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


def test_old_conflicting_funding_date_cannot_become_a_recent_trigger():
    now = entry._wf_date("2026-09-10")
    conflict = {
        "companyName": "Liquid AI", "companyWebsite": "liquid.ai", "roundType": "seed",
        "announcedDate": "2026-08-13", "occurredAt": "2024-10-02T05:41:23Z",
    }
    assert entry._wf_trigger(conflict, "funding", now, 90) is None
    supported = {**conflict, "occurredAt": "2026-08-13T05:41:23Z"}
    trigger = entry._wf_trigger(supported, "funding", now, 90)
    assert trigger["funding"]["source_identity_status"] == "not_verified_by_index"
    assert trigger["headcount_evidence"]["verified_exact"] is False


def test_narrow_role_reports_same_function_postings_per_place(monkeypatch):
    calls = []
    async def api(endpoint, params, key):
        calls.append(params)
        places = json.loads(params.get("job_locations", "[]"))
        broad = params.get("departments") == "sales"
        if places == ["Dubai"]:
            return envelope(total=5 if broad else 0, paid=False)
        return envelope(total=200 if broad else 12, paid=False)
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_hiring_companies", {"role": "bdr", "headcount_max": 9, "job_locations": ["US", "Dubai"], "count": True})
    assert result["by_place"]["Dubai"] == {"postings": 0, "broader_sales_postings": 5}
    assert result["by_place"]["US"]["postings"] == 12
    assert "role='sales'" in result["hints"][0] and "Dubai" in result["hints"][0]
    assert all(p["team_size"] == "1-9" for p in calls)


def test_seed_asks_do_not_use_arbitrary_headcount_caps(monkeypatch):
    params = entry._wf_hiring_params({"funding_rounds": ["Seed"], "as_of": "2026-09-10"})
    assert "team_size" not in params
    assert entry._wf_hiring_params({"funding_rounds": ["Seed"], "headcount_max": 2000, "as_of": "2026-09-10"})["team_size"] == "1-2000"
    assert "team_size" not in entry._wf_hiring_params({"funding_rounds": ["Series C"], "as_of": "2026-09-10"})
    async def api(endpoint, params, key):
        if params.get("count"):
            return envelope(total=3, paid=False)
        return envelope([{
            "id": "j1", "companyId": "c1", "companyName": "A", "companyWebsite": "a.com",
            "companyEmployeeCount": 900, "title": "Engineer", "jobUrl": "https://a/jobs/1",
            "matchedFunding": [{
                "signalId": "f1", "roundType": "Seed", "verificationStatus": "unverified",
                "dateQualification": "all_stored_event_dates_within_requested_window",
                "sources": [{"url": "https://news/a", "title": "A raises seed", "publishedAt": "2026-09-01"}],
            }],
        }])
    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_funded_hiring_companies", {"funding_rounds": ["Seed"]})
    assert result["companies"][0]["headcount"] == 900
    assert result["companies"][0]["qualification"] == "matches_indexed_filters"
    assert result["query_status"] == "complete"
    review = result["companies"][0]["funding_evidence_review"][0]
    assert review["source_identity_status"] == "needs_source_review"
    assert review["sources"][0]["url"] == "https://news/a"


def test_sector_preset_maps_to_industry_labels_on_workflows_and_search_tools(monkeypatch):
    params = entry._wf_hiring_params({"sector": "fmcg", "as_of": "2026-09-10"})
    assert "Personal Care Product Manufacturing" in params["categories"].split("|")
    api_params, _, _ = entry._prepare_tool_args({"positions": "cfo", "sector": "fmcg"}, "search_job_change_signals", "hr")
    assert "Food and Beverage Manufacturing" in api_params["categories"].split("|") and "sector" not in api_params
    response = asyncio.run(entry._handle_jsonrpc({"id": 1, "method": "tools/call", "params": {"name": "search_job_change_signals", "arguments": {"sector": "mining"}}}, "key", "hr"))
    assert response["result"]["isError"] and "expected one of" in response["result"]["content"][0]["text"]
    creative = entry._wf_hiring_params({"sector": "creative/digital", "as_of": "2026-09-10"})
    assert {"Design Services", "Advertising Services", "Public Relations and Communications Services"} <= set(creative["categories"].split("|"))


def test_search_tool_sends_job_locations_as_json_and_compact_counts_drop_empty_data(monkeypatch):
    api_params, _, _ = entry._prepare_tool_args({"job_locations": ["Poland"], "exclude_company_countries": "PL"}, "search_hiring_signals", "classic")
    assert json.loads(api_params["job_locations"]) == ["Poland"]
    api_params, _, _ = entry._prepare_tool_args({"job_locations": "Belgium, Dubai"}, "search_hiring_signals", "classic")
    assert json.loads(api_params["job_locations"]) == ["Belgium", "Dubai"]
    async def api(endpoint, params, key):
        return {"success": True, "data": [], "pagination": {"totalCount": 7}, "meta": {"endpoint": "signals.hiring", "creditsUsed": 0}}
    monkeypatch.setattr(entry, "_call_api", api)
    hr = asyncio.run(entry._handle_jsonrpc({"id": 1, "method": "tools/call", "params": {"name": "search_hiring_signals", "arguments": {"count": True, "by_country": False}}}, "key", "hr"))
    body = json.loads(hr["result"]["content"][0]["text"])
    assert "data" not in body and body["countOnly"] is True and body["pagination"]["totalCount"] == 7
    classic = asyncio.run(entry._handle_jsonrpc({"id": 1, "method": "tools/call", "params": {"name": "search_hiring_signals", "arguments": {"count": True}}}, "key"))
    assert json.loads(classic["result"]["content"][0]["text"])["data"] == []


def test_source_text_requirements_are_quoted_without_inference(monkeypatch):
    async def api(endpoint, params, key):
        return envelope([{
            "id": "j1", "companyId": "c1", "companyName": "Explicit", "companyWebsite": "explicit.example",
            "title": "Founding AE", "jobUrl": "https://explicit.example/jobs/1",
            "descriptionText": "Join our team. Our founder currently leads sales across Europe. You will be the right-hand to our founder.",
        }])

    monkeypatch.setattr(entry, "_call_api", api)
    result = call("find_hiring_companies", {"required_evidence": ["founder_led_sales", "founder_right_hand"]})
    [company] = result["companies"]
    assert result["query_status"] == "complete"
    assert company["match_status"] == "supported_with_source_text"
    evidence = {item["requirement"]: item for item in company["criteria"]}
    assert evidence["founder_led_sales"]["quote"].startswith("Our founder currently leads sales")
    assert evidence["founder_right_hand"]["source_url"].endswith("/jobs/1")
    assert company["unverified_requirements"] == []


def test_titles_and_job_locations_do_not_infer_first_hire_or_office(monkeypatch):
    async def api(endpoint, params, key):
        return envelope([{
            "id": "j1", "companyId": "c1", "companyName": "Careful", "companyWebsite": "careful.example",
            "title": "Founding Engineer", "location": "Berlin", "jobUrl": "https://careful.example/jobs/1",
            "descriptionText": "Build the product with a distributed team.",
        }])

    monkeypatch.setattr(entry, "_call_api", api)
    [company] = call("find_hiring_companies", {"required_evidence": ["first_hire", "office_opening"]})["companies"]
    assert company["match_status"] == "partial_evidence"
    assert {item["requirement"] for item in company["unverified_requirements"]} == {"first_hire", "office_opening"}


def test_explicit_office_location_wording_is_evidence_of_presence_only(monkeypatch):
    async def api(endpoint, params, key):
        return envelope([{
            "id": "j1", "companyId": "c1", "companyName": "DevBrother", "companyWebsite": "devbrother.com",
            "title": "Engineer", "location": "Offices in Ukraine (Kyiv) and Poland (Wroclaw)",
            "jobUrl": "https://example.test/job/1",
        }])

    monkeypatch.setattr(entry, "_call_api", api)
    [company] = call("find_hiring_companies", {"job_locations": ["Poland"], "required_evidence": ["office_presence", "office_opening"]})["companies"]
    criteria = {item["requirement"]: item for item in company["criteria"]}
    assert criteria["office_presence"]["source_field"] == "job_location"
    assert [item["requirement"] for item in company["unverified_requirements"]] == ["office_opening"]


def test_office_description_requires_requested_place_alignment(monkeypatch):
    async def api(endpoint, params, key):
        return envelope([{
            "id": "j1", "companyId": "c1", "companyName": "Asana", "companyWebsite": "asana.com",
            "title": "Engineer", "location": "Warsaw", "jobUrl": "https://example.test/job/1",
            "descriptionText": "This role is based in our Warsaw office with an office-centric hybrid schedule.",
        }, {
            "id": "j2", "companyId": "c2", "companyName": "Elsewhere", "companyWebsite": "elsewhere.example",
            "title": "Engineer", "location": "Warsaw", "jobUrl": "https://example.test/job/2",
            "descriptionText": "This role is based in our London office.",
        }, {
            "id": "j3", "companyId": "c3", "companyName": "Brussels", "companyWebsite": "brussels.example",
            "title": "Engineer", "location": "Brussels", "jobUrl": "https://example.test/job/3",
            "descriptionText": "This role is based in our Brussels office.",
        }])

    monkeypatch.setattr(entry, "_call_api", api)
    companies = call("find_hiring_companies", {"job_locations": ["Poland"], "required_evidence": ["office_presence"]})["companies"]
    assert companies[0]["match_status"] == "supported_with_source_text"
    assert companies[0]["criteria"][-1]["quote"].startswith("This role is based in our Warsaw office")
    assert companies[1]["match_status"] == "partial_evidence"
    belgium = call("find_hiring_companies", {"job_locations": ["Belgium"], "required_evidence": ["office_presence"]})["companies"]
    assert belgium[2]["match_status"] == "supported_with_source_text"
    assert entry._wf_source_claims({
        "id": "j4", "location": "United States", "descriptionText": "Our office is based in London and serves customers across the United States.",
    }, ["office_presence"], {"job_locations": ["US"]}) == {}


def test_caller_defined_startup_and_growth_rules_map_to_api():
    params = entry._wf_hiring_params({
        "headcount_max": 200,
        "headcount_growth_window": "6m",
        "headcount_growth_min": 12.5,
        "startup_definition": {"max_headcount": 100, "founded_year_min": 2020, "require_funding": True},
        "as_of": "2026-09-10",
    })
    assert params["team_size"] == "1-100"
    assert params["founded_year_min"] == 2020
    assert params["headcount_growth_window"] == "6m" and params["headcount_growth_min"] == 12.5
    assert params["funding_date_from"] == "2026-06-12"


def test_nested_startup_definition_is_validated_before_io(monkeypatch):
    calls = []
    async def api(*args):
        calls.append(args)
        return envelope()
    monkeypatch.setattr(entry, "_call_api", api)
    response = asyncio.run(entry._handle_jsonrpc({"id": 1, "method": "tools/call", "params": {
        "name": "find_hiring_companies", "arguments": {"startup_definition": {"max_headcount": "tiny", "surprise": True}},
    }}, "key", "hr"))
    assert response["result"]["isError"] and calls == []
    response = asyncio.run(entry._handle_jsonrpc({"id": 2, "method": "tools/call", "params": {
        "name": "find_hiring_companies", "arguments": {"headcount_growth_window": "6m"},
    }}, "key", "hr"))
    assert response["result"]["isError"] and "requires headcount_growth_min" in response["result"]["content"][0]["text"] and calls == []


def test_live_ats_verification_is_bounded_and_supports_required_evidence(monkeypatch):
    async def api(endpoint, params, key):
        return envelope([{
            "id": "j1", "companyId": "c1", "companyName": "ATS Co", "companyWebsite": "ats.example",
            "title": "Designer", "jobUrl": "https://boards.greenhouse.io/atsco/jobs/123",
        }, {
            "id": "j2", "companyId": "c1", "companyName": "ATS Co", "companyWebsite": "ats.example",
            "title": "Marketer", "jobUrl": "https://jobs.lever.co/atsco/abc",
        }])
    checks = []
    async def verify(posting, public_cache=None):
        checks.append(posting["id"])
        return {"source_verified_open": True, "source_verification": {"status": "open", "method": "test_public_api", "offices": ["London"]}}
    monkeypatch.setattr(entry, "_call_api", api)
    monkeypatch.setattr(entry, "_wf_verify_live_posting", verify)
    result = call("find_hiring_companies", {
        "required_evidence": ["verified_live_vacancy", "office_presence"],
        "verification_limit": 1,
    })
    [company] = result["companies"]
    assert checks == ["j1"] and result["usage"]["source_checks"] == 1
    assert company["match_status"] == "supported_source_verified"
    assert company["postings"][0]["open_status"] == "source_verified_open"
    assert company["postings"][1]["source_verified_open"] is None


@pytest.mark.parametrize("url,provider", [
    ("https://job-boards.greenhouse.io/acme/jobs/123", "greenhouse"),
    ("https://jobs.lever.co/acme/a-b_c", "lever"),
    ("https://jobs.ashbyhq.com/acme/abc_123", "ashby"),
])
def test_only_allowlisted_ats_urls_are_translated(url, provider):
    assert entry._wf_ats_target(url)[0] == provider
    assert entry._wf_ats_target("https://example.com/jobs/123") is None


def test_funding_identity_uses_explicit_source_title():
    status, reason = entry._wf_funding_identity("North Star", "northstar.example", {
        "sources": [{"url": "https://news.example/story", "title": "North Star raises a Series A"}],
    })
    assert status == "supported_by_source_title" and "explicitly names" in reason
    generic, _ = entry._wf_funding_identity("Seed", "seed.example", {
        "sources": [{"url": "https://news.example/story", "title": "Seed round raises $10M"}],
    })
    assert generic == "needs_source_review"


def test_ats_api_absence_is_unknown_not_closed(monkeypatch):
    async def missing(url):
        return 404, None
    monkeypatch.setattr(entry, "_wf_public_json", missing)
    result = asyncio.run(entry._wf_verify_live_posting({"url": "https://jobs.lever.co/acme/abc"}))
    assert result["source_verified_open"] is None
    assert result["source_verification"]["status"] == "not_visible_in_public_api"


def test_ashby_board_fetch_is_deduplicated(monkeypatch):
    calls = []
    async def api(endpoint, params, key):
        return envelope([
            {"id": "j1", "companyId": "c1", "companyName": "A", "companyWebsite": "a.example", "jobUrl": "https://jobs.ashbyhq.com/acme/one"},
            {"id": "j2", "companyId": "c1", "companyName": "A", "companyWebsite": "a.example", "jobUrl": "https://jobs.ashbyhq.com/acme/two"},
        ])
    async def public(url):
        calls.append(url)
        return 200, {"jobs": [
            {"jobPostingId": "one", "jobUrl": "https://jobs.ashbyhq.com/acme/one"},
            {"jobPostingId": "two", "jobUrl": "https://jobs.ashbyhq.com/acme/two"},
        ]}
    monkeypatch.setattr(entry, "_call_api", api)
    monkeypatch.setattr(entry, "_wf_public_json", public)
    result = call("find_hiring_companies", {"verify_live": True, "verification_limit": 2})
    assert len(calls) == 1
    assert all(posting["source_verified_open"] for posting in result["companies"][0]["postings"])


def test_shared_ats_timeout_cannot_cancel_the_whole_workflow(monkeypatch):
    original_wait_for = asyncio.wait_for
    async def api(endpoint, params, key):
        return envelope([{
            "id": f"j{i}", "companyId": "c1", "companyName": "A", "companyWebsite": "a.example",
            "jobUrl": f"https://jobs.ashbyhq.com/acme/job{i}",
        } for i in range(9)])
    async def slow_public(url):
        await asyncio.sleep(.02)
        return 200, {"jobs": []}
    async def tiny_timeout(awaitable, timeout):
        return await original_wait_for(awaitable, timeout=.001)
    monkeypatch.setattr(entry, "_call_api", api)
    monkeypatch.setattr(entry, "_wf_public_json", slow_public)
    monkeypatch.setattr(entry.asyncio, "wait_for", tiny_timeout)
    result = call("find_hiring_companies", {"verify_live": True, "verification_limit": 9})
    assert len(result["companies"][0]["postings"]) == 9
    assert all(posting["source_verified_open"] is None for posting in result["companies"][0]["postings"])


def test_ats_office_metadata_must_match_requested_place(monkeypatch):
    async def api(endpoint, params, key):
        return envelope([{
            "id": "j1", "companyId": "c1", "companyName": "A", "companyWebsite": "a.example",
            "jobUrl": "https://boards.greenhouse.io/acme/jobs/123",
        }])
    async def verify(posting, public_cache=None):
        return {"source_verified_open": True, "source_verification": {"status": "open", "offices": ["London"]}}
    monkeypatch.setattr(entry, "_call_api", api)
    monkeypatch.setattr(entry, "_wf_verify_live_posting", verify)
    [company] = call("find_hiring_companies", {"job_locations": ["Poland"], "required_evidence": ["office_presence"]})["companies"]
    assert company["match_status"] == "partial_evidence"


def test_malformed_source_url_does_not_abort_lead_evidence():
    assert entry._source_named_lead({"sources": [{"url": "http://[bad", "title": "Round led by Safe Capital"}]}) == "Safe Capital"
