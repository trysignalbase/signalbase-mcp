# Signalbase MCP Server

A Model Context Protocol (MCP) server that proxies the [Signalbase API](https://docs.trysignalbase.com), deployed on Cloudflare Workers. Gives AI agents (Claude, Cursor, etc.) access to real-time funding signals, acquisition signals, job change signals, hiring data, investor profiles, and company search.

## Tools

| Tool | Description | Cost |
|------|-------------|------|
| `search_funding_signals` | Search funding rounds by sector, geography, headcount, round type, date | 1 credit per search; `count=true` free |
| `search_acquisition_signals` | Track M&A activity and acquisition indicators | 1 credit per search; `count=true` free |
| `search_job_change_signals` | Monitor leadership and key-hire role changes | 1 credit per search; `count=true` free |
| `search_hiring_signals` | Find live job postings by role, department, company HQ, domain list | 1 credit per search; `count=true` free |
| `search_investors` | Search VCs, angels, PE firms with portfolio data | 1 credit per search; `count=true` free |
| `search_companies` | Browse company profiles with headcount and growth | 1 credit per search; `count=true` free |

Every tool also accepts `verbose` (Worker-only, never forwarded to the API). By default responses are trimmed: long text fields are cut to 300 characters, logo/image URLs are dropped, and `_meta.trimmed=true` is added. Links (`jobUrl`, `sources`, LinkedIn URLs, `companyWebsite`) and `validThrough` are always kept. Pass `verbose=true` for the full payload.

### Filters common to every tool

| Parameter | Notes |
|-----------|-------|
| `countries` / `exclude_countries` | ISO-2 codes (`US,GB`), English names (`Sweden`), or region shortcuts `EU`, `EUROPE`, `DACH`, `BENELUX`, `NORDICS`, `CEE`, `WE`, `NA`, `LATAM`. Unknown values return HTTP 400. |
| `company_domain` / `company_linkedin_url` | Comma-separated lists, up to 50 per call, strict canonical match — one credit for the whole list (funding, acquisitions, job changes, hiring). |
| `count` | `true` returns only the total count. Free on all six tools. |
| `page`, `limit`, `search`, `dateFrom`, `dateTo`, `date_preset` | Pagination, free text and dates (`date_preset` overrides the absolute dates). |

Per-tool parameter tables live in [`docs/`](./docs/overview.md).

## Authentication

Get your API key from the [Signalbase dashboard](https://www.trysignalbase.com/workspace/api). Pass it as a Bearer token in the `Authorization` header of every MCP request.

## Setup

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "signalbase": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://mcp.trysignalbase.com",
        "--header",
        "Authorization: Bearer YOUR_API_KEY"
      ]
    }
  }
}
```

### Claude Code CLI

```bash
claude mcp add signalbase \
  --transport http \
  --url https://mcp.trysignalbase.com \
  --header "Authorization: Bearer YOUR_API_KEY"
```

### Cursor

Create or edit `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "signalbase": {
      "url": "https://mcp.trysignalbase.com",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

### Generic MCP Client

Send a POST request with a JSON-RPC 2.0 body:

```bash
curl -X POST https://mcp.trysignalbase.com \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "search_funding_signals",
      "arguments": {
        "subcategories": "ai",
        "countries": "US",
        "date_preset": "last_30d",
        "limit": 5
      }
    }
  }'
```

## Example Workflows

### Funded pool → who is hiring (2–3 credits total)
1. Size it for free: `search_funding_signals` with `countries=EU`, `employee_count_max=10`, `date_preset=last_90d`, `count=true`
2. Pull the pool: same filters with `limit=50`
3. Collect each row's `companyWebsite` domain
4. One credit per 50 domains: `search_hiring_signals` with `company_domain=<up to 50 domains>`, `departments=sales`, `limit=100`, `sort_by=date_posted` — rows carry `jobUrl` and `validThrough`; expired postings are excluded by default
5. Independent lane: `search_hiring_signals` with `company_countries=EU`, `team_size=1-10`, `departments=sales`

The `funded-and-hiring` prompt (`prompts/get`) scripts this with arguments `geography`, `max_employees`, `department`, `window`.

### Market research — recently funded AI startups
```json
{"name": "search_funding_signals", "arguments": {"subcategories": "ai", "date_preset": "last_30d", "round": "Seed,Series A"}}
```

### Investor lookup
```json
{"name": "search_investors", "arguments": {"categories": "vc", "countries": "US", "search": "seed stage"}}
```

### Leadership change monitoring
```json
{"name": "search_job_change_signals", "arguments": {"seniorities": "c_level,vp", "departments": "engineering"}}
```

## Credit Usage

- Every **executed search costs 1 credit**, including searches that return 0 rows and every extra page.
- `count=true` is **free on all six tools** — use it to size a query before spending a credit.
- A `company_domain` / `company_linkedin_url` list of up to 50 entries is a single search (1 credit); never loop one call per company.
- Unknown parameters or unknown country values return HTTP 400 and cost nothing.

## Hiring coverage

The hiring index is ~84% US job locations. For European (or any non-US) targets, do not filter by job location alone — use `company_countries=<region>` (+ `team_size`) or the funded-pool workflow above (`company_domain` list). Expired postings are excluded by default; pass `include_expired=true` for historical analysis.

## Rate Limits

Standard Signalbase API rate limits apply. If you receive a 429 response, wait and retry.

## Development

```bash
py -3.13 -m pytest tests -q          # unit tests (JS runtime stubbed in tests/conftest.py)
py -3.13 -m py_compile src/entry.py
npx wrangler dev                      # local worker on http://127.0.0.1:8787
MCP=http://127.0.0.1:8787 KEY=... bash tests/smoke.sh   # live smoke test (spends ~4 credits)
```

## Deployment

### Connect to Cloudflare (recommended)

1. Push this repo to GitHub
2. In the [Cloudflare dashboard](https://dash.cloudflare.com), go to **Workers & Pages** → **Create** → **Connect to Git**
3. Select the repo and deploy — Cloudflare auto-detects `wrangler.toml`
4. Every push to `main` triggers a new deploy

### Manual deploy

```bash
npx wrangler deploy
```

### Custom domain

Configure in the Cloudflare dashboard under Workers → your worker → Settings → Domains & Routes. Or uncomment the `[[routes]]` section in `wrangler.toml`.

## Links

- [Signalbase API Docs](https://docs.trysignalbase.com)
- [Get API Key](https://www.trysignalbase.com/workspace/api)
- [Signalbase Dashboard](https://www.trysignalbase.com/personal/account)
- [Cloudflare Workers Python Docs](https://developers.cloudflare.com/workers/languages/python/)
