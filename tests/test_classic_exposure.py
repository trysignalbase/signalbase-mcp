"""Classic profile exposes REST filters the HR profile already had (1.2.0)."""
import entry


def _classic_props(name):
    return next(t for t in entry._tools_for_profile("classic") if t["name"] == name)["inputSchema"]["properties"]


def _hr_props(name):
    return next(t for t in entry._tools_for_profile("hr") if t["name"] == name)["inputSchema"]["properties"]


def test_classic_hiring_schema_exposes_description():
    prop = _classic_props("search_hiring_signals")["description"]
    assert prop["type"] == "string"
    assert "websearch" in prop["description"]
    assert prop == entry.HIRING_DESCRIPTION_PROP


def test_hr_hiring_description_reuses_the_shared_prop():
    assert _hr_props("search_hiring_signals")["description"] == entry.HIRING_DESCRIPTION_PROP


def test_description_prop_does_not_misdescribe_the_search_argument():
    """`search` matches name, industry, title, location and city -- never the body."""
    text = entry.HIRING_DESCRIPTION_PROP["description"]
    assert "Title-only" not in text
    assert "never the description body" in text


def test_classic_funding_schema_advertises_date_basis_without_a_default():
    prop = _classic_props("search_funding_signals")["date_basis"]
    assert prop["enum"] == ["announced", "occurred_at"]
    # A default here would make MCP clients apply it themselves.
    assert "default" not in prop
    assert "opt-in" in prop["description"]


def test_hr_keeps_its_announced_default():
    hr = _hr_props("search_funding_signals")["date_basis"]
    assert hr["default"] == "announced"
    params, _, _ = entry._prepare_tool_args({}, "search_funding_signals", "hr")
    assert params["date_basis"] == "announced"


def test_classic_never_injects_date_basis():
    """A classic saved query keeps the stored-event-date window it was built
    against. 'announced' both adds and drops rows, so it cannot be silent."""
    for args in ({}, {"countries": "DE"}, {"date_preset": "last_7d"}, {"count": True}):
        params, _, _ = entry._prepare_tool_args(dict(args), "search_funding_signals", "classic")
        assert "date_basis" not in params, args
        assert "filter_version" not in params, args


def test_prepare_tool_args_preserves_explicit_date_basis():
    for profile in ("classic", "hr"):
        for value in ("announced", "occurred_at"):
            params, _, _ = entry._prepare_tool_args(
                {"date_basis": value}, "search_funding_signals", profile
            )
            assert params["date_basis"] == value, (profile, value)


def test_date_basis_is_funding_only():
    for tool in ("search_hiring_signals", "search_acquisition_signals", "search_companies"):
        for profile in ("classic", "hr"):
            params, _, _ = entry._prepare_tool_args({}, tool, profile)
            assert "date_basis" not in params, (tool, profile)


def test_prepare_tool_args_forwards_hiring_description_unchanged():
    params, _, _ = entry._prepare_tool_args({"description": "\"Series A\""}, "search_hiring_signals", "classic")
    assert params["description"] == "\"Series A\""


def test_instructions_document_both_arguments():
    assert "`date_basis`" in entry.INSTRUCTIONS
    assert "`description`" in entry.INSTRUCTIONS
