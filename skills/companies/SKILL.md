---
name: signalbase-companies
description: Use when the user asks about company profiles, company search, headcount data, company growth metrics, or wants to look up specific companies independent of signal data.
argument-hint: "[company name, industry, geography, or size range]"
---

# Companies Skill

## Tool: `search_companies`
**Endpoint:** `GET /companies` | **Cost:** 1 credit per executed search (0 rows still cost); `count=true` free

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default 1) |
| `limit` | integer | Results per page, max 100 |
| `search` | string | Name, industry, description, keywords |
| `countries` | string | ISO codes, names, or regions: `US,GB`, `EU`, `DACH` (unknown → 400) |
| `exclude_countries` | string | Same values, excluded |
| `categories` | string | Pipe-separated LinkedIn industry labels |
| `subcategories` | string | Comma-separated Signalbase categories (multi-select) |
| `industry` | string | Comma-separated industry names (exact) |
| `domain` | string | Website domain, strict canonical match |
| `linkedin_url` | string | LinkedIn company URL, strict canonical match |
| `employee_count_min` / `employee_count_max` | integer | Headcount bounds |
| `founded_year_min` / `founded_year_max` | integer | Founded year bounds |
| `sort_by` | string | `name`, `employee_count`, `founded_year`, `created_at` |
| `sort_order` | string | `asc` or `desc` |
| `count` | boolean | Only the total count (free) |
| `verbose` | boolean | Full untrimmed payload (Worker-only) |

## Example Workflows

### Count companies in a segment (free)
```json
{"search": "AI", "countries": "EU", "count": true}
```

### Look up a specific company by domain
```json
{"domain": "stripe.com"}
```

### Find fast-growing startups (50-200 employees, founded 2021+)
```json
{"founded_year_min": 2021, "employee_count_min": 50, "employee_count_max": 200, "sort_by": "employee_count", "sort_order": "desc"}
```

### Browse by industry
```json
{"industry": "Software Development", "countries": "US,GB", "limit": 50}
```

## Gotchas

- Every executed search costs 1 credit even with 0 rows — always `count=true` first
- `industry` param is **exact match** on LinkedIn industry label
- `growthInfo` in response can be `null` — not all companies have growth data
- Growth percentages: `growth_1m`, `growth_3m`, `growth_6m`, `growth_9m`, `growth_12m`
- `categories`, `keywords`, `specialties` in the response are arrays — these are response fields, not filter params
- `description` is truncated to 300 chars and `logoUrl` dropped unless `verbose=true`
