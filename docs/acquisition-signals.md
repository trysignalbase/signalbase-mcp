# Acquisition Signals

## Tool: `search_acquisition_signals`

Search for acquisition and M&A signals. Returns companies showing acquisition indicators with signal scores and details.

**Endpoint:** `GET /signals/acquisitions`
**Cost:** 1 credit per executed search (even with 0 rows); free with `count=true`

## Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `page` | integer | Page number (default 1) | `1` |
| `limit` | integer | Results per page, max 50 (default 20) | `20` |
| `search` | string | Free-text search by company name or keywords | `"tech"` |
| `countries` | string | Comma-separated ISO-2 codes, English names, or regions (`EU`, `EUROPE`, `DACH`, `BENELUX`, `NORDICS`, `CEE`, `WE`, `NA`, `LATAM`); unknown → 400 | `"US,GB,CA"` |
| `exclude_countries` | string | Same values as `countries`, excluded | `"US"` |
| `categories` | string | Pipe-separated LinkedIn industry labels | `"Software Development\|Healthcare"` |
| `subcategories` | string | Comma-separated Signalbase categories (multi-select) | `"saas,healthcare"` |
| `amount_min` | integer | Minimum deal amount, whole USD | `1000000` |
| `amount_max` | integer | Maximum deal amount, whole USD | `500000000` |
| `employee_count_min` | integer | Minimum company headcount | `50` |
| `employee_count_max` | integer | Maximum company headcount | `500` |
| `founded_year_min` | integer | Minimum founded year | `2015` |
| `founded_year_max` | integer | Maximum founded year | `2024` |
| `company_domain` | string | Comma-separated domains, up to 50, strict canonical match | `"a.com,b.com"` |
| `company_linkedin_url` | string | Comma-separated LinkedIn company URLs, up to 50 | `"https://www.linkedin.com/company/a"` |
| `dateFrom` | string | Start date (YYYY-MM-DD) | `"2024-01-01"` |
| `dateTo` | string | End date (YYYY-MM-DD) | `"2024-12-31"` |
| `date_preset` | string | Relative date shorthand (overrides dateFrom/dateTo) | `"last_30d"` |
| `count` | boolean | Return only the total count (free) | `true` |
| `verbose` | boolean | Worker-only: return the full untrimmed payload | `true` |

## Example Request

```json
{
  "method": "tools/call",
  "params": {
    "name": "search_acquisition_signals",
    "arguments": {
      "countries": "US",
      "subcategories": "saas",
      "date_preset": "last_90d",
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
      "companyName": "TechVentures Inc",
      "industry": "Software Development",
      "country": "United States",
      "website": "https://www.techventures.com",
      "linkedinUrl": "https://www.linkedin.com/company/techventures",
      "employeeCount": 150,
      "revenue": "10M-50M",
      "foundedYear": 2018,
      "acquisitionSignalScore": 85,
      "signalIndicators": [
        "Recent funding round",
        "Leadership changes",
        "Market consolidation"
      ]
    }
  ],
  "pagination": {
    "currentPage": 1,
    "totalPages": 25,
    "totalCount": 500,
    "hasNextPage": true,
    "hasPreviousPage": false
  },
  "meta": {
    "endpoint": "signals.acquisitions",
    "creditsUsed": 1
  },
  "_meta": {"trimmed": true, "hint": "pass verbose=true for full text"}
}
```

## Common Workflows

### Track M&A activity in SaaS
```json
{"subcategories": "saas", "date_preset": "last_90d"}
```

### Find mid-size acquisition targets in Europe
```json
{"subcategories": "healthcare", "countries": "EU", "employee_count_min": 50, "employee_count_max": 500}
```

## Important Notes

- `acquisitionSignalScore` ranges from 0–100, with higher scores indicating stronger M&A likelihood
- `signalIndicators` provides human-readable reasons for the score
- Revenue is returned as a range string (e.g. "10M-50M"), not a numeric value
- Every executed search costs 1 credit, even with 0 rows — size with `count=true` first (free)
