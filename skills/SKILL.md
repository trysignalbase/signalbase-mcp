---
name: signalbase-mcp
description: Use when the user asks about funding signals, acquisition signals, job change signals, hiring signals, investors, or company data from Signalbase. Also use when the user needs to set up or configure the Signalbase MCP server.
argument-hint: "[query or topic to research]"
---

# Signalbase MCP Server — Skills Overview

This MCP server provides access to the Signalbase API for real-time business intelligence.

## Available Tools

| Tool | What It Does | Cost |
|------|-------------|------|
| `search_funding_signals` | Find recently funded companies by round type, sector, geography | 1 credit |
| `search_acquisition_signals` | Track M&A activity and acquisition indicators | 1 credit |
| `search_job_change_signals` | Monitor C-suite and leadership role changes | 1 credit |
| `search_hiring_signals` | Find companies actively hiring by role, department, location | 1 credit |
| `search_investors` | Search VCs, angels, PE firms with AUM and portfolio data | 1 credit |
| `search_companies` | Browse company profiles with headcount, growth, industry | 1 credit |

## Setup

### MCP Endpoint
```
https://signalbase-mcp.<your-subdomain>.workers.dev
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
        "https://signalbase-mcp.<your-subdomain>.workers.dev",
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
      "url": "https://signalbase-mcp.<your-subdomain>.workers.dev",
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

1. **Use `count=true` first** on hiring and companies to preview result sizes without spending credits
2. **`date_preset` overrides `dateFrom`/`dateTo`** — use relative dates like `last_30d` for convenience
3. **`categories` vs `subcategories`** — categories = LinkedIn industry labels (pipe-separated), subcategories = Signalbase categories (comma-separated)
4. **Countries** — use ISO alpha-2 codes (US, GB, DE) or region shortcuts (CEE, NORDICS, NA)
5. **Amounts** — all funding amounts are whole USD integers (5000000 = $5M)
