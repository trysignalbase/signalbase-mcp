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


def test_classic_funding_schema_exposes_date_basis_with_announced_default():
    prop = _classic_props("search_funding_signals")["date_basis"]
    assert prop["enum"] == ["announced", "occurred_at"]
    assert prop["default"] == "announced"
    hr = _hr_props("search_funding_signals")["date_basis"]
    assert hr["enum"] == prop["enum"] and hr["default"] == "announced"


def test_prepare_tool_args_defaults_classic_funding_date_basis():
    params, _, _ = entry._prepare_tool_args({"countries": "DE"}, "search_funding_signals", "classic")
    assert params["date_basis"] == "announced"
    assert params["countries"] == "DE"
    assert "filter_version" not in params  # classic filter_version default is untouched


def test_prepare_tool_args_preserves_explicit_date_basis():
    params, _, _ = entry._prepare_tool_args({"date_basis": "occurred_at"}, "search_funding_signals", "classic")
    assert params["date_basis"] == "occurred_at"
    params, _, _ = entry._prepare_tool_args({"date_basis": "occurred_at"}, "search_funding_signals", "hr")
    assert params["date_basis"] == "occurred_at"


def test_date_basis_default_is_funding_only():
    for tool in ("search_hiring_signals", "search_acquisition_signals", "search_companies"):
        params, _, _ = entry._prepare_tool_args({}, tool, "classic")
        assert "date_basis" not in params, tool


def test_prepare_tool_args_forwards_hiring_description_unchanged():
    params, _, _ = entry._prepare_tool_args({"description": "\"Series A\""}, "search_hiring_signals", "classic")
    assert params["description"] == "\"Series A\""


def test_instructions_document_both_arguments():
    assert "`date_basis`" in entry.INSTRUCTIONS
    assert "`description`" in entry.INSTRUCTIONS
