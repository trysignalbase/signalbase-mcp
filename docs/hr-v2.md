# HR MCP v2

HR MCP v2 adds four recruiting workflows to the six existing search tools. No new
account or API key is required. All operations use the existing API and data;
historical records are not repaired or backfilled.

Two smaller opt-in profiles are also available. `/v2/brief` preserves the original
concise-card contract. `/v2/recruiting` is the versioned 2.1 projection: it returns
the same candidate population in compact TextContent only, merges duplicate funding
and review data by stable signal ID, shortens appointment excerpts, removes raw
aliases, and hoists repeated caveats. Classic and `/v2` are unchanged; `/v2/brief`
keeps its fields and structured-content shape while using compact JSON text and
correcting duplicate requirement/unknown-cost bookkeeping.

## Workflow tools

| Tool | Purpose |
|---|---|
| `find_hiring_companies` | Companies with indexed open roles, explicit HQ/job geography, headcount/growth, caller-defined startup rules, posting age, source-text claims and optional live ATS checks. |
| `find_funded_hiring_companies` | Funding/hiring intersection joined in the API before counts and pagination; includes matching funding and source-identity evidence. |
| `find_hiring_outlook` | Bounded search for leadership/funding triggers, followed by pre-trigger posting/announced-join checks and current hiring checks. |
| `research_investor_activity` | Investor HQ lookup joined to actual round-participation records, e.g. Toronto investors in major US rounds. |

The hiring workflows return separate exact posting/company totals for `count=true`
(two free requests), or grouped companies with source links, interpreted filters,
unknown requirements, continuation and actual usage. A partial batch is never called
exhaustive. A data workflow can use multiple API credits; each underlying data request
costs one credit. Request and 45-second execution budgets are enforced.
Responses separate `query_status`, `match_status`, and `evidence_level`; legacy
`status` mirrors query completeness. The JSON remains in the standard text-content
response used by the negotiated 2025-03 protocol revision.

Examples:

```json
{"name":"find_hiring_companies","arguments":{"role":"bdr","headcount_max":9,"job_locations":["Belgium","US","Netherlands","Luxembourg","Dubai"],"required_evidence":["founder_led_sales"],"count":true}}
{"name":"find_funded_hiring_companies","arguments":{"role":"GTM","funding_within_days":90,"posting_age_days_min":31,"required_evidence":["continuous_vacancy"],"max_pages":1}}
{"name":"find_hiring_companies","arguments":{"role":"design or marketing","company_countries":["GB"],"headcount_max":200,"headcount_growth_window":"3m","headcount_growth_min":10,"startup_definition":{"founded_year_min":2020,"max_headcount":200},"posted_within_days":30,"verify_live":true}}
{"name":"research_investor_activity","arguments":{"investor_headquarters":"Toronto","company_countries":["US"],"round_amount_min":10000000,"funding_within_days":365}}
```

`job_locations` ORs countries and supported job metros. Dubai stays a city in the UAE.
Bay Area means job location; HQ city remains unavailable. Company HQ
countries are specified separately with `company_countries`. The HQ-only
`exclude_company_countries` filter can find Polish jobs at foreign companies.
For creative/digital recruiting, `sector="creative/digital"` maps a documented
narrow set of creative-services industries and can be combined with
`role="design or marketing"`; the interpreted query exposes the exact mapping.

`required_evidence` makes unsupported claims explicit. Explicit employer wording can
support founder-led sales/right-hand, first-hire, scaling, office or budget claims and
is returned with a bounded quote and job URL. Public Greenhouse, Lever and Ashby records
can support live-vacancy status; all other job sources remain unknown. Founder origin,
current ownership, current funding stage and continuously unfilled jobs are never
inferred from proxies. Stored company headcounts
are labelled stored/estimated rather than verified exact. Round labels and job
associations can be wrong; source URLs and data-quality limits
are returned without rewriting those records.

Every stored funding event date must support the requested recency window; a recent
announcedDate cannot promote an old occurredAt. Both fields, stored verification,
source titles/links/dates and identity uncertainty are returned. A past Seed round
does not establish current stage. No company blacklist or arbitrary headcount cap is
used as evidence validation. Investor workflow lead claims remain unverified unless
source titles support them. Staffing exclusions use known industry labels; remote
filtering requires title/location work-arrangement wording, rejects occupations such
as “remote sensing”, and checks description text for negative remote statements.

## Connect

After deploying the Worker, configure a Streamable HTTP MCP connection with:

```text
URL: https://mcp.trysignalbase.com/v2
Authorization: Bearer <your existing API key>
```

For Cowork or another client that uses the keyed URL, deploy the app change too and use:

```text
https://www.trysignalbase.com/api/mcp/v2/c/<your existing API key>
Authentication: None (the URL carries the key)
```

Existing connections keep using `https://mcp.trysignalbase.com` or
`/api/mcp/c/<key>`. They receive improved matching with full responses and their
original historical defaults. They are not redirected to v2.

## Ask normally

Examples:

- “Find companies headquartered in the Nordics hiring BDRs or engineers.”
- “Which companies with fewer than 50 employees are hiring salespeople in Germany?”
- “Show hiring activity last year, grouped by company.”

The `recruiting-market` prompt accepts `role` and `geography`. The agent can also
call `search_hiring_signals` directly:

```json
{
  "role": "bdr or engineers",
  "countries": "NORDICS",
  "country_scope": "hq",
  "headcount_max": 49,
  "count": true
}
```

No compatibility flag is needed. Mixed roles retain OR semantics, country shortcuts
expand, and the response includes a best-effort breakdown for explicit multi-country
lists. Region shortcuts are counted as a region, not expanded into extra probes.

The `likely-first-hire` prompt ranks previously quiet companies after a New VP,
New Head of, New C-level, Series A or Seed signal using the supplied 30/60/90-day
benchmark floors. It checks current hiring separately, never combines overlapping
rates, and does not infer a particular role from an any-hire benchmark.

## Defaults and controls

- Source claims reject negated, historical, hypothetical and different-employer
  statements. `first_hire_scope` separates company, regional and functional first
  hires; a regional first hire requires an explicit place and `job_locations`.
- HR results include `screening` flags for employer/intermediary, explicit headcount,
  source-company and specific software-role conflicts. Flags preserve the rows and
  source evidence while setting `match_status=needs_review`. They do not repair data.
- `verify_live` can follow explicit Apply links and validated redirects from the
  supported public job boards to Greenhouse, Lever or Ashby. Job identity and title
  must match before verification; empty/invalid JSON never verifies a vacancy.
  The response includes the source chain and counters for attempts, HTTP requests,
  resolved postings and verified postings. Missing public listings remain unknown.
- Description workflows use `include_total=false` by default: total counts are null,
  and `hasNextPage` is computed from a lookahead row. `count=true` remains an exact
  indexed count. Timeout usage explicitly marks unknown credit cost.

- Hiring searches request open postings. An explicit historical end date or past
  calendar preset retains history. `include_expired=true` includes history;
  explicit `false` filters to open postings even with dates.
- `as_of` anchors relative windows and the posting-freshness test. It is not a
  historical index snapshot; later-indexed backdated rows can change a replay.
- Compact responses keep `data` rows. Hiring also adds `companies`, grouped from
  the current page. `verbose=true` returns the full payload; `group_by_company=false`
  suppresses the additional groups.
- Pagination and free counts measure postings, not unique companies. A company
  can appear on more than one page. Grouping merges identical titles and is not
  a count of individual vacancies.
- Multi-country counts can run up to six additional probes, each bounded to five
  seconds. Failed probes are `null` with a note; the combined total remains usable.
  `by_country=false` disables probes. Every request still consumes API rate-limit
  capacity, even when it costs no credits.
- Country errors are explicit on v2. `NORTH_AMERICA` means the region; `NA` means
  Namibia. The classic endpoint continues accepting legacy country literals.

“Open” is an indexed freshness estimate: `validThrough` has not passed, or a posting without
an expiry is at most 60 days old. Set `verify_live=true` or require
`verified_live_vacancy` to check supported public ATS records; unsupported URLs remain
unknown rather than being fetched. Use posting/source links as evidence.

Each executed data search costs one credit, including empty results. `count=true`
is free. All explicit controls remain available on both endpoints.
