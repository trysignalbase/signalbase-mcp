# Investors

## Tool: `search_investors`

Search for investors — VCs, angels, PE firms, accelerators, and more. Returns investor profiles with AUM, investment focus, check sizes, portfolio details, and contact info.

**Endpoint:** `GET /signals/investors`
**Cost:** 1 credit per call

## Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `page` | integer | Page number (default 1) | `1` |
| `limit` | integer | Results per page, max 50 (default 20) | `20` |
| `search` | string | Free-text search by investor name or description | `"sequoia"` |
| `countries` | string | Comma-separated country codes | `"US,GB,CA"` |
| `categories` | string | Comma-separated investor types | `"vc,angel"` |

## Investor Types

```
vc, angel, pe, corporate, government, accelerator,
family_office, hedge_fund, crowdfunding
```

## Example Request

```json
{
  "method": "tools/call",
  "params": {
    "name": "search_investors",
    "arguments": {
      "categories": "vc",
      "countries": "US",
      "search": "seed stage",
      "limit": 10
    }
  }
}
```

## Example Response

```json
{
  "success": true,
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Sequoia Capital",
      "investorType": "vc",
      "country": "United States",
      "city": "Menlo Park",
      "state": "California",
      "description": "Leading venture capital firm...",
      "website": "https://www.sequoiacap.com",
      "linkedinUrl": "https://www.linkedin.com/company/sequoia-capital",
      "twitterUrl": "https://twitter.com/sequoia",
      "foundedYear": 1972,
      "teamSize": 85,
      "aum": 85000000000,
      "investmentFocus": ["Technology", "Healthcare", "Financial Services"],
      "investmentStage": ["Seed", "Series A", "Series B", "Growth"],
      "typicalCheckSize": {"min": 1000000, "max": 100000000},
      "portfolioCompaniesCount": 250,
      "notableInvestments": ["Apple", "Google", "Airbnb", "Stripe"],
      "activelyInvesting": true,
      "lastInvestmentDate": "2024-11-10"
    }
  ],
  "pagination": {
    "currentPage": 1,
    "totalPages": 50,
    "totalCount": 1000,
    "hasNextPage": true
  },
  "meta": {
    "endpoint": "signals.investors",
    "creditsUsed": 1
  }
}
```

## Common Workflows

### Find VCs investing in AI
```json
{"categories": "vc", "search": "artificial intelligence"}
```

### Find European angel investors
```json
{"categories": "angel", "countries": "GB,DE,FR,NL,SE"}
```

### Find accelerators
```json
{"categories": "accelerator"}
```

## Important Notes

- `aum` (Assets Under Management) is in whole USD (e.g. `85000000000` = $85B)
- `typicalCheckSize` provides `min` and `max` in USD
- `activelyInvesting` indicates whether the firm is currently making new investments
- The `categories` parameter for investors maps to **investor types** (vc, angel, pe), which is different from the `categories` parameter on signal endpoints (which maps to industry labels)
