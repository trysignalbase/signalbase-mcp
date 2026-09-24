"""Thin monitoring transport. Tool definitions and execution live in the app contract.

Same shape as recruiting_v3: validate the agent's arguments against the
generated contract, then hand the call to the app. The differences are
deliberate and all about these being the fleet's first write tools.

  * operation_id is required machinery, not an optimisation. A transport
    timeout on create_monitor is ambiguous — the monitor may exist. The app
    reserves against (team, endpoint, operation_id) before executing, so
    retrying with the same id replays the stored result instead of creating a
    second monitor. The failure payload therefore tells the agent to retry
    with the SAME id and never to invent a new one.

  * The contract hash travels on every call (X-Monitoring-Contract, added by
    entry.py), so a Worker release that has drifted from the app cannot drive
    writes against tool definitions the user never saw.
"""
import asyncio
import json
import uuid
from copy import deepcopy
from mcp_schema import validate
from monitoring_contract import CONTRACT

RESOURCE_URI = "signalbase://monitoring/v3/guide"


def tools():
    result = deepcopy(CONTRACT["tools"])
    for tool in result:
        tool["inputSchema"]["properties"]["operation_id"] = {
            "type": "string", "pattern": "^[A-Za-z0-9_-]{8,128}$",
            "description": "Retry identifier. After a transport failure, retry the identical call with the SAME operation_id: the change is applied at most once, and a replay returns the original result. Never send a new id to retry, and never reuse an id for different arguments. Omit for a new action."}
    return result


async def handle(body, api_key, call):
    method, request_id = body.get("method"), body.get("id")
    params = body.get("params") or {}

    def response(value):
        return {"jsonrpc": "2.0", "id": request_id, "result": value}

    def error(code, message):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    if method == "initialize":
        return response({"protocolVersion": "2025-03-26", "serverInfo": {"name": CONTRACT["server_name"], "version": CONTRACT["semantic_version"]}, "capabilities": {"tools": {"listChanged": False}, "resources": {}}, "instructions": CONTRACT["instructions"]})
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return response({})
    if method == "tools/list":
        return response({"tools": tools()})
    if method == "resources/list":
        return response({"resources": [{"uri": RESOURCE_URI, "name": "Monitoring concepts and examples", "mimeType": "application/json"}]})
    if method == "resources/read":
        if params.get("uri") != RESOURCE_URI:
            return error(-32602, "Unknown resource")
        return response({"contents": [{"uri": params["uri"], "mimeType": "application/json", "text": json.dumps({k: CONTRACT[k] for k in ("semantic_version", "concepts", "examples")}, separators=(",", ":"))}]})
    if method != "tools/call":
        return error(-32601, "Unknown method")

    tool = next((tool for tool in tools() if tool["name"] == params.get("name")), None)
    if not tool:
        return error(-32602, "Unknown monitoring tool; use tools/list")
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
        # Ambiguous by nature: the write may or may not have landed. Say so, and
        # pin the retry to this operation_id so it cannot double-apply.
        payload = {"execution_status": "failed",
                   "error": "Transport did not complete. This does not mean the change failed — retry the identical call with the same operation_id to apply it at most once, or read the monitor back to check.",
                   "operation_id": operation_id}
        return response({"isError": True, "content": [{"type": "text", "text": json.dumps(payload, separators=(",", ":"))}]})

    payload = result.get("data")
    if not isinstance(payload, dict):
        # A structured app error (bad arguments, unknown monitor, conflicting
        # operation_id) carries its message; surface it rather than a generic.
        message = result.get("error") if isinstance(result, dict) else None
        failure = {"execution_status": "failed",
                   "error": message or "Monitoring service returned an invalid result",
                   "code": result.get("code") if isinstance(result, dict) else None,
                   "operation_id": operation_id}
        return response({"isError": True, "content": [{"type": "text", "text": json.dumps(failure, separators=(",", ":"))}]})

    payload = {**payload, "operation_id": operation_id, "api_usage": result.get("meta", {})}
    failed = result.get("success") is False or payload.get("execution_status") == "failed"
    return response({"isError": failed, "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]})
