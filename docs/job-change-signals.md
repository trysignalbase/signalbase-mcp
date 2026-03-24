# Job Change Signals

## Tool: `search_job_change_signals`

Search for leadership and key-hire job change signals. Returns people who recently changed roles with person name, new role, company, and LinkedIn URLs.

**Endpoint:** `GET /signals/job-changes`
**Cost:** 1 credit per call

## Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `page` | integer | Page number (default 1) | `1` |
| `limit` | integer | Results per page, max 50 (default 20) | `20` |
| `search` | string | Free-text search by company or person keywords | `"engineering leadership"` |
| `positions` | string | Comma-separated positions | `"cto,head of engineering"` |
| `departments` | string | Comma-separated departments | `"engineering,product"` |
| `seniorities` | string | Comma-separated seniority levels | `"c_level,vp,head"` |
| `personLinkedinUrl` | string | Exact LinkedIn profile URL | `"https://www.linkedin.com/in/example"` |
| `companyLinkedinUrl` | string | Exact LinkedIn company page URL | `"https://www.linkedin.com/company/example"` |

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
  }
}
```

## Common Workflows

### Track CTO changes
```json
{"positions": "cto", "limit": 20}
```

### Monitor engineering leadership moves
```json
{"seniorities": "c_level,vp,head", "departments": "engineering"}
```

### Look up a specific person's job changes
```json
{"personLinkedinUrl": "https://www.linkedin.com/in/johndoe"}
```

### Find leadership changes at a specific company
```json
{"companyLinkedinUrl": "https://www.linkedin.com/company/stripe"}
```

## Important Notes

- The `positions` filter matches specific titles (e.g. "cto"), while `seniorities` matches broader levels (e.g. "c_level" captures CEO, CTO, CFO, etc.)
- Use `seniorities` for broader coverage, `positions` for specific roles
- LinkedIn URLs must be exact matches (not partial)
- No date filtering on this endpoint — results are sorted by recency
