# Acquisition Signals

## Tool: `search_acquisition_signals`

Search for acquisition and M&A signals. Returns companies showing acquisition indicators with signal scores and details.

**Endpoint:** `GET /signals/acquisitions`
**Cost:** 1 credit per call

## Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `page` | integer | Page number (default 1) | `1` |
| `limit` | integer | Results per page, max 50 (default 20) | `20` |
| `search` | string | Free-text search by company name or keywords | `"tech"` |
| `countries` | string | Comma-separated country codes or region shortcuts | `"US,GB,CA"` |
| `categories` | string | Comma-separated company categories | `"Technology,Healthcare"` |
| `dateFrom` | string | Start date (YYYY-MM-DD) | `"2024-01-01"` |
| `dateTo` | string | End date (YYYY-MM-DD) | `"2024-12-31"` |
| `date_preset` | string | Relative date shorthand (overrides dateFrom/dateTo) | `"last_30d"` |

## Example Request

```json
{
  "method": "tools/call",
  "params": {
    "name": "search_acquisition_signals",
    "arguments": {
      "countries": "US",
      "categories": "Technology",
      "date_preset": "last_90d",
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
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "companyName": "TechVentures Inc",
      "industry": "Software Development",
      "country": "United States",
      "website": "https://www.techventures.com",
      "linkedinUrl": "https://www.linkedin.com/company/techventures",
      "employeeCount": 150,
      "revenue": "10M-50M",
      "foundedYear": 2018,
      "acquisitionSignalScore": 85,
      "signalIndicators": [
        "Recent funding round",
        "Leadership changes",
        "Market consolidation"
      ]
    }
  ],
  "pagination": {
    "currentPage": 1,
    "totalPages": 25,
    "totalCount": 500,
    "hasNextPage": true,
    "hasPreviousPage": false
  },
  "meta": {
    "endpoint": "signals.acquisitions",
    "creditsUsed": 1
  }
}
```

## Common Workflows

### Track M&A activity in SaaS
```json
{"categories": "Technology", "search": "saas", "date_preset": "last_90d"}
```

### Find acquisition targets in healthcare
```json
{"categories": "Healthcare", "countries": "US,GB"}
```

## Important Notes

- `acquisitionSignalScore` ranges from 0–100, with higher scores indicating stronger M&A likelihood
- `signalIndicators` provides human-readable reasons for the score
- Revenue is returned as a range string (e.g. "10M-50M"), not a numeric value
