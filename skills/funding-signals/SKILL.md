---
name: signalbase-funding-signals
description: Use when the user asks about funding rounds, startup fundraising, venture capital deals, recently funded companies, or Series A/B/C rounds. Searches real-time funding intelligence.
argument-hint: "[sector, geography, round type, or company name]"
---

# Funding Signals Skill

## Tool: `search_funding_signals`
**Endpoint:** `GET /signals/funding` | **Cost:** 1 credit

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default 1) |
| `limit` | integer | Results per page, max 50 |
| `search` | string | Company name or keywords |
| `countries` | string | Comma-separated: `US,GB` or `NORDICS` |
| `categories` | string | Pipe-separated LinkedIn industries: `Software Development\|Financial Services` |
| `subcategories` | string | Comma-separated: `ai,fintech,saas` |
| `round` | string | Comma-separated: `Seed,Series A` |
| `dateFrom` | string | YYYY-MM-DD |
| `dateTo` | string | YYYY-MM-DD |
| `date_preset` | string | `last_30d`, `this_quarter`, etc. |

## Example Workflows

### Recently funded AI startups in the US
```json
{"subcategories": "ai", "countries": "US", "date_preset": "last_30d"}
```

### Series A rounds in fintech (last quarter)
```json
{"subcategories": "fintech", "round": "Series A", "date_preset": "last_quarter"}
```

### Large rounds ($10M+) — sort through results by fundingAmount
```json
{"date_preset": "last_7d", "limit": 50}
```

## Gotchas

- `categories` uses **pipe** `|` as delimiter, not comma
- `subcategories` uses **comma** as delimiter
- Amounts are whole USD integers: `15000000` = $15M
- `date_preset` overrides `dateFrom`/`dateTo`
- Round types are title-case: `Series A`, not `series a`
