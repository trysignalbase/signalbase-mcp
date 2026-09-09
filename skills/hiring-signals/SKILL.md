---
name: signalbase-hiring-signals
description: Use when the user asks about job postings, which companies are hiring, open roles, hiring trends, or wants to find companies building specific teams.
argument-hint: "[role, department, location, sector, or company]"
---

# Hiring Signals Skill

## Tool: `search_hiring_signals`
**Endpoint:** `GET /signals/hiring` | **Cost:** 1 credit per executed search (0 rows still cost); `count=true` free

**Coverage:** ~84% of job locations are US. For European targets filter by company HQ (`company_countries`) or by a `company_domain` list — never by job location alone. Expired postings are excluded by default.

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default 1) |
| `limit` | integer | Results per page, max 100 |
| `search` | string | Free-text search |
| `countries` | string | Job location **or** company HQ. ISO codes, names, or regions `EU`, `NORDICS`, `DACH`, … (unknown → 400) |
| `job_countries` | string | Job location only |
| `company_countries` | string | Company HQ only — use for European targets |
| `exclude_countries` | string | Same values, excluded |
| `states` | string | Comma-separated US state codes |
| `city` | string | City/location search |
| `company_name` | string | Company name match |
| `company_domain` | string | Comma-separated domains, up to 50, strict match — one credit for the list |
| `company_linkedin_url` | string | Comma-separated LinkedIn company URLs, up to 50 |
| `categories` | string | Pipe-separated industry categories |
| `subcategories` | string | Comma-separated Signalbase categories (multi-select) |
| `positions` | string | Comma-separated positions |
| `departments` | string | Comma-separated departments (`sales`, `engineering`, …) |
| `seniorities` | string | Comma-separated seniority levels |
| `team_size` | string | Company size ranges: `1-10`, `11-50`, `51-200`, `201-1000`, `1000-plus` |
| `applicants` | string | Ranges: `0-25,26-50,51-100,101-200,201-plus` |
| `include_expired` | boolean | Default false (expired hidden); true to include |
| `dateFrom` / `dateTo` | string | YYYY-MM-DD |
| `date_preset` | string | Relative date shorthand |
| `sort_by` | string | `date_posted`, `created_at`, `title`, `company_name`, `location` |
| `sort_order` | string | `asc` or `desc` |
| `count` | boolean | Only the total count (free) |
| `verbose` | boolean | Full untrimmed payload (Worker-only) |

## Example Workflows

### Preview count first (free)
```json
{"company_countries": "NORDICS", "departments": "sales", "count": true}
```

### Funded pool → open sales roles (one credit per 50 domains)
```json
{"company_domain": "a.com,b.com,c.com", "departments": "sales", "limit": 100, "sort_by": "date_posted"}
```

### Early-stage European companies hiring sales
```json
{"company_countries": "EU", "team_size": "1-10", "departments": "sales", "limit": 100, "sort_by": "date_posted"}
```

### AI companies hiring engineers in SF
```json
{"subcategories": "ai", "departments": "engineering", "city": "San Francisco"}
```

### Low-competition roles
```json
{"applicants": "0-25", "departments": "engineering", "job_countries": "US"}
```

## Gotchas

- Every executed search costs 1 credit even with 0 rows — always `count=true` first
- Each row carries `jobUrl` and `validThrough`; expired postings are hidden unless `include_expired=true`
- `categories` uses **pipe** `|` separator, not comma
- `numApplicants` in response is a string, not integer
- `team_size` = company size, not the specific team
- US states use 2-letter codes: CA, NY, TX
- `descriptionText` is truncated to 300 chars and logos dropped unless `verbose=true`
