# Funding Signals

## Tool: `search_funding_signals`

Search for real-time funding round signals. Returns companies that recently raised funding with round type, amount, investors, and company details.

**Endpoint:** `GET /signals/funding`
**Cost:** 1 credit per call

## Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `page` | integer | Page number (default 1) | `1` |
| `limit` | integer | Results per page, max 50 (default 20) | `20` |
| `search` | string | Free-text search by company name or industry keywords | `"fintech"` |
| `countries` | string | Comma-separated country codes or region shortcuts | `"US,GB"` or `"NORDICS"` |
| `categories` | string | Pipe-separated LinkedIn industry labels | `"Software Development\|Financial Services"` |
| `subcategories` | string | Comma-separated Signalbase categories | `"ai,fintech,saas"` |
| `round` | string | Comma-separated funding round types | `"Seed,Series A"` |
| `dateFrom` | string | Start date (YYYY-MM-DD) | `"2024-01-01"` |
| `dateTo` | string | End date (YYYY-MM-DD) | `"2024-12-31"` |
| `date_preset` | string | Relative date shorthand (overrides dateFrom/dateTo) | `"last_30d"` |

## Round Types

```
Pre-Seed, Seed, Series A, Series B, Series C, Series D, Series E,
Series F, Series G, Growth, Debt, Grant, IPO, Undisclosed
```

## Example Request

```json
{
  "method": "tools/call",
  "params": {
    "name": "search_funding_signals",
    "arguments": {
      "subcategories": "ai,saas",
      "countries": "US",
      "date_preset": "last_30d",
      "round": "Seed,Series A",
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
      "signalId": "550e8400-e29b-41d4-a716-446655440000",
      "companyName": "FinTech Innovations",
      "roundType": "Series A",
      "fundingAmount": 15000000,
      "fundingCurrency": "USD",
      "announcedDate": "2024-10-15",
      "industry": "Financial Technology",
      "country": "United States",
      "website": "https://www.fintechinnovations.com",
      "linkedinUrl": "https://www.linkedin.com/company/fintechinnovations",
      "employeeCount": 85,
      "foundedYear": 2020,
      "investorNames": ["Sequoia Capital", "Andreessen Horowitz"],
      "leadInvestor": "Sequoia Capital",
      "totalFundingToDate": 25000000,
      "valuation": 75000000
    }
  ],
  "pagination": {
    "currentPage": 1,
    "totalPages": 15,
    "totalCount": 300,
    "hasNextPage": true,
    "hasPreviousPage": false
  },
  "meta": {
    "endpoint": "signals.funding",
    "creditsUsed": 1
  }
}
```

## Common Workflows

### Find recently funded AI startups
```json
{"subcategories": "ai", "date_preset": "last_30d", "round": "Seed,Pre-Seed"}
```

### Track Series B+ rounds in Europe
```json
{"countries": "WE,NORDICS,CEE", "round": "Series B,Series C,Series D", "date_preset": "last_90d"}
```

### Search for a specific company's funding
```json
{"search": "Stripe"}
```

## Important Notes

- **Amounts** are stored as whole USD integers (e.g. `15000000` = $15M)
- **Currency** filter is an exact-match filter, not a converter — most records are USD
- The `categories` parameter uses pipe (`|`) separation, not commas
- The `subcategories` parameter uses comma separation
- `date_preset` takes precedence over `dateFrom`/`dateTo`
