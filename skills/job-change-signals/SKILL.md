---
name: signalbase-job-change-signals
description: Use when the user asks about executive moves, leadership changes, CTO/CEO/VP hires, people changing jobs, or tracking career moves at specific companies.
argument-hint: "[role, department, seniority, person, or company]"
---

# Job Change Signals Skill

> Compatibility: the existing endpoint preserves full payloads, historical defaults and accepted inputs while improving matching automatically. HR MCP `/v2` enables compact responses, open hiring searches, grouped companies and country breakdowns by default. Both keep `data` rows.

## Tool: `search_job_change_signals`
**Endpoint:** `GET /signals/job-changes` | **Cost:** 1 credit per executed search (0 rows still cost); `count=true` free

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default 1) |
| `limit` | integer | Results per page, max 50 |
| `search` | string | Person or company keywords |
| `countries` | string | Person country or company HQ. ISO codes, names, or regions `EU`, `DACH`, … (with `filter_version=2`: unknown → 400) |
| `exclude_countries` | string | Same values, excluded |
| `city` | string | City match |
| `company_name` | string | Company name match |
| `company_domain` | string | Comma-separated domains, up to 50, strict match |
| `company_linkedin_url` | string | Comma-separated LinkedIn company URLs, up to 50 (`companyLinkedinUrl` is a deprecated single-value alias) |
| `person_linkedin_url` | string | Exact LinkedIn profile URL |
| `new_role` | string | Free-text match on the new title |
| `positions` | string | Comma-separated: `cto,ceo,vp of engineering` |
| `departments` | string | Comma-separated: `engineering,product` |
| `seniorities` | string | Comma-separated: `c_level,vp,director` (word-boundary matched) |
| `dateFrom` / `dateTo` | string | YYYY-MM-DD |
| `date_preset` | string | Relative date shorthand |
| `sort_by` | string | `occurred_at`, `discovered_at`, `person_name`, `company_name` |
| `sort_order` | string | `asc` or `desc` |
| `count` | boolean | Only the total count (free) |
| `verbose` | boolean | Full untrimmed payload (Worker-only) |

## Enums

**Positions:** ceo, cto, cfo, coo, vp of engineering, vp of sales, vp of marketing, head of product, head of growth, head of engineering, engineering manager, product manager, sales manager, marketing manager, founder, co-founder

**Departments:** marketing, sales, engineering, product, design, operations, finance, people, data, customer_success, growth, legal

**Seniorities:** founder, c_level, vp, director, head, lead, manager

## Example Workflows

### C-suite changes in DACH this month
```json
{"seniorities": "c_level", "countries": "DACH", "date_preset": "this_month"}
```

### New CTOs
```json
{"positions": "cto", "date_preset": "last_30d"}
```

### Engineering leadership across a list of companies (one credit)
```json
{"company_domain": "stripe.com,vercel.com", "departments": "engineering", "seniorities": "c_level,vp"}
```

## Gotchas

- Every executed search costs 1 credit even with 0 rows — always `count=true` first
- `seniorities=c_level` is broader than `positions=ceo` — it catches all C-suite roles, but word-boundary matching means "Director of Sales" is not `c_level`
- LinkedIn URLs and domains are strict canonical matches
- `personHeadline` is truncated to 300 chars only with `verbose=false`
