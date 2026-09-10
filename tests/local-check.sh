#!/usr/bin/env bash
# Free-call check matrix for the Georgi fixes. Works against `wrangler dev`
# (MCP=http://localhost:8787) or the deployed Worker. Every call uses
# count=true, so nothing here spends credits.
#
#   MCP=http://localhost:8787 KEY=ff_live_... bash tests/local-check.sh
#
# Columns: what | expected on the OLD api/worker | expected on the NEW ones.

set -uo pipefail
: "${MCP:=http://localhost:8787}"
: "${KEY:?set KEY to an API key valid for the API the Worker points at}"

rpc() { curl -sS -m 90 -X POST "$MCP" -H "Content-Type: application/json" -H "Authorization: Bearer $KEY" -d "$1"; }
text() { python -c 'import sys,json
r=json.load(sys.stdin)
if "error" in r: print("RPC-ERROR", r["error"]["message"][:120]); sys.exit()
t=r["result"]["content"][0]["text"]
if t.startswith("{"):
    d=json.loads(t); print("total=%s credits=%s" % (d["pagination"]["totalCount"], d["meta"]["creditsUsed"]))
else:
    print(t.replace("\n"," ")[:140])'; }
count() { # count <label> <tool> <args-json> <old> <new>
  printf "%-46s %-60s " "$1" "old: $4 | new: $5"
  rpc "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$2\",\"arguments\":$3}}" | text
}

echo "== schema"
rpc '{"jsonrpc":"2.0","id":0,"method":"tools/list"}' | python -c 'import sys,json
t={x["name"]:x["inputSchema"]["properties"] for x in json.load(sys.stdin)["result"]["tools"]}
print("  funding.employee_count_max :", "employee_count_max" in t["search_funding_signals"], "(old: False)")
print("  hiring.include_expired     :", "include_expired" in t["search_hiring_signals"], "(old: False)")
print("  hiring.company_domain      :", "company_domain" in t["search_hiring_signals"], "(old: False)")
print("  subcategories has enum     :", "enum" in t["search_funding_signals"]["subcategories"], "(old: True)")
print("  server version             :", end=" ")'
rpc '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"check","version":"0"}}}' | python -c 'import sys,json; print(json.load(sys.stdin)["result"]["serverInfo"]["version"], "(old: 1.0.0)")'

echo "== countries (free counts)"
count "hiring countries=NORDICS"        search_hiring_signals  '{"filter_version":2,"countries":"NORDICS","count":true}'                              "0"       ">0 (= SE+NO+DK+FI+IS)"
count "hiring countries=Sweden"         search_hiring_signals  '{"filter_version":2,"countries":"Sweden","count":true}'                               "0"       "= countries=SE"
count "hiring countries=SE"             search_hiring_signals  '{"filter_version":2,"countries":"SE","count":true}'                                   "n"       "same n"
count "hiring countries=Narnia"         search_hiring_signals  '{"filter_version":2,"countries":"Narnia","count":true}'                               "total=0" "API error 400 naming Narnia"
count "funding countries=EU"            search_funding_signals '{"filter_version":2,"countries":"EU","date_preset":"last_90d","count":true}'          "0"       ">0"
count "jobchange countries=DACH"        search_job_change_signals '{"filter_version":2,"countries":"DACH","count":true}'                              "0"       ">0"

echo "== Georgi's pool (free counts)"
count "funding EU <=10 staff last_90d"  search_funding_signals '{"filter_version":2,"countries":"EU","employee_count_max":10,"date_preset":"last_90d","count":true}' "0 (EU unknown)" "~275 on prod data"
count "hiring EU 1-10 sales last_90d"   search_hiring_signals  '{"filter_version":2,"countries":"EU","team_size":"1-10","departments":"sales","date_preset":"last_90d","count":true}' "0" ">=0, no Syngenta/Publicis after backfill"

echo "== freshness"
count "hiring US default"               search_hiring_signals  '{"filter_version":2,"countries":"US","count":true}'                                   "N"       "N (unchanged historical total)"
count "hiring US include_expired=true"  search_hiring_signals  '{"filter_version":2,"countries":"US","count":true,"include_expired":true}'            "400 unknown param" "N (= default)"

echo "== identifier lists"
count "hiring company_domain list"      search_hiring_signals  '{"filter_version":2,"company_domain":"stripe.com,notion.so","departments":"sales","count":true}' "400 Invalid company_domain" "total=..."
count "hiring company_domain as array"  search_hiring_signals  '{"filter_version":2,"company_domain":["stripe.com","notion.so"],"count":true}'          "400"     "total=... (Worker joins the list)"

echo "== seniority"
count "jobchange seniorities=c_level"   search_job_change_signals '{"filter_version":2,"seniorities":"c_level","count":true}'                         "~105k (Director bug)" "much smaller than seniorities=director"
count "jobchange seniorities=director"  search_job_change_signals '{"filter_version":2,"seniorities":"director","count":true}'                        "~55k"    "unchanged"
echo "done"

count "hiring US open only opt-in" search_hiring_signals '{"countries":"US","count":true,"include_expired":false}' "400 unknown param" "N_live <= N"
