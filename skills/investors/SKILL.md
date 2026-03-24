---
name: signalbase-investors
description: Use when the user asks about venture capital firms, angel investors, PE firms, accelerators, investor portfolios, AUM, check sizes, or wants to find investors in a specific sector or geography.
argument-hint: "[investor type, sector focus, or geography]"
---

# Investors Skill

## Tool: `search_investors`
**Endpoint:** `GET /signals/investors` | **Cost:** 1 credit

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default 1) |
| `limit` | integer | Results per page, max 50 |
| `search` | string | Investor name or description |
| `countries` | string | Comma-separated country codes |
| `categories` | string | Comma-separated investor types |

## Investor Types

```
vc, angel, pe, corporate, government, accelerator,
family_office, hedge_fund, crowdfunding
```

## Example Workflows

### Find seed-stage VCs in the US
```json
{"categories": "vc", "countries": "US", "search": "seed"}
```

### Find European angel investors
```json
{"categories": "angel", "countries": "GB,DE,FR,NL,SE"}
```

### Search for a specific firm
```json
{"search": "Sequoia Capital"}
```

### Find accelerators globally
```json
{"categories": "accelerator", "limit": 50}
```

## Gotchas

- `categories` on investors = **investor types** (vc, angel), NOT industry categories
- `aum` is in whole USD: `85000000000` = $85B
- `typicalCheckSize` has `min` and `max` in USD
- `investmentFocus` and `investmentStage` are arrays in the response
- `activelyInvesting` = boolean indicating if currently making deals
