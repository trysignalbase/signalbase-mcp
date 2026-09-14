# Signalbase MCP Server — Overview

> Compatibility: the existing endpoint preserves full payloads, historical defaults and accepted inputs while improving matching automatically. HR MCP `/v2` enables compact responses, open hiring searches, grouped companies and country breakdowns by default. Both keep `data` rows.

## What It Does

The Signalbase MCP server is a Model Context Protocol proxy that sits between AI agents (Claude, Cursor, etc.) and the [Signalbase API](https://docs.trysignalbase.com). It exposes six tools that cover the full Signalbase data surface:

| Tool | API Endpoint | Cost |
|------|-------------|------|
| `search_funding_signals` | `GET /signals/funding` | 1 credit per search; `count=true` free |
| `search_acquisition_signals` | `GET /signals/acquisitions` | 1 credit per search; `count=true` free |
| `search_job_change_signals` | `GET /signals/job-changes` | 1 credit per search; `count=true` free |
| `search_hiring_signals` | `GET /signals/hiring` | 1 credit per search; `count=true` free |
| `search_investors` | `GET /signals/investors` | 1 credit per search; `count=true` free |
| `search_companies` | `GET /companies` | 1 credit per search; `count=true` free |

## How It Works

1. **Client** (Claude Desktop, Cursor, Claude Code CLI) sends an MCP JSON-RPC request to the server
2. **Server** extracts the `Authorization: Bearer <key>` header from the request
3. **Server** maps the MCP `tools/call` to the correct Signalbase API endpoint
4. **Server** pops the Worker-only `verbose` flag, joins list-valued arguments with commas, and forwards everything else verbatim as query parameters to `https://www.trysignalbase.com/api/v2` (the API returns HTTP 400 for unknown parameters)
5. **Server** returns the API response as MCP tool result content — trimmed by default (see below)

## Authentication

The server does **not** store any API keys. Clients pass their Signalbase API key via the `Authorization` header on every MCP request. The server extracts it and forwards it to the upstream API.

Get your API key at: [trysignalbase.com/workspace/api](https://www.trysignalbase.com/workspace/api)

## Runtime

- **Cloudflare Workers** with Python (Pyodide)
- No pip packages — uses only Python standard library + JS interop
- Deployed globally on Cloudflare's edge network for low latency

## Credit System

- Every **executed search costs 1 credit**, including searches that return 0 rows and each additional page.
- `count=true` is **free on all six tools** and returns only the total count. Use it to size a query before paying for it.
- A `company_domain` / `company_linkedin_url` list (up to 50 entries) is one search — one credit for the whole pool.
- Requests rejected with HTTP 400 (unknown parameter, unknown country value) cost nothing.

## Countries

`countries` and `exclude_countries` (and hiring's `job_countries` / `company_countries`) accept ISO 3166-1 alpha-2 codes (`US,GB,DE`), English names (`Sweden`), or region shortcuts `EU`, `EUROPE`, `DACH`, `BENELUX`, `NORDICS`, `CEE`, `WE`, `NORTH_AMERICA`, `LATAM`. Unknown values return HTTP 400 with a hint.

## Response (example with `verbose=false`) Trimming

By default the server trims API payloads to save tokens: `descriptionText`, `companyDescription`, `description`, `postContent` and `personHeadline` are cut to 300 characters (+ `…`), logo/image URL fields (`companyLogo`, `companyLogoUrl`, `logoUrl`, `logo_url`, `image`) are dropped, JSON is compact, and `_meta: {"trimmed": true, "hint": "pass verbose=true for full text"}` is added. Links (`jobUrl`, `sources`, LinkedIn URLs, `companyWebsite`) and `validThrough` are always kept. Pass `verbose=true` to any tool for the full, indented payload.

## Prompts

`prompts/list` exposes `funded-and-hiring` (arguments `geography`, `max_employees`, `department`, `window`), `market-scan`, `investor-research`, `sales-prospecting` and `leadership-changes`.
