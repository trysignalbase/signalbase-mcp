---
name: signalbase-acquisition-signals
description: Use when the user asks about acquisitions, M&A activity, merger targets, companies being acquired, or acquisition indicators.
argument-hint: "[sector, geography, or company name]"
---

# Acquisition Signals Skill

> Compatibility: the existing endpoint preserves full payloads, historical defaults and accepted inputs while improving matching automatically. HR MCP `/v2` enables compact responses, open hiring searches, grouped companies and country breakdowns by default. Both keep `data` rows.

## Tool: `search_acquisition_signals`
**Endpoint:** `GET /signals/acquisitions` | **Cost:** 1 credit per executed search (0 rows still cost); `count=true` free

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default 1) |
| `limit` | integer | Results per page, max 50 |
| `search` | string | Company name or keywords |
| `countries` | string | ISO codes, names, or regions: `US,GB`, `EU`, `DACH` (with `filter_version=2`: unknown → 400) |
| `exclude_countries` | string | Same values, excluded |
| `categories` | string | Pipe-separated LinkedIn industries |
| `subcategories` | string | Comma-separated multi-select: `saas,healthcare` |
| `amount_min` / `amount_max` | integer | Deal amount bounds, whole USD |
| `employee_count_min` / `employee_count_max` | integer | Company headcount bounds |
| `founded_year_min` / `founded_year_max` | integer | Founded year bounds |
| `company_domain` | string | Comma-separated domains, up to 50, strict match |
| `company_linkedin_url` | string | Comma-separated LinkedIn company URLs, up to 50 |
| `dateFrom` / `dateTo` | string | YYYY-MM-DD |
| `date_preset` | string | Relative date shorthand |
| `count` | boolean | Only the total count (free) |
| `verbose` | boolean | Full untrimmed payload (Worker-only) |

## Example Workflows

### Recent M&A in SaaS
```json
{"subcategories": "saas", "date_preset": "last_90d"}
```

### Mid-size acquisition targets in Europe
```json
{"subcategories": "healthcare", "countries": "EU", "employee_count_min": 50, "employee_count_max": 500}
```

## Gotchas

- Every executed search costs 1 credit even with 0 rows — always `count=true` first
- `acquisitionSignalScore` is 0–100 (higher = stronger M&A signal)
- `signalIndicators` gives human-readable reasons for the score
- Revenue in response is a range string like "10M-50M"
