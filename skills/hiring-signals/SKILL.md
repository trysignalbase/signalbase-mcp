---
name: signalbase-hiring-signals
description: Use when the user asks about job postings, which companies are hiring, open roles, hiring trends, or wants to find companies building specific teams.
argument-hint: "[role, department, location, sector, or company]"
---

# Hiring Signals Skill

## Tool: `search_hiring_signals`
**Endpoint:** `GET /signals/hiring` | **Cost:** 1 credit (free with count=true)

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default 1) |
| `limit` | integer | Results per page, max 100 |
| `search` | string | Free-text search |
| `countries` | string | Comma-separated country codes |
| `states` | string | Comma-separated US state codes |
| `city` | string | City/location search |
| `categories` | string | Pipe-separated industry categories |
| `subcategories` | string | Comma-separated Signalbase categories |
| `positions` | string | Comma-separated positions |
| `departments` | string | Comma-separated departments |
| `seniorities` | string | Comma-separated seniority levels |
| `team_size` | string | Ranges: `1-10,11-50,51-200,201-1000,1000-plus` |
| `applicants` | string | Ranges: `0-25,26-50,51-100,101-200,201-plus` |
| `dateFrom` | string | YYYY-MM-DD |
| `dateTo` | string | YYYY-MM-DD |
| `date_preset` | string | Relative date shorthand |
| `sort_by` | string | `date_posted`, `created_at`, `title`, `company_name`, `location` |
| `sort_order` | string | `asc` or `desc` |
| `count` | boolean | If true, returns only count (free) |

## Example Workflows

### Preview count first (free)
```json
{"subcategories": "ai", "countries": "US", "count": true}
```

### AI companies hiring engineers in SF
```json
{"subcategories": "ai", "departments": "engineering", "city": "San Francisco"}
```

### Early-stage startups hiring VPs
```json
{"team_size": "1-10,11-50", "seniorities": "vp", "date_preset": "last_14d"}
```

### Low-competition roles
```json
{"applicants": "0-25", "departments": "engineering", "countries": "US"}
```

## Gotchas

- Always use `count=true` first to check result size — it's free
- `categories` uses **pipe** `|` separator, not comma
- `numApplicants` in response is a string, not integer
- Team size = company size, not the specific team
- US states use 2-letter codes: CA, NY, TX
