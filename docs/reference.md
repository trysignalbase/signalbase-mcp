# Reference — All Enums & Constants

## Date Presets

Relative date filters supported across all endpoints. When provided, `date_preset` takes precedence over `dateFrom`/`dateTo`.

```
today, yesterday, last_7d, last_14d, last_30d, last_60d, last_90d,
last_6m, last_1y, last_2y, this_week, this_month, this_quarter,
this_year, last_week, last_month, last_quarter, last_year
```

## Funding Round Types

```
Pre-Seed, Seed, Series A, Series B, Series C, Series D, Series E,
Series F, Series G, Growth, Debt, Grant, IPO, Undisclosed
```

## Subcategories (Signalbase Categories)

```
ai, saas, software, cybersecurity, web3, devtools, analytics, cloud,
iot, fintech, payments, accounting, ecommerce, insurance,
vc & investment, regtech, marketing, advertising, sales, hr tech,
legal, healthcare, biotechnology, education, real estate, energy,
logistics, manufacturing, retail, agriculture, food & beverage,
automotive, aerospace & defense, robotics, telecommunications,
travel, sports, gaming, media, govtech, construction,
environmental services, battery technology, arts, architecture,
cosmetics, science, non-profit
```

## Positions (Job Changes & Hiring)

```
ceo, cto, cfo, coo, vp of engineering, vp of sales, vp of marketing,
head of product, head of growth, head of engineering,
engineering manager, product manager, sales manager, marketing manager,
founder, co-founder
```

## Departments

```
marketing, sales, engineering, product, design, operations,
finance, people, data, customer_success, growth, legal
```

## Seniorities

```
founder, c_level, vp, director, head, lead, manager
```

## Investor Types

```
vc, angel, pe, corporate, government, accelerator,
family_office, hedge_fund, crowdfunding
```

## Country Regions

```
CEE      — Central & Eastern Europe
WE       — Western Europe
NORDICS  — Nordic countries
NA       — North America
LATAM    — Latin America
```

## Country Codes (ISO 3166-1 alpha-2)

All standard ISO country codes are supported. Common examples:

| Code | Country |
|------|---------|
| US | United States |
| GB | United Kingdom |
| DE | Germany |
| FR | France |
| CA | Canada |
| AU | Australia |
| IL | Israel |
| IN | India |
| JP | Japan |
| SE | Sweden |
| NL | Netherlands |
| CH | Switzerland |
| SG | Singapore |
| BR | Brazil |
| KR | South Korea |

## Currency Codes

```
USD, EUR, GBP, JPY, INR, AUD, CAD, CHF, SEK, NOK, DKK, SGD, HKD,
BRL, KRW, CNY, NZD, ZAR, MXN, ILS, PLN, TRY, AED, SAR
```

Most records use `USD`. The currency filter is an exact-match filter — no server-side conversion.

## Sort Fields

### Funding
```
occurred_at, discovered_at, amount, employee_count, founded_year
```

### Acquisitions
```
occurred_at, discovered_at, amount, employee_count
```

### Job Changes
```
occurred_at, discovered_at, person_name, company_name
```

### Hiring
```
date_posted, created_at, title, company_name, location
```

### Investors
```
name, created_at, ticket_size_min, ticket_size_max
```

### Companies
```
name, employee_count, founded_year, created_at
```

## Sort Orders

```
asc, desc
```

## Team Size Ranges (Hiring)

```
1-10, 11-50, 51-200, 201-1000, 1000-plus
```

## Applicant Ranges (Hiring)

```
0-25, 26-50, 51-100, 101-200, 201-plus
```

## Verification Statuses (Funding)

```
verified, unverified, pending
```

## Round Flavors (Funding)

```
bridge, extension, secondary
```

## Signal Source Types

```
press_release, news_article, social_media, blog_post,
sec_filing, crunchbase, pitchbook
```
