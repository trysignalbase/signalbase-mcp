# Hiring Signals

## Tool: `search_hiring_signals`

Search for hiring signals (open job postings). Returns active job listings with title, location, company details, applicant counts, and seniority info.

**Endpoint:** `GET /signals/hiring`
**Cost:** 1 credit per call (free with `count=true`)

## Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `page` | integer | Page number (default 1) | `1` |
| `limit` | integer | Results per page, max 100 (default 20) | `50` |
| `search` | string | Free-text search across company, title, location | `"engineering"` |
| `countries` | string | Comma-separated country codes | `"US,GB,DE"` |
| `states` | string | Comma-separated US state codes | `"CA,NY,TX"` |
| `city` | string | Free-text city/location search | `"San Francisco"` |
| `categories` | string | Pipe-separated industry categories | `"Technology\|Software"` |
| `subcategories` | string | Comma-separated Signalbase categories | `"ai,fintech,saas"` |
| `positions` | string | Comma-separated positions | `"cto,head of engineering"` |
| `departments` | string | Comma-separated departments | `"engineering,product"` |
| `seniorities` | string | Comma-separated seniority levels | `"c_level,vp,head"` |
| `team_size` | string | Comma-separated team size ranges | `"51-200,201-1000"` |
| `applicants` | string | Comma-separated applicant count ranges | `"0-25,26-50"` |
| `dateFrom` | string | Start date (YYYY-MM-DD) | `"2024-01-01"` |
| `dateTo` | string | End date (YYYY-MM-DD) | `"2024-12-31"` |
| `date_preset` | string | Relative date shorthand | `"last_30d"` |
| `sort_by` | string | Sort field | `"date_posted"` |
| `sort_order` | string | Sort direction | `"desc"` |
| `count` | boolean | Return only total count (no credits) | `true` |

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
      "subcategories": "ai,saas",
      "departments": "engineering",
      "countries": "US",
      "date_preset": "last_30d",
      "sort_by": "date_posted",
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
      "title": "Senior Software Engineer",
      "jobUrl": "https://www.linkedin.com/jobs/view/123456789",
      "location": "San Francisco, CA",
      "city": "San Francisco",
      "region": "California",
      "country": "US",
      "datePosted": "2024-11-01T00:00:00Z",
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
  }
}
```

## Common Workflows

### Preview result count first (free)
```json
{"subcategories": "ai", "countries": "US", "count": true}
```

### Find companies hiring VPs of Engineering
```json
{"positions": "vp of engineering", "countries": "US", "date_preset": "last_14d"}
```

### Track early-stage startup hiring
```json
{"team_size": "1-10,11-50", "subcategories": "ai,saas", "date_preset": "last_30d"}
```

### Find roles with low competition
```json
{"applicants": "0-25", "departments": "engineering", "countries": "US"}
```

## Important Notes

- `count=true` returns only the total count — zero credits deducted
- `numApplicants` is returned as a string, not a number
- `categories` uses pipe (`|`) separation for hiring signals
- Team size refers to the entire company, not the specific team
- US states can be filtered with the `states` parameter (e.g. "CA,NY")
