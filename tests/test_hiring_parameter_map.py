import json
from pathlib import Path

import entry


def test_generated_hiring_parameter_map_matches_classic_discovery_and_rest_inventory():
    root = Path(__file__).resolve().parents[1]
    mapping = json.loads((root / "docs" / "hiring-parameter-map.json").read_text("utf8"))
    inventory = json.loads((root / "tests" / "fixtures" / "api-contract.json").read_text("utf8"))
    rest = next(route for route in inventory["routes"] if route["path"] == "/api/v2/signals/hiring")
    descriptor = next(tool for tool in entry._tools_for_profile("classic") if tool["name"] == "search_hiring_signals")
    props = descriptor["inputSchema"]["properties"]
    entries = mapping["parameter_mapping"]
    assert {item["rest_query_parameter"] for item in entries} == set(rest["query_parameters"])
    for item in entries:
        assert item["parser_fields"] == item["router_fields"]
        assert item["parser_fields"]
        assert all(field["schema"] is not None for field in item["parsed_schema"])
        assert item["mcp_argument"] in props
    assert mapping["worker_only_shims"]["group_by_company"].endswith("not a REST parameter")
    assert mapping["worker_only_shims"]["verbose"].endswith("not a REST parameter")
