---
name: signalbase-job-change-signals
description: Use when the user asks about executive moves, leadership changes, CTO/CEO/VP hires, people changing jobs, or tracking career moves at specific companies.
argument-hint: "[role, department, seniority, person, or company]"
---

# Job Change Signals Skill

## Tool: `search_job_change_signals`
**Endpoint:** `GET /signals/job-changes` | **Cost:** 1 credit

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default 1) |
| `limit` | integer | Results per page, max 50 |
| `search` | string | Person or company keywords |
| `positions` | string | Comma-separated: `cto,ceo,vp of engineering` |
| `departments` | string | Comma-separated: `engineering,product` |
| `seniorities` | string | Comma-separated: `c_level,vp,director` |
| `personLinkedinUrl` | string | Exact LinkedIn profile URL |
| `companyLinkedinUrl` | string | Exact LinkedIn company URL |

## Enums

**Positions:** ceo, cto, cfo, coo, vp of engineering, vp of sales, vp of marketing, head of product, head of growth, head of engineering, engineering manager, product manager, sales manager, marketing manager, founder, co-founder

**Departments:** marketing, sales, engineering, product, design, operations, finance, people, data, customer_success, growth, legal

**Seniorities:** founder, c_level, vp, director, head, lead, manager

## Example Workflows

### Track all C-suite changes
```json
{"seniorities": "c_level"}
```

### New CTOs
```json
{"positions": "cto"}
```

### Engineering leadership at a specific company
```json
{"companyLinkedinUrl": "https://www.linkedin.com/company/stripe", "departments": "engineering"}
```

## Gotchas

- `seniorities=c_level` is broader than `positions=ceo` — it catches all C-suite roles
- LinkedIn URLs must be exact matches
- No date filtering available on this endpoint — results are sorted by recency
