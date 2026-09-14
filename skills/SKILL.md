---
name: signalbase-mcp
description: Use when the user asks about funding signals, acquisition signals, job change signals, hiring signals, investors, or company data from Signalbase. Also use when the user needs to set up or configure the Signalbase MCP server.
argument-hint: "[query or topic to research]"
---

# Signalbase MCP Server — Skills Overview

> Compatibility: the existing endpoint preserves full payloads, historical defaults and accepted inputs while improving matching automatically. HR MCP `/v2` enables compact responses, open hiring searches, grouped companies and country breakdowns by default. Both keep `data` rows.

This MCP server provides access to the Signalbase API for real-time business intelligence.

## Available Tools

| Tool | What It Does | Cost |
|------|-------------|------|
| `search_funding_signals` | Find recently funded companies by round type, sector, geography, headcount | 1 credit per search; `count=true` free |
| `search_acquisition_signals` | Track M&A activity and acquisition indicators | 1 credit per search; `count=true` free |
| `search_job_change_signals` | Monitor C-suite and leadership role changes | 1 credit per search; `count=true` free |
| `search_hiring_signals` | Find companies actively hiring by role, department, company HQ, domain list | 1 credit per search; `count=true` free |
| `search_investors` | Search VCs, angels, PE firms with AUM and portfolio data | 1 credit per search; `count=true` free |
| `search_companies` | Browse company profiles with headcount, growth, industry | 1 credit per search; `count=true` free |

## Setup

### MCP Endpoint
```
https://mcp.trysignalbase.com
```

### Transport
HTTP POST with JSON-RPC 2.0

### Authentication
Pass your Signalbase API key as:
```
Authorization: Bearer YOUR_SIGNALBASE_API_KEY
```

Get your key at: https://www.trysignalbase.com/workspace/api

### Claude Desktop Config (claude_desktop_config.json)
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

### Cursor Config (.cursor/mcp.json)
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

## Domain-Specific Skills

- [Funding Signals](./funding-signals/SKILL.md) — search_funding_signals
- [Acquisition Signals](./acquisition-signals/SKILL.md) — search_acquisition_signals
- [Job Change Signals](./job-change-signals/SKILL.md) — search_job_change_signals
- [Hiring Signals](./hiring-signals/SKILL.md) — search_hiring_signals
- [Investors](./investors/SKILL.md) — search_investors
- [Companies](./companies/SKILL.md) — search_companies

## Key Tips

1. **Credits** — every executed search costs 1 credit, even with 0 rows. `count=true` is free on all six tools: size first, then pay once with a large `limit`.
2. **Countries** — ISO alpha-2 codes (US, GB, DE), English names (Sweden), or region shortcuts EU, EUROPE, DACH, BENELUX, NORDICS, CEE, WE, NORTH_AMERICA, LATAM. With `filter_version=2`, unknown values return HTTP 400; the classic endpoint continues accepting legacy literals.
3. **Hiring is US-heavy (~84% US job locations)** — for European targets use `company_countries=EU` + `team_size`, or a `company_domain` list from a funding search (up to 50 domains = one credit). Historical postings are included by default; use `include_expired=false` for open roles.
4. **`date_preset` overrides `dateFrom`/`dateTo`** — use relative dates like `last_90d`
5. **`categories` vs `subcategories`** — categories = LinkedIn industry labels (pipe-separated), subcategories = Signalbase categories (comma-separated multi-select)
6. **Amounts** — all funding amounts are whole USD integers (5000000 = $5M)
7. **`verbose=true`** — responses are full by default; opt into trimming with `verbose=false` (300-char text, no logos); pass `verbose=true` when you need full descriptions. It never reaches the API.
8. **Prompt `funded-and-hiring`** — scripts the funded-pool → hiring-by-domain workflow (arguments geography, max_employees, department, window).
