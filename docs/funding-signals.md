# Funding Signals

> Compatibility: the existing endpoint preserves full payloads, historical defaults and accepted inputs while improving matching automatically. HR MCP `/v2` enables compact responses, open hiring searches, grouped companies and country breakdowns by default. Both keep `data` rows.

## Tool: `search_funding_signals`

Search for real-time funding round signals. Returns companies that recently raised funding with round type, amount, investors, and company details.

**Endpoint:** `GET /signals/funding`
**Cost:** 1 credit per executed search (even with 0 rows); free with `count=true`

## Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `page` | integer | Page number (default 1) | `1` |
| `limit` | integer | Results per page, max 50 (default 20) | `20` |
| `search` | string | Free-text search by company name or industry keywords | `"fintech"` |
| `countries` | string | Comma-separated ISO-2 codes, English names, or regions (`EU`, `EUROPE`, `DACH`, `BENELUX`, `NORDICS`, `CEE`, `WE`, `NORTH_AMERICA`, `LATAM`); with `filter_version=2`: unknown → 400 | `"US,GB"` or `"NORDICS"` |
| `exclude_countries` | string | Same values as `countries`, excluded | `"US"` |
| `categories` | string | Pipe-separated LinkedIn industry labels | `"Software Development\|Financial Services"` |
| `subcategories` | string | Comma-separated Signalbase categories (multi-select) | `"ai,fintech,saas"` |
| `round` | string | Comma-separated funding round types | `"Seed,Series A"` |
| `amount_min` | integer | Minimum round amount, whole USD | `1000000` |
| `amount_max` | integer | Maximum round amount, whole USD | `20000000` |
| `employee_count_min` | integer | Minimum company headcount | `2` |
| `employee_count_max` | integer | Maximum company headcount (unknown headcount excluded) | `10` |
| `founded_year_min` | integer | Minimum founded year | `2020` |
| `founded_year_max` | integer | Maximum founded year | `2025` |
| `company_domain` | string | Comma-separated domains, up to 50, strict canonical match | `"stripe.com,vercel.com"` |
| `company_linkedin_url` | string | Comma-separated LinkedIn company URLs, up to 50 | `"https://www.linkedin.com/company/stripe"` |
| `dateFrom` | string | Start date (YYYY-MM-DD) | `"2024-01-01"` |
| `dateTo` | string | End date (YYYY-MM-DD) | `"2024-12-31"` |
| `date_preset` | string | Relative date shorthand (overrides dateFrom/dateTo) | `"last_30d"` |
| `count` | boolean | Return only the total count (free) | `true` |
| `verbose` | boolean | Worker-only: return the full untrimmed payload | `true` |

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
  },
  "_meta": {"trimmed": true, "hint": "pass verbose=true for full text"}
}
```

## Common Workflows

### Size a micro-company pool in Europe for free, then pull it
```json
{"countries": "EU", "employee_count_max": 10, "date_preset": "last_90d", "count": true}
```
```json
{"countries": "EU", "employee_count_max": 10, "date_preset": "last_90d", "limit": 50}
```
Then feed the website domains to `search_hiring_signals` via `company_domain` (up to 50 per call, one credit).

### Find recently funded AI startups
```json
{"subcategories": "ai", "date_preset": "last_30d", "round": "Seed,Pre-Seed"}
```

### Track Series B+ rounds in Europe
```json
{"countries": "EUROPE", "round": "Series B,Series C,Series D", "date_preset": "last_90d"}
```

### Search for a specific company's funding
```json
{"company_domain": "stripe.com"}
```

## Important Notes

- **Amounts** are stored as whole USD integers (e.g. `15000000` = $15M)
- Every executed search costs 1 credit, even with 0 rows — size with `count=true` first (free)
- The `categories` parameter uses pipe (`|`) separation, not commas
- The `subcategories` parameter uses comma separation (multi-select)
- `date_preset` takes precedence over `dateFrom`/`dateTo`
- Descriptions are truncated to 300 characters and logo fields dropped only with `verbose=false`
