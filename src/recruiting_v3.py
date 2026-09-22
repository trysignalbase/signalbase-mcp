"""Thin v3 transport. Business definitions and execution live in the app contract."""
import asyncio
import json
import re
import uuid
from copy import deepcopy
from recruiting_contract import CONTRACT, REQUEST_CONTRACT


def validate(value, schema, root=None, path="arguments"):
    root = root or schema
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        return validate(value, target, root, path)
    if "anyOf" in schema:
        for child in schema["anyOf"]:
            try:
                validate(value, child, root, path)
                return
            except ValueError:
                pass
        raise ValueError(f"{path}: no allowed argument shape matched")
    kind = schema.get("type")
    valid = {"object": isinstance(value, dict), "array": isinstance(value, list),
             "string": isinstance(value, str), "boolean": isinstance(value, bool),
             "integer": isinstance(value, int) and not isinstance(value, bool),
             "number": isinstance(value, (int, float)) and not isinstance(value, bool),
             "null": value is None}
    if kind and not valid.get(kind, False):
        raise ValueError(f"{path}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: use one of {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{path}: expected {schema['const']}")
    if kind == "object":
        properties = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(value)
        extra = set(value) - set(properties)
        if missing:
            raise ValueError(f"{path}: missing {', '.join(sorted(missing))}")
        if extra and schema.get("additionalProperties") is False:
            raise ValueError(f"{path}: unknown fields {', '.join(sorted(extra))}")
        for key, item in value.items():
            if key in properties:
                validate(item, properties[key], root, f"{path}.{key}")
    if kind == "array":
        low, high = schema.get("minItems", 0), schema.get("maxItems", 100000)
        if len(value) < low or len(value) > high:
            bound = f"at least {low}" if len(value) < low else f"at most {high}"
            raise ValueError(
                f"{path}: {len(value)} items given; this field accepts {bound}"
                + (". Split the list across several calls" if len(value) > high else "")
            )
        for index, item in enumerate(value):
            validate(item, schema.get("items", {}), root, f"{path}[{index}]")
    if kind == "string":
        low, high = schema.get("minLength", 0), schema.get("maxLength", 1000000)
        if len(value) < low or len(value) > high:
            bound = f"at least {low}" if len(value) < low else f"at most {high}"
            raise ValueError(f"{path}: {len(value)} characters given; this field accepts {bound}")
        if schema.get("pattern") and not re.search(schema["pattern"], value):
            raise ValueError(f"{path}: unsupported string format")
    if kind in ("integer", "number"):
        low, high = schema.get("minimum", float("-inf")), schema.get("maximum", float("inf"))
        if value < low or value > high:
            bound = f"at least {low}" if value < low else f"at most {high}"
            raise ValueError(f"{path}: {value} given; this field accepts {bound}")


def tools(request_adapter=False):
    result = deepcopy((REQUEST_CONTRACT if request_adapter else CONTRACT)["tools"])
    for tool in result:
        tool["inputSchema"]["properties"]["operation_id"] = {
            "type": "string", "pattern": "^[A-Za-z0-9_-]{8,128}$",
            "description": "Retry identifier returned after transport failure. Reuse only with identical arguments to avoid a second debit. Omit for a new search."}
    return result


async def handle(body, api_key, call, request_adapter=False):
    contract = REQUEST_CONTRACT if request_adapter else CONTRACT
    method, request_id = body.get("method"), body.get("id")
    params = body.get("params") or {}
    def response(value):
        return {"jsonrpc": "2.0", "id": request_id, "result": value}
    def error(code, message):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    if method == "initialize":
        return response({"protocolVersion": "2025-03-26", "serverInfo": {"name": contract["server_name"], "version": contract["semantic_version"]}, "capabilities": {"tools": {"listChanged": False}, "resources": {}}, "instructions": contract["instructions"]})
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return response({})
    if method == "tools/list":
        return response({"tools": tools(request_adapter)})
    if method == "resources/list":
        return response({"resources": [{"uri": "signalbase://recruiting/v3/guide", "name": "Recruiting search concepts and examples", "mimeType": "application/json"}]})
    if method == "resources/read":
        if params.get("uri") != "signalbase://recruiting/v3/guide":
            return error(-32602, "Unknown resource")
        return response({"contents": [{"uri": params["uri"], "mimeType": "application/json", "text": json.dumps({k: contract[k] for k in ("semantic_version", "concepts", "examples")}, separators=(",", ":"))}]})
    if method != "tools/call":
        return error(-32601, "Unknown method")
    tool = next((tool for tool in tools(request_adapter) if tool["name"] == params.get("name")), None)
    if not tool:
        return error(-32602, "Unknown recruiting tool; use tools/list")
    arguments = deepcopy(params.get("arguments", {}))
    try:
        validate(arguments, tool["inputSchema"])
        if not api_key:
            raise ValueError("API key required")
    except (ValueError, KeyError, TypeError) as exc:
        return error(-32602, str(exc))
    operation_id = arguments.pop("operation_id", None) or uuid.uuid4().hex
    try:
        result = await asyncio.wait_for(call(tool["name"], arguments, api_key, operation_id), timeout=50)
    except Exception:
        payload = {"execution_status": "failed", "error": "Transport did not complete; this is not an empty search. Retry identical arguments with operation_id.", "operation_id": operation_id, "usage": {"credits_known": False}}
        return response({"isError": True, "content": [{"type": "text", "text": json.dumps(payload, separators=(",", ":"))}]})
    payload = result.get("data", result)
    if not isinstance(payload, dict):
        return error(-32603, "Recruiting service returned an invalid result")
    payload = {**payload, "operation_id": operation_id, "api_usage": result.get("meta", {})}
    failed = result.get("success") is False or payload.get("execution_status") == "failed"
    return response({"isError": failed, "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]})
