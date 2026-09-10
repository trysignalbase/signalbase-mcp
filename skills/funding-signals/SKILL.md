---
name: signalbase-funding-signals
description: Use when the user asks about funding rounds, startup fundraising, venture capital deals, recently funded companies, or Series A/B/C rounds. Searches real-time funding intelligence.
argument-hint: "[sector, geography, round type, or company name]"
---

# Funding Signals Skill

> Compatibility: the existing endpoint preserves full payloads, historical defaults and accepted inputs while improving matching automatically. HR MCP `/v2` enables compact responses, open hiring searches, grouped companies and country breakdowns by default. Both keep `data` rows.

## Tool: `search_funding_signals`
**Endpoint:** `GET /signals/funding` | **Cost:** 1 credit per executed search (0 rows still cost); `count=true` free

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default 1) |
| `limit` | integer | Results per page, max 50 |
| `search` | string | Company name or keywords |
| `countries` | string | ISO codes, names, or regions: `US,GB`, `Sweden`, `EU`, `NORDICS`, `DACH` (with `filter_version=2`: unknown → 400) |
| `exclude_countries` | string | Same values, excluded |
| `categories` | string | Pipe-separated LinkedIn industries: `Software Development\|Financial Services` |
| `subcategories` | string | Comma-separated multi-select: `ai,fintech,saas` |
| `round` | string | Comma-separated: `Seed,Series A` |
| `amount_min` / `amount_max` | integer | Round amount bounds, whole USD |
| `employee_count_min` / `employee_count_max` | integer | Company headcount bounds (e.g. `employee_count_max=10`) |
| `founded_year_min` / `founded_year_max` | integer | Founded year bounds |
| `company_domain` | string | Comma-separated domains, up to 50, strict match — one credit for the list |
| `company_linkedin_url` | string | Comma-separated LinkedIn company URLs, up to 50 |
| `dateFrom` / `dateTo` | string | YYYY-MM-DD |
| `date_preset` | string | `last_30d`, `last_90d`, `this_quarter`, etc. |
| `count` | boolean | Only the total count (free) |
| `verbose` | boolean | Full untrimmed payload (Worker-only) |

## Example Workflows

### Micro companies in Europe that raised in the last 90 days (size free, then pull)
```json
{"countries": "EU", "employee_count_max": 10, "date_preset": "last_90d", "count": true}
```
```json
{"countries": "EU", "employee_count_max": 10, "date_preset": "last_90d", "limit": 50}
```
Then pass the website domains to `search_hiring_signals` as `company_domain` (≤50 per call).

### Recently funded AI startups in the US
```json
{"subcategories": "ai", "countries": "US", "date_preset": "last_30d"}
```

### Series A rounds in fintech (last quarter)
```json
{"subcategories": "fintech", "round": "Series A", "date_preset": "last_quarter"}
```

### Rounds of $10M+ in the Nordics
```json
{"countries": "NORDICS", "amount_min": 10000000, "date_preset": "last_90d", "limit": 50}
```

## Gotchas

- Every executed search costs 1 credit even with 0 rows — always `count=true` first
- `categories` uses **pipe** `|` as delimiter, not comma; `subcategories` uses **comma**
- Amounts are whole USD integers: `15000000` = $15M
- `date_preset` overrides `dateFrom`/`dateTo`
- Round types are title-case: `Series A`, not `series a`
- Descriptions are truncated to 300 chars only with `verbose=false`
