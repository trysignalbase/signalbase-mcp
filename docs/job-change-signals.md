# Job Change Signals

## Tool: `search_job_change_signals`

Search for leadership and key-hire job change signals. Returns people who recently changed roles with person name, new role, company, and LinkedIn URLs.

**Endpoint:** `GET /signals/job-changes`
**Cost:** 1 credit per executed search (even with 0 rows); free with `count=true`

## Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `page` | integer | Page number (default 1) | `1` |
| `limit` | integer | Results per page, max 50 (default 20) | `20` |
| `search` | string | Free-text search by company or person keywords | `"engineering leadership"` |
| `countries` | string | Person country OR company HQ. ISO-2 codes, English names, or regions (`EU`, `EUROPE`, `DACH`, `BENELUX`, `NORDICS`, `CEE`, `WE`, `NA`, `LATAM`); unknown → 400 | `"DACH"` |
| `exclude_countries` | string | Same values as `countries`, excluded | `"US"` |
| `city` | string | Free-text city match | `"Berlin"` |
| `company_name` | string | Company name match | `"Stripe"` |
| `company_domain` | string | Comma-separated domains, up to 50, strict canonical match | `"stripe.com,vercel.com"` |
| `company_linkedin_url` | string | Comma-separated LinkedIn company URLs, up to 50 | `"https://www.linkedin.com/company/stripe"` |
| `companyLinkedinUrl` | string | Deprecated alias of `company_linkedin_url` (single URL) | |
| `person_linkedin_url` | string | Exact LinkedIn profile URL | `"https://www.linkedin.com/in/example"` |
| `new_role` | string | Free-text match on the new role title | `"Chief Technology Officer"` |
| `positions` | string | Comma-separated positions | `"cto,head of engineering"` |
| `departments` | string | Comma-separated departments | `"engineering,product"` |
| `seniorities` | string | Comma-separated seniority levels (word-boundary matched) | `"c_level,vp,head"` |
| `dateFrom` | string | Start date (YYYY-MM-DD) | `"2024-01-01"` |
| `dateTo` | string | End date (YYYY-MM-DD) | `"2024-12-31"` |
| `date_preset` | string | Relative date shorthand (overrides dateFrom/dateTo) | `"last_30d"` |
| `sort_by` | string | `occurred_at`, `discovered_at`, `person_name`, `company_name` | `"occurred_at"` |
| `sort_order` | string | `asc` or `desc` | `"desc"` |
| `count` | boolean | Return only the total count (free) | `true` |
| `verbose` | boolean | Worker-only: return the full untrimmed payload | `true` |

## Positions Enum

```
ceo, cto, cfo, coo, vp of engineering, vp of sales, vp of marketing,
head of product, head of growth, head of engineering, engineering manager,
product manager, sales manager, marketing manager, founder, co-founder
```

## Departments Enum

```
marketing, sales, engineering, product, design, operations,
finance, people, data, customer_success, growth, legal
```

## Seniorities Enum

```
founder, c_level, vp, director, head, lead, manager
```

## Example Request

```json
{
  "method": "tools/call",
  "params": {
    "name": "search_job_change_signals",
    "arguments": {
      "seniorities": "c_level,vp",
      "departments": "engineering",
      "countries": "EU",
      "date_preset": "last_30d",
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
      "personName": "Alex Johnson",
      "personLinkedinUrl": "https://www.linkedin.com/in/alexjohnson",
      "signalType": "job_change",
      "occurredAt": "2024-11-01T00:00:00Z",
      "discoveredAt": "2024-11-02T12:00:00Z",
      "companyName": "NextGen Software",
      "companyLinkedinUrl": "https://www.linkedin.com/company/nextgensoftware",
      "newRole": "Chief Technology Officer"
    }
  ],
  "pagination": {
    "currentPage": 1,
    "totalPages": 12,
    "totalCount": 240,
    "hasNextPage": true
  },
  "meta": {
    "endpoint": "signals.job-changes",
    "creditsUsed": 1
  },
  "_meta": {"trimmed": true, "hint": "pass verbose=true for full text"}
}
```

## Common Workflows

### Track CTO changes
```json
{"positions": "cto", "date_preset": "last_30d", "limit": 20}
```

### Monitor engineering leadership moves
```json
{"seniorities": "c_level,vp,head", "departments": "engineering"}
```

### Look up a specific person's job changes
```json
{"person_linkedin_url": "https://www.linkedin.com/in/johndoe"}
```

### Leadership changes across a list of companies (one credit)
```json
{"company_domain": "stripe.com,vercel.com,linear.app", "seniorities": "c_level,vp"}
```

## Important Notes

- The `positions` filter matches specific titles (e.g. "cto"), while `seniorities` matches broader levels (e.g. "c_level" captures CEO, CTO, CFO, etc.) using word boundaries — a "Director of Sales" is not `c_level`
- Use `seniorities` for broader coverage, `positions` for specific roles
- LinkedIn URLs and domains are strict canonical matches (not partial)
- Every executed search costs 1 credit, even with 0 rows — size with `count=true` first (free)
- `personHeadline` is truncated to 300 characters unless `verbose=true`
