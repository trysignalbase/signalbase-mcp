# Hiring Signals

## Tool: `search_hiring_signals`

Search for hiring signals (open job postings). Returns live job listings with title, location, `jobUrl`, `validThrough`, company details, applicant counts, and seniority info. Expired postings are excluded by default.

**Endpoint:** `GET /signals/hiring`
**Cost:** 1 credit per executed search (even with 0 rows); free with `count=true`

> **Coverage warning:** the index is ~84% US job locations. For European or other non-US targets do not filter by job location alone — use `company_countries` (company HQ) + `team_size`, or check a funded pool via `company_domain` (up to 50 domains, one credit).

## Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `page` | integer | Page number (default 1) | `1` |
| `limit` | integer | Results per page, max 100 (default 20) | `50` |
| `search` | string | Free-text search across company, title, location | `"engineering"` |
| `countries` | string | Matches the **job location OR the company HQ**. ISO-2 codes, English names, or regions (`EU`, `EUROPE`, `DACH`, `BENELUX`, `NORDICS`, `CEE`, `WE`, `NA`, `LATAM`); unknown → 400 | `"US,GB,DE"` |
| `job_countries` | string | Job location only (same values) | `"US"` |
| `company_countries` | string | Company HQ only (same values) — use this for European targets | `"EU"` |
| `exclude_countries` | string | Same values as `countries`, excluded | `"US"` |
| `states` | string | Comma-separated US state codes | `"CA,NY,TX"` |
| `city` | string | Free-text city/location search | `"San Francisco"` |
| `company_name` | string | Company name match | `"Stripe"` |
| `company_domain` | string | Comma-separated domains, up to 50, strict canonical match — one credit for the list | `"stripe.com,vercel.com"` |
| `company_linkedin_url` | string | Comma-separated LinkedIn company URLs, up to 50 | `"https://www.linkedin.com/company/stripe"` |
| `categories` | string | Pipe-separated industry categories | `"Technology\|Software"` |
| `subcategories` | string | Comma-separated Signalbase categories (multi-select) | `"ai,fintech,saas"` |
| `positions` | string | Comma-separated positions | `"cto,head of engineering"` |
| `departments` | string | Comma-separated departments | `"engineering,product"` |
| `seniorities` | string | Comma-separated seniority levels | `"c_level,vp,head"` |
| `team_size` | string | Comma-separated **company** size ranges | `"1-10"` or `"1-10,11-50"` |
| `applicants` | string | Comma-separated applicant count ranges | `"0-25,26-50"` |
| `include_expired` | boolean | Default `false`: postings past `validThrough` are hidden. `true` includes them | `true` |
| `dateFrom` | string | Start date (YYYY-MM-DD) | `"2024-01-01"` |
| `dateTo` | string | End date (YYYY-MM-DD) | `"2024-12-31"` |
| `date_preset` | string | Relative date shorthand | `"last_30d"` |
| `sort_by` | string | Sort field | `"date_posted"` |
| `sort_order` | string | Sort direction | `"desc"` |
| `count` | boolean | Return only the total count (free) | `true` |
| `verbose` | boolean | Worker-only: return the full untrimmed payload | `true` |

### Sort By Options
`date_posted`, `created_at`, `title`, `company_name`, `location`

### Team Size Ranges
`1-10`, `11-50`, `51-200`, `201-1000`, `1000-plus`

### Applicant Ranges
`0-25`, `26-50`, `51-100`, `101-200`, `201-plus`

## Example Request

```json
{
  "method": "tools/call",
  "params": {
    "name": "search_hiring_signals",
    "arguments": {
      "company_countries": "EU",
      "team_size": "1-10",
      "departments": "sales",
      "sort_by": "date_posted",
      "sort_order": "desc",
      "limit": 100
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
      "title": "Senior Software Engineer",
      "jobUrl": "https://www.linkedin.com/jobs/view/123456789",
      "location": "San Francisco, CA",
      "city": "San Francisco",
      "region": "California",
      "country": "US",
      "datePosted": "2024-11-01T00:00:00Z",
      "validThrough": "2024-12-01T00:00:00Z",
      "employmentType": "Full-time",
      "seniorityLevel": "Mid-Senior level",
      "jobFunction": "Engineering",
      "numApplicants": "45",
      "companyName": "NextGen Software",
      "companyWebsite": "https://www.nextgensoftware.com",
      "companyIndustry": "Technology",
      "companyEmployeeCount": 250,
      "companyFoundedYear": 2018
    }
  ],
  "pagination": {
    "currentPage": 1,
    "totalPages": 50,
    "totalCount": 1000,
    "hasNextPage": true
  },
  "meta": {
    "endpoint": "signals.hiring",
    "creditsUsed": 1
  },
  "_meta": {"trimmed": true, "hint": "pass verbose=true for full text"}
}
```

## Common Workflows

### Preview result count first (free)
```json
{"company_countries": "NORDICS", "departments": "sales", "count": true}
```

### Check a funded pool for open sales roles (one credit per 50 domains)
```json
{"company_domain": "a.com,b.com,c.com", "departments": "sales", "limit": 100, "sort_by": "date_posted"}
```

### Early-stage European companies hiring sales
```json
{"company_countries": "EU", "team_size": "1-10", "departments": "sales", "limit": 100, "sort_by": "date_posted"}
```

### Find companies hiring VPs of Engineering in the US
```json
{"positions": "vp of engineering", "job_countries": "US", "date_preset": "last_14d"}
```

### Find roles with low competition
```json
{"applicants": "0-25", "departments": "engineering", "countries": "US"}
```

## Important Notes

- Every executed search costs 1 credit, even with 0 rows — size with `count=true` first (free)
- Expired postings are excluded by default; each row carries `jobUrl` and `validThrough`
- `numApplicants` is returned as a string, not a number
- `categories` uses pipe (`|`) separation for hiring signals
- `team_size` refers to the entire company, not the specific team
- US states can be filtered with the `states` parameter (e.g. "CA,NY")
- `descriptionText` is truncated to 300 characters and logo fields are dropped unless `verbose=true`
