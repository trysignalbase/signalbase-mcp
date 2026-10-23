# Recruiting v3 connector

Core `/v3` uses original-request recruiting searches, retaining people, contact
collection and monitoring. Discover current tools and reconnect clients with
cached schemas. Explicit `/v3/recruiting` and `/v3/monitoring` retain structured
search inputs; root/v2 remain unchanged. Free preview stays structured.

For an uncertain old structured Core call, retry through `/v3/recruiting` only
within its original 10-minute replay window, with identical arguments and the
same `operation_id`. If expired or timing is unknown, inspect/reconcile usage
first; do not repeat the paid call. A transport failure does not prove a refund.

## 3.12.0 release candidate (20 October 2026)

The paired app vocabulary distinguishes counsel professions and rank, in-house
lawyers, Head of Talent and People leadership from broad legal/people functions.
Sales Operations is not an exact Head of Sales match. Eligibility belongs to the
same directly owned title clause; supporting another leader is not holding that
role. Related alternatives do not establish the requested profession or rank.

Structured `search_appointments` accepts `role_mode: "role"` (the default) or
`"title"`. Role mode interprets the reviewed concepts; title mode retains a
literal phrase such as `People leaders` without expanding it to Head/VP People.
One global mode applies to the whole role list; mixed literal/business
requirements need separate, explicit scopes. Request mode preserves the user's
literal wording and never turns an unresolved BOTH-role company requirement
into a count of two unrelated titles.

The app and Worker must ship the same generated 3.12.0 contract pair. A stale
contract is rejected before search/accounting rather than executed under changed
definitions. Existing classic, HR and monitoring profiles retain their contracts.

## Local 3.7.7 release candidate (29 September 2026)

The generated contract pair follows the app's Munich/Saxony vocabulary,
preview rate-window and failed-search absence-shape corrections. Worker
routing remains as verified in 3.7.6.

## Local 3.7.6 post-review candidate (29 September 2026)

This generated contract pair follows the app's reviewed first-hire and
failed-page corrections. The Worker preview-route fix from 3.7.5 is unchanged.

## Local 3.7.5 candidate (29 September 2026)

The plain-request `/v3/recruiting/request` profile sends
`preview_recruiting_search` to the app's structured preview route with the
structured contract hash. Search calls still use the request adapter. Preview
remains free; the paired app bounds failed-search recovery envelopes to 36 KB.
Both sides use the generated 3.7.5 contract pair.

## Local 3.7.4 candidate (29 September 2026)

The paired app and Worker contract is generated from the app checkout. Unified
v3 profiles and `/v3/recruiting/request` expose `search_people` for a separate
company lookup. A company identifier lookup can return current employees with
`matched_signal: null` when no signal-led people match. Function, seniority,
person-location and signal-type filters disable that fallback. Company search
records provide a `field_coverage.people.follow_up` when a usable domain or
LinkedIn company URL is present. Each executed people lookup costs a credit;
`count=true` is free. The lookup is not a complete roster or org chart.

The app contract now accepts 50 normalized company domains while other lists
retain their prior limits. The Worker passes those criteria through unchanged.
Use the exact generated contract pair during candidate verification.

`preview_recruiting_search` is a free, authenticated structured candidate
count in both recruiting profiles. It reports distinct indexed company and
posting IDs for completed SQL scope, not qualified/live-verified matches. It
does not invoke original-request planning or provider checks. Unsupported
evidence/outlook/HQ-profile claims are rejected. Each paid follow-up search is
separate. The current MCP response default remains `full`; `compact` is opt-in
until overflow continuation validation is complete.

The app bounds search responses to 36 KB so connector clients can display
them. Dense pages become a `bounded_summary` or `lead_index` with every
returned ID, qualification status, exact continuation and a primary returned
job/source link where one exists. Nested evidence counts show what was omitted;
use `get_evidence` for shown IDs or narrow the query. An unrepresentable page
is uncharged and returns a same-position retry. This Worker forwards the
app-owned response unchanged. Release it only with the paired app commit.
Evidence lookups have the same 36 KB cap, with excerpt truncation flags and
every requested ID/status retained. Lead indexes now distinguish total matching
postings from displayed jobs and expose relevant growth, investor, expiry and
employer/location flags plus evidence-fallback state.
The paired app recognizes `Munich`/`München`/`Muenchen` in German work-city
filters and returns unknown counts after failed searches so a connector cannot
mistake a database timeout for proof of no source. A timed-out OR evidence
search can return single-claim `recovery_calls` for explicitly labelled
diagnostic alternatives.

Use Worker `/v3/recruiting` or app `/api/mcp/v3/recruiting/c/<token>`. Deploy the app's v3 recruiting routes first. Keyed URLs contain credentials and must not appear in logs or reports.

The tools search companies, appointments and investor participation, and retrieve evidence by ID. All search definitions and execution live in the app. The Python profile forwards POST requests and preserves the app's matches, alternatives, review items, source evidence, coverage and usage. An ordinary role search can retrieve labelled related titles without a count-mode prerequisite. The generated instructions ask clients to cite returned links for each named lead and run one supported labelled fallback when a completed strict search yields too few matches.

`request` is the original wording for audit; this structured profile also requires business `criteria`. Company HQ, work location and evidence geography remain independent. Omit hiring for company-only growth research. Historical VC/PE backing has no implicit recency. Required office/founder claims drive evidence discovery. Follow `next_call` for unfinished coverage; never report an unsearched market as empty.

The MCP resource `signalbase://recruiting/v3/guide` provides generated concepts and executable examples. Essential semantics remain in each tool's description/schema. The companion app document `docs/recruiting-v3.md` is the full implementation guide.

`src/recruiting_contract.py` is generated by the app's `scripts/export-recruiting-contract.ts` with `RECRUITING_WORKER_PATH` pointing at this checkout. Run the generator with `--check` when reviewing paired changes. Never hand-edit the generated contract. `tests/test_recruiting_v3.py` validates discovery examples, nested inputs, result preservation and transport recovery; existing profile tests protect compatibility.

After a transport failure, use the returned `operation_id` only with identical arguments. This reuses the app's ten-minute idempotency reservation; a different/new request needs a new ID. The Worker does not automatically issue a second paid request after uncertain execution.

The separate `/v3/recruiting/request` profile accepts the original request and paging/source controls, forwarding interpretation to the app's explicitly configured planner. Its keyed app path is `/api/mcp/v3/recruiting/request/c/<token>`. Planner usage and interpreted clauses are returned; continuation reuses a cached plan. This profile is experimental and does not silently replace the structured profile. The structured profile invokes no server-side model.

Release acceptance requires Opus 5 and weaker-model usability, plus the intended Cowork client and deployed HTTP path. Claude Code fixture runs exercise this module's actual dispatcher through a test stdio bridge; they do not establish deployed proxy/billing behavior. Deploy the app and approved evidence indexes before enabling the matching Worker contract. Reverting to the previous connector path is the rollback.
