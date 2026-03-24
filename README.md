# Signalbase MCP Server

A Model Context Protocol (MCP) server that proxies the [Signalbase API](https://docs.trysignalbase.com), deployed on Cloudflare Workers. Gives AI agents (Claude, Cursor, etc.) access to real-time funding signals, acquisition signals, job change signals, hiring data, investor profiles, and company search.

## Tools

| Tool | Description | Cost |
|------|-------------|------|
| `search_funding_signals` | Search funding rounds by sector, geography, round type, date | 1 credit |
| `search_acquisition_signals` | Track M&A activity and acquisition indicators | 1 credit |
| `search_job_change_signals` | Monitor leadership and key-hire role changes | 1 credit |
| `search_hiring_signals` | Find open job postings by role, department, location | 1 credit |
| `search_investors` | Search VCs, angels, PE firms with portfolio data | 1 credit |
| `search_companies` | Browse company profiles with headcount and growth | 1 credit |

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

### Market research — recently funded AI startups
```json
{"name": "search_funding_signals", "arguments": {"subcategories": "ai", "date_preset": "last_30d", "round": "Seed,Series A"}}
```

### Sales prospecting — funded companies that are hiring
1. `search_funding_signals` with `date_preset=last_30d` and your target `subcategories`
2. `search_hiring_signals` with matching `subcategories` and relevant `departments`
3. Cross-reference to find companies with both budget and hiring intent

### Investor lookup
```json
{"name": "search_investors", "arguments": {"categories": "vc", "countries": "US", "search": "seed stage"}}
```

### Leadership change monitoring
```json
{"name": "search_job_change_signals", "arguments": {"seniorities": "c_level,vp", "departments": "engineering"}}
```

## Credit Usage

- Each tool call costs **1 credit** from your Signalbase plan
- `search_hiring_signals` and `search_companies` support `count=true` which returns only the total count with **0 credits**
- Use `count=true` to preview result sizes before pulling full data

## Rate Limits

Standard Signalbase API rate limits apply. If you receive a 429 response, wait and retry.

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
