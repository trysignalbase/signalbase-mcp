# Signalbase MCP Server

Real-time business intelligence for AI agents. Access funding signals, acquisition signals, job change tracking, hiring data, investor profiles, and company search through the Model Context Protocol.

## What You Can Do

- **Track funding rounds** — Find companies that just raised Seed, Series A, B, C+ rounds. Filter by sector, geography, amount, and date.
- **Monitor M&A activity** — Discover acquisition targets and track deal flow with signal scores and indicators.
- **Follow leadership changes** — Get notified when CTOs, VPs, and other executives change companies. Filter by role, department, and seniority.
- **Analyze hiring trends** — See which companies are actively hiring, by role, location, team size, and applicant volume.
- **Research investors** — Search VCs, angels, PE firms, and accelerators. View AUM, check sizes, portfolio companies, and investment focus.
- **Browse companies** — Search 100K+ company profiles with headcount, growth metrics, industry, and founding details.

## Tools

| Tool | Description | Credits |
|------|-------------|---------|
| `search_funding_signals` | Funding round search | 1 |
| `search_acquisition_signals` | M&A signal search | 1 |
| `search_job_change_signals` | Leadership change search | 1 |
| `search_hiring_signals` | Job posting search | 1 (0 with count) |
| `search_investors` | Investor database search | 1 |
| `search_companies` | Company profile search | 1 (0 with count) |

## Authentication

Requires a Signalbase API key passed as `Authorization: Bearer <key>`. Get yours at [trysignalbase.com](https://www.trysignalbase.com/workspace/api).

## Runtime

Python on Cloudflare Workers (Pyodide). No external dependencies. Deployed globally on Cloudflare's edge network.
