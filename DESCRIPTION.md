# Signalbase MCP Server

> Compatibility: the existing endpoint preserves full payloads, historical defaults and accepted inputs while improving matching automatically. HR MCP `/v2` enables compact responses, open hiring searches, grouped companies and country breakdowns by default. Both keep `data` rows.

Real-time business intelligence for AI agents. Access funding signals, acquisition signals, job change tracking, hiring data, investor profiles, and company search through the Model Context Protocol.

## What You Can Do

- **Track funding rounds** — Find companies that just raised Seed, Series A, B, C+ rounds. Filter by sector, geography (ISO codes, names, or regions like EU / NORDICS / DACH), headcount, amount, and date.
- **Monitor M&A activity** — Discover acquisition targets and track deal flow with signal scores and indicators.
- **Follow leadership changes** — Get notified when CTOs, VPs, and other executives change companies. Filter by role, department, seniority, geography, and company.
- **Analyze hiring trends** — See which companies are actively hiring, by role, department, company HQ, company size, and applicant volume — or check a list of up to 50 company domains for open roles in one call. Historical postings are included by default; use `include_expired=false` for open roles.
- **Research investors** — Search VCs, angels, PE firms, and accelerators. View AUM, check sizes, portfolio companies, and investment focus.
- **Browse companies** — Search 100K+ company profiles with headcount, growth metrics, industry, and founding details.

## Tools

| Tool | Description | Credits |
|------|-------------|---------|
| `search_funding_signals` | Funding round search | 1 per search (0 with count=true) |
| `search_acquisition_signals` | M&A signal search | 1 per search (0 with count=true) |
| `search_job_change_signals` | Leadership change search | 1 per search (0 with count=true) |
| `search_hiring_signals` | Job posting search | 1 per search (0 with count=true) |
| `search_investors` | Investor database search | 1 per search (0 with count=true) |
| `search_companies` | Company profile search | 1 per search (0 with count=true) |

Every executed search costs 1 credit, even when it returns 0 rows. `count=true` is free on every tool. Responses are full by default; opt into trimming with `verbose=false` (long text cut to 300 characters, logos dropped); pass `verbose=true` for the full payload.

## Authentication

Requires a Signalbase API key passed as `Authorization: Bearer <key>`. Get yours at [trysignalbase.com](https://www.trysignalbase.com/workspace/api).

## Runtime

Python on Cloudflare Workers (Pyodide). No external dependencies. Deployed globally on Cloudflare's edge network.
