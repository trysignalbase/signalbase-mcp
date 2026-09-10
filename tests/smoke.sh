#!/usr/bin/env bash
# Smoke test against a deployed (or `wrangler dev`) Worker.
#
#   MCP=https://mcp.trysignalbase.com KEY=sb_... bash tests/smoke.sh
#
# Only count=true calls are free; steps 4 and 5 execute paid searches (1 credit each).
# Requires curl and jq.

set -euo pipefail

: "${MCP:?set MCP to the worker URL, e.g. https://mcp.trysignalbase.com}"
: "${KEY:?set KEY to a Signalbase API key}"

rpc() {
  # rpc <method> <params-json>
  curl -sS -X POST "$MCP" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $KEY" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":$2}"
}

call() {
  # call <tool> <arguments-json>  → prints the tool's text payload
  rpc tools/call "{\"name\":\"$1\",\"arguments\":$2}" | jq -r '.result.content[0].text'
}

echo "== 1. tools/list: new keys present, no enum on subcategories"
TOOLS=$(rpc tools/list '{}')
echo "$TOOLS" | jq -e '.result.tools[] | select(.name=="search_funding_signals") | .inputSchema.properties | has("employee_count_max")' >/dev/null
echo "$TOOLS" | jq -e '.result.tools[] | select(.name=="search_hiring_signals") | .inputSchema.properties | has("job_countries") and has("company_domain") and has("include_expired")' >/dev/null
echo "$TOOLS" | jq -e '[.result.tools[] | .inputSchema.properties.subcategories? | select(. != null) | has("enum")] | all(. == false)' >/dev/null
echo "$TOOLS" | jq -r '.result.tools[] | "\(.name): \(.inputSchema.properties | keys | length) params"'

echo "== 2. hiring countries=NORDICS count (free)"
call search_hiring_signals '{"filter_version":2,"countries":"NORDICS","count":true}' | jq -c '.'

echo "== 3. funding countries=EU employee_count_max=10 date_preset=last_90d count (free)"
call search_funding_signals '{"filter_version":2,"countries":"EU","employee_count_max":10,"date_preset":"last_90d","count":true}' | jq -c '.'

echo "== 4. funded pool → hiring by company_domain (2 paid calls)"
FUNDED=$(call search_funding_signals '{"filter_version":2,"countries":"EU","employee_count_max":10,"date_preset":"last_90d","limit":50}')
DOMAINS=$(echo "$FUNDED" | jq -r '[.data[]?.companyWebsite // empty | sub("^https?://";"") | sub("^www\\.";"") | sub("/.*$";"")] | unique | .[:50] | join(",")')
echo "domains ($(echo "$DOMAINS" | tr ',' '\n' | grep -c . || true)): ${DOMAINS:0:200}..."
if [ -n "$DOMAINS" ]; then
  call search_hiring_signals "{\"filter_version\":2,\"include_expired\":false,\"company_domain\":\"$DOMAINS\",\"departments\":\"sales\",\"limit\":100,\"sort_by\":\"date_posted\"}" \
    | jq -c '{total: .pagination.totalCount, rows: (.data | length), sample: [.data[:3][] | {companyName, title, jobUrl, validThrough}]}'
else
  echo "no domains in funded pool — skipping hiring call"
fi

echo "== 5. verbose vs trimmed byte size (2 paid calls)"
TRIMMED=$(call search_funding_signals '{"filter_version":2,"countries":"EU","date_preset":"last_30d","limit":20,"verbose":false}' | wc -c)
VERBOSE=$(call search_funding_signals '{"filter_version":2,"countries":"EU","date_preset":"last_30d","limit":20,"verbose":true}' | wc -c)
echo "trimmed=${TRIMMED}B verbose=${VERBOSE}B"

echo "OK"
