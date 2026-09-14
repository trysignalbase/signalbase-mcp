---
name: signalbase-investors
description: Use when the user asks about venture capital firms, angel investors, PE firms, accelerators, investor portfolios, AUM, check sizes, or wants to find investors in a specific sector or geography.
argument-hint: "[investor type, sector focus, or geography]"
---

# Investors Skill

> Compatibility: the existing endpoint preserves full payloads, historical defaults and accepted inputs while improving matching automatically. HR MCP `/v2` enables compact responses, open hiring searches, grouped companies and country breakdowns by default. Both keep `data` rows.

## Tool: `search_investors`
**Endpoint:** `GET /signals/investors` | **Cost:** 1 credit per executed search (0 rows still cost); `count=true` free

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default 1) |
| `limit` | integer | Results per page, max 50 |
| `search` | string | Investor name or description |
| `countries` | string | ISO codes, names, or regions: `US,GB`, `EU`, `NORDICS` (with `filter_version=2`: unknown → 400) |
| `exclude_countries` | string | Same values, excluded |
| `categories` | string | Comma-separated investor types |
| `type` | string | Single investor type (alternative to `categories`) |
| `headquarters` | string | Free-text HQ match, e.g. `London` |
| `ticket_size_min` / `ticket_size_max` | integer | Typical check size bounds, whole USD |
| `count` | boolean | Only the total count (free) |
| `verbose` | boolean | Full untrimmed payload (Worker-only) |

## Investor Types

```
vc, angel, pe, corporate, government, accelerator,
family_office, hedge_fund, crowdfunding
```

## Example Workflows

### Count seed-stage VCs in the Nordics (free)
```json
{"categories": "vc", "countries": "NORDICS", "ticket_size_max": 2000000, "count": true}
```

### Find seed-stage VCs in the US
```json
{"categories": "vc", "countries": "US", "search": "seed"}
```

### Find European angel investors
```json
{"categories": "angel", "countries": "EU"}
```

### Search for a specific firm
```json
{"search": "Sequoia Capital"}
```

## Gotchas

- Every executed search costs 1 credit even with 0 rows — always `count=true` first
- `categories` on investors = **investor types** (vc, angel), NOT industry categories
- `aum` is in whole USD: `85000000000` = $85B
- `typicalCheckSize` has `min` and `max` in USD
- `investmentFocus` and `investmentStage` are arrays in the response
- `activelyInvesting` = boolean indicating if currently making deals
- `description` is truncated to 300 chars only with `verbose=false`
