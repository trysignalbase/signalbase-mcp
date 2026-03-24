---
name: signalbase-acquisition-signals
description: Use when the user asks about acquisitions, M&A activity, merger targets, companies being acquired, or acquisition indicators.
argument-hint: "[sector, geography, or company name]"
---

# Acquisition Signals Skill

## Tool: `search_acquisition_signals`
**Endpoint:** `GET /signals/acquisitions` | **Cost:** 1 credit

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default 1) |
| `limit` | integer | Results per page, max 50 |
| `search` | string | Company name or keywords |
| `countries` | string | Comma-separated country codes |
| `categories` | string | Comma-separated categories |
| `dateFrom` | string | YYYY-MM-DD |
| `dateTo` | string | YYYY-MM-DD |
| `date_preset` | string | Relative date shorthand |

## Example Workflows

### Recent M&A in tech
```json
{"categories": "Technology", "date_preset": "last_90d"}
```

### Acquisition targets in healthcare
```json
{"categories": "Healthcare", "countries": "US,GB"}
```

## Gotchas

- `acquisitionSignalScore` is 0–100 (higher = stronger M&A signal)
- `signalIndicators` gives human-readable reasons for the score
- Revenue in response is a range string like "10M-50M"
