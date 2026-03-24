# Signalbase MCP Server — Overview

## What It Does

The Signalbase MCP server is a Model Context Protocol proxy that sits between AI agents (Claude, Cursor, etc.) and the [Signalbase API](https://docs.trysignalbase.com). It exposes six tools that cover the full Signalbase data surface:

| Tool | API Endpoint | Cost |
|------|-------------|------|
| `search_funding_signals` | `GET /signals/funding` | 1 credit |
| `search_acquisition_signals` | `GET /signals/acquisitions` | 1 credit |
| `search_job_change_signals` | `GET /signals/job-changes` | 1 credit |
| `search_hiring_signals` | `GET /signals/hiring` | 1 credit |
| `search_investors` | `GET /signals/investors` | 1 credit |
| `search_companies` | `GET /companies` | 1 credit |

## How It Works

1. **Client** (Claude Desktop, Cursor, Claude Code CLI) sends an MCP JSON-RPC request to the server
2. **Server** extracts the `Authorization: Bearer <key>` header from the request
3. **Server** maps the MCP `tools/call` to the correct Signalbase API endpoint
4. **Server** forwards the API key and query parameters to `https://www.trysignalbase.com/api/v2`
5. **Server** returns the API response as MCP tool result content

## Authentication

The server does **not** store any API keys. Clients pass their Signalbase API key via the `Authorization` header on every MCP request. The server extracts it and forwards it to the upstream API.

Get your API key at: [trysignalbase.com/workspace/api](https://www.trysignalbase.com/workspace/api)

## Runtime

- **Cloudflare Workers** with Python (Pyodide)
- No pip packages — uses only Python standard library + JS interop
- Deployed globally on Cloudflare's edge network for low latency

## Credit System

Each API call consumes **1 credit** from your Signalbase plan. Two tools support a free `count=true` mode that returns only the total result count without consuming credits:
- `search_hiring_signals`
- `search_companies`

Use `count=true` to preview result sizes before pulling full data.
