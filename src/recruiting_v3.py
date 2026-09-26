"""Thin v3 transport. Business definitions and execution live in the app contract."""
import asyncio
import json
import uuid
from copy import deepcopy
from mcp_schema import validate  # re-exported: importers use recruiting_v3.validate
from recruiting_contract import CONTRACT, REQUEST_CONTRACT


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
