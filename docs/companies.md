# Companies

## Tool: `search_companies`

Search and browse the Signalbase company database independently of signals. Returns company profiles with headcount, industry, growth metrics, and more.

**Endpoint:** `GET /companies`
**Cost:** 1 credit per executed search (even with 0 rows); free with `count=true`

## Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `page` | integer | Page number (default 1) | `1` |
| `limit` | integer | Results per page, max 100 (default 20) | `50` |
| `search` | string | Free-text search across name, industry, description, keywords, specialties | `"AI"` |
| `countries` | string | Comma-separated ISO-2 codes, English names, or regions (`EU`, `EUROPE`, `DACH`, `BENELUX`, `NORDICS`, `CEE`, `WE`, `NA`, `LATAM`); unknown → 400 | `"US,GB,DE"` |
| `exclude_countries` | string | Same values as `countries`, excluded | `"US"` |
| `categories` | string | Pipe-separated LinkedIn industry labels | `"Software Development\|Financial Services"` |
| `subcategories` | string | Comma-separated Signalbase categories (multi-select) | `"ai,saas"` |
| `industry` | string | Comma-separated industry names (exact match) | `"Software,Technology"` |
| `domain` | string | Company website domain (strict canonical match) | `"stripe.com"` |
| `linkedin_url` | string | Company LinkedIn URL (strict canonical match) | `"https://www.linkedin.com/company/stripe"` |
| `employee_count_min` | integer | Minimum employee count | `50` |
| `employee_count_max` | integer | Maximum employee count | `5000` |
| `founded_year_min` | integer | Minimum founded year | `2020` |
| `founded_year_max` | integer | Maximum founded year | `2025` |
| `sort_by` | string | Sort field | `"employee_count"` |
| `sort_order` | string | Sort direction | `"desc"` |
| `count` | boolean | Return only the total count (free) | `true` |
| `verbose` | boolean | Worker-only: return the full untrimmed payload | `true` |

### Sort By Options
`name`, `employee_count`, `founded_year`, `created_at`

## Example Request

```json
{
  "method": "tools/call",
  "params": {
    "name": "search_companies",
    "arguments": {
      "search": "AI",
      "countries": "US",
      "employee_count_min": 50,
      "employee_count_max": 500,
      "founded_year_min": 2020,
      "sort_by": "employee_count",
      "sort_order": "desc",
      "limit": 20
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
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "NextGen Software",
      "slug": "nextgen-software",
      "description": "Enterprise SaaS platform for workflow automation.",
      "website": "https://www.nextgensoftware.com",
      "linkedinUrl": "https://www.linkedin.com/company/nextgensoftware",
      "twitterUrl": "https://twitter.com/nextgensoftware",
      "industry": "Technology",
      "foundedYear": 2018,
      "headquartersCountry": "US",
      "employeeCount": 250,
      "categories": ["Software", "SaaS", "Enterprise"],
      "keywords": ["workflow automation", "enterprise", "AI"],
      "specialties": ["process automation", "integration"],
      "growthInfo": {
        "growth_1m": 1.2,
        "growth_3m": 3.5,
        "growth_6m": 8.1,
        "growth_9m": 12.0,
        "growth_12m": 18.5
      }
    }
  ],
  "pagination": {
    "currentPage": 1,
    "totalPages": 200,
    "totalCount": 4000,
    "hasNextPage": true
  },
  "meta": {
    "endpoint": "companies.list",
    "creditsUsed": 1
  },
  "_meta": {"trimmed": true, "hint": "pass verbose=true for full text"}
}
```

`logoUrl` is present in the API payload but dropped by the Worker unless `verbose=true`.

## Common Workflows

### Count AI companies in Europe (free)
```json
{"search": "AI", "countries": "EU", "count": true}
```

### Look up one company by domain
```json
{"domain": "stripe.com"}
```

### Find fast-growing startups
```json
{"founded_year_min": 2021, "employee_count_min": 10, "employee_count_max": 200, "sort_by": "employee_count", "sort_order": "desc"}
```

### Search by industry
```json
{"industry": "Software Development", "countries": "US", "limit": 50}
```

## Important Notes

- `count=true` returns only the total count — zero credits deducted; every executed search costs 1 credit, even with 0 rows
- `growthInfo` shows headcount growth as percentages over 1m, 3m, 6m, 9m, 12m windows — can be `null`
- `industry` uses exact match on the LinkedIn industry label (not fuzzy)
- The `industry` parameter on the companies endpoint is different from `categories` on signal endpoints — here it maps directly to the company's industry field
- `categories`, `keywords`, and `specialties` in the response are arrays (not the filter parameter)
- `description` is truncated to 300 characters unless `verbose=true`
