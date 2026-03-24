"""
Signalbase MCP Server — Cloudflare Workers (Python / Pyodide)
A Model Context Protocol server that proxies the Signalbase API.
Provides funding signals, acquisition signals, job change signals,
hiring signals, investor data, and company search via MCP tools.
"""

from pyodide.ffi import to_js
from js import Response, Headers, Object, fetch, JSON

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

API_BASE = "https://www.trysignalbase.com/api/v2"
PROTOCOL_VERSION = "2025-03-26"
SERVER_NAME = "signalbase-mcp"
SERVER_VERSION = "1.0.0"

DATE_PRESETS = [
    "today", "yesterday", "last_7d", "last_14d", "last_30d",
    "last_60d", "last_90d", "last_6m", "last_1y", "last_2y",
    "this_week", "this_month", "this_quarter", "this_year",
    "last_week", "last_month", "last_quarter", "last_year",
]

FUNDING_ROUND_TYPES = [
    "Pre-Seed", "Seed", "Series A", "Series B", "Series C",
    "Series D", "Series E", "Series F", "Series G", "Growth",
    "Debt", "Grant", "IPO", "Undisclosed",
]

SUBCATEGORIES = [
    "ai", "saas", "software", "cybersecurity", "web3", "devtools",
    "analytics", "cloud", "iot", "fintech", "payments", "accounting",
    "ecommerce", "insurance", "vc & investment", "regtech",
    "marketing", "advertising", "sales", "hr tech", "legal",
    "healthcare", "biotechnology", "education", "real estate",
    "energy", "logistics", "manufacturing", "retail", "agriculture",
    "food & beverage", "automotive", "aerospace & defense",
    "robotics", "telecommunications", "travel", "sports", "gaming",
    "media", "govtech", "construction", "environmental services",
    "battery technology", "arts", "architecture", "cosmetics",
    "science", "non-profit",
]

POSITIONS = [
    "ceo", "cto", "cfo", "coo", "vp of engineering", "vp of sales",
    "vp of marketing", "head of product", "head of growth",
    "head of engineering", "engineering manager", "product manager",
    "sales manager", "marketing manager", "founder", "co-founder",
]

DEPARTMENTS = [
    "marketing", "sales", "engineering", "product", "design",
    "operations", "finance", "people", "data", "customer_success",
    "growth", "legal",
]

SENIORITIES = [
    "founder", "c_level", "vp", "director", "head", "lead", "manager",
]

INVESTOR_TYPES = [
    "vc", "angel", "pe", "corporate", "government",
    "accelerator", "family_office", "hedge_fund", "crowdfunding",
]

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}

# ──────────────────────────────────────────────────────────────
# Tool definitions
# ──────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_funding_signals",
        "description": (
            "Search for real-time funding round signals. Returns companies that recently "
            "raised funding with round type, amount, investors, and company details. "
            "Costs 1 credit per call."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "integer",
                    "description": "Page number (default 1)",
                    "minimum": 1,
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Results per page, max 50 (default 20)",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 20,
                },
                "search": {
                    "type": "string",
                    "description": "Free-text search by company name or industry keywords",
                },
                "countries": {
                    "type": "string",
                    "description": "Comma-separated country codes or region shortcuts (e.g. 'US,GB' or 'CEE,NORDICS')",
                },
                "categories": {
                    "type": "string",
                    "description": "Pipe-separated LinkedIn industry labels (e.g. 'Software Development|Financial Services')",
                },
                "subcategories": {
                    "type": "string",
                    "description": "Comma-separated Signalbase categories (e.g. 'ai,fintech,saas')",
                    "enum": SUBCATEGORIES,
                },
                "round": {
                    "type": "string",
                    "description": "Comma-separated funding round types (e.g. 'Seed,Series A')",
                },
                "dateFrom": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "dateTo": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
                "date_preset": {
                    "type": "string",
                    "description": "Relative date shorthand (overrides dateFrom/dateTo)",
                    "enum": DATE_PRESETS,
                },
            },
        },
        "annotations": {
            "title": "Search Funding Signals",
            "readOnlyHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "search_acquisition_signals",
        "description": (
            "Search for acquisition and M&A signals. Returns companies showing "
            "acquisition indicators with signal scores and indicator details. "
            "Costs 1 credit per call."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "integer",
                    "description": "Page number (default 1)",
                    "minimum": 1,
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Results per page, max 50 (default 20)",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 20,
                },
                "search": {
                    "type": "string",
                    "description": "Free-text search by company name or industry keywords",
                },
                "countries": {
                    "type": "string",
                    "description": "Comma-separated country codes or region shortcuts",
                },
                "categories": {
                    "type": "string",
                    "description": "Comma-separated company categories",
                },
                "dateFrom": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "dateTo": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
                "date_preset": {
                    "type": "string",
                    "description": "Relative date shorthand (overrides dateFrom/dateTo)",
                    "enum": DATE_PRESETS,
                },
            },
        },
        "annotations": {
            "title": "Search Acquisition Signals",
            "readOnlyHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "search_job_change_signals",
        "description": (
            "Search for leadership and key-hire job change signals. Returns people "
            "who recently changed roles with person name, new role, company, and "
            "LinkedIn URLs. Costs 1 credit per call."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "integer",
                    "description": "Page number (default 1)",
                    "minimum": 1,
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Results per page, max 50 (default 20)",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 20,
                },
                "search": {
                    "type": "string",
                    "description": "Free-text search by company or person keywords",
                },
                "positions": {
                    "type": "string",
                    "description": "Comma-separated positions (e.g. 'cto,head of engineering')",
                },
                "departments": {
                    "type": "string",
                    "description": "Comma-separated departments (e.g. 'engineering,product')",
                },
                "seniorities": {
                    "type": "string",
                    "description": "Comma-separated seniority levels (e.g. 'c_level,vp,head')",
                },
                "personLinkedinUrl": {
                    "type": "string",
                    "description": "Exact LinkedIn profile URL of the person",
                },
                "companyLinkedinUrl": {
                    "type": "string",
                    "description": "Exact LinkedIn company page URL",
                },
            },
        },
        "annotations": {
            "title": "Search Job Change Signals",
            "readOnlyHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "search_hiring_signals",
        "description": (
            "Search for hiring signals (open job postings). Returns active job listings "
            "with title, location, company details, applicant counts, and seniority info. "
            "Costs 1 credit per call. Use count=true to get total count without credits."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "integer",
                    "description": "Page number (default 1)",
                    "minimum": 1,
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Results per page, max 100 (default 20)",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20,
                },
                "search": {
                    "type": "string",
                    "description": "Free-text search across company name, industry, job title, location, and city",
                },
                "countries": {
                    "type": "string",
                    "description": "Comma-separated country codes",
                },
                "states": {
                    "type": "string",
                    "description": "Comma-separated US state codes (e.g. 'CA,NY,TX')",
                },
                "city": {
                    "type": "string",
                    "description": "Free-text city/location search",
                },
                "categories": {
                    "type": "string",
                    "description": "Pipe-separated company industry categories",
                },
                "subcategories": {
                    "type": "string",
                    "description": "Comma-separated Signalbase categories",
                },
                "positions": {
                    "type": "string",
                    "description": "Comma-separated positions to filter by",
                },
                "departments": {
                    "type": "string",
                    "description": "Comma-separated departments to filter by",
                },
                "seniorities": {
                    "type": "string",
                    "description": "Comma-separated seniority levels to filter by",
                },
                "team_size": {
                    "type": "string",
                    "description": "Comma-separated team size ranges (e.g. '51-200,201-1000')",
                },
                "applicants": {
                    "type": "string",
                    "description": "Comma-separated applicant count ranges (e.g. '0-25,26-50')",
                },
                "dateFrom": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "dateTo": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
                "date_preset": {
                    "type": "string",
                    "description": "Relative date shorthand (overrides dateFrom/dateTo)",
                    "enum": DATE_PRESETS,
                },
                "sort_by": {
                    "type": "string",
                    "description": "Sort field",
                    "enum": ["date_posted", "created_at", "title", "company_name", "location"],
                },
                "sort_order": {
                    "type": "string",
                    "description": "Sort direction",
                    "enum": ["asc", "desc"],
                },
                "count": {
                    "type": "boolean",
                    "description": "If true, returns only total count (no credits deducted)",
                },
            },
        },
        "annotations": {
            "title": "Search Hiring Signals",
            "readOnlyHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "search_investors",
        "description": (
            "Search for investors — VCs, angels, PE firms, accelerators, and more. "
            "Returns investor profiles with AUM, investment focus, check sizes, portfolio "
            "details, and contact info. Costs 1 credit per call."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "integer",
                    "description": "Page number (default 1)",
                    "minimum": 1,
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Results per page, max 50 (default 20)",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 20,
                },
                "search": {
                    "type": "string",
                    "description": "Free-text search by investor name or description",
                },
                "countries": {
                    "type": "string",
                    "description": "Comma-separated country codes",
                },
                "categories": {
                    "type": "string",
                    "description": "Comma-separated investor types (e.g. 'vc,angel,pe')",
                },
            },
        },
        "annotations": {
            "title": "Search Investors",
            "readOnlyHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "search_companies",
        "description": (
            "Search and browse the Signalbase company database independently of signals. "
            "Returns company profiles with headcount, industry, growth metrics, and more. "
            "Costs 1 credit per call. Use count=true to get total count without credits."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "integer",
                    "description": "Page number (default 1)",
                    "minimum": 1,
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Results per page, max 100 (default 20)",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20,
                },
                "search": {
                    "type": "string",
                    "description": "Free-text search across name, industry, description, keywords, specialties",
                },
                "countries": {
                    "type": "string",
                    "description": "Comma-separated country codes",
                },
                "industry": {
                    "type": "string",
                    "description": "Comma-separated industry names (exact match)",
                },
                "employee_count_min": {
                    "type": "integer",
                    "description": "Minimum employee count",
                    "minimum": 0,
                },
                "employee_count_max": {
                    "type": "integer",
                    "description": "Maximum employee count",
                    "minimum": 0,
                },
                "founded_year_min": {
                    "type": "integer",
                    "description": "Minimum founded year",
                },
                "founded_year_max": {
                    "type": "integer",
                    "description": "Maximum founded year",
                },
                "sort_by": {
                    "type": "string",
                    "description": "Sort field",
                    "enum": ["name", "employee_count", "founded_year", "created_at"],
                },
                "sort_order": {
                    "type": "string",
                    "description": "Sort direction",
                    "enum": ["asc", "desc"],
                },
                "count": {
                    "type": "boolean",
                    "description": "If true, returns only total count (no credits deducted)",
                },
            },
        },
        "annotations": {
            "title": "Search Companies",
            "readOnlyHint": True,
            "openWorldHint": True,
        },
    },
]

# ──────────────────────────────────────────────────────────────
# Instructions for AI agents
# ──────────────────────────────────────────────────────────────

INSTRUCTIONS = """
# Signalbase MCP — Agent Instructions

## Overview
You have access to the Signalbase API through this MCP server. It provides real-time
business intelligence across six domains: funding rounds, acquisitions, job changes,
hiring (open roles), investors, and companies.

## Credit Costs
Every tool call costs **1 credit** except:
- `count=true` on hiring and companies tools (0 credits, returns total count only)

## Key Workflows

### 1. Market Research
Start with `search_funding_signals` filtered by subcategory and date to find recently
funded companies. Then use `search_companies` to get deeper profiles on interesting ones.

### 2. Sales Prospecting
Use `search_hiring_signals` to find companies actively hiring for roles your product
serves. Combine with `search_funding_signals` (date_preset=last_30d) to find newly
funded companies with budget to spend.

### 3. Investor Lookup
Use `search_investors` to find VCs/angels by type and geography. Cross-reference with
`search_funding_signals` to see their recent investments.

### 4. Leadership Change Monitoring
Use `search_job_change_signals` with seniority=c_level to track C-suite movements.
New leaders often bring new vendor relationships.

### 5. Competitive Intelligence
Use `search_acquisition_signals` to track M&A activity in a sector. Combine with
`search_companies` to profile the acquirers and targets.

## Important Tips

### Countries
- Use ISO 3166-1 alpha-2 codes: US, GB, DE, FR, etc.
- Region shortcuts available: CEE, WE, NORDICS, NA, LATAM
- Multiple values are comma-separated: `countries=US,GB,DE`

### Categories vs Subcategories
- `categories` = LinkedIn industry labels, pipe-separated: `Software Development|Financial Services`
- `subcategories` = Signalbase categories, comma-separated: `ai,fintech,saas`
- These are different classification systems — use both for precision.

### Date Filtering
- Use `date_preset` for relative ranges (e.g. `last_30d`, `this_quarter`)
- `date_preset` overrides `dateFrom`/`dateTo` when both are provided
- For absolute ranges, use `dateFrom` and `dateTo` in YYYY-MM-DD format

### Pagination
- Default page size is 20; max varies by endpoint (50 or 100)
- Always check `pagination.hasNextPage` before fetching more
- Use `count=true` first (on hiring/companies) to preview result size without spending credits

### Boolean Parameters
- The `count` parameter should be sent as `true` (string) in the URL

### Amounts
- All funding amounts are stored as whole USD integers (e.g. 5000000 = $5M)
- Currency field is an exact-match filter, not a converter
"""

# ──────────────────────────────────────────────────────────────
# MCP Prompts
# ──────────────────────────────────────────────────────────────

PROMPTS = [
    {
        "name": "market-scan",
        "description": "Scan a market sector for recent activity — funding, hiring, and M&A signals",
        "arguments": [
            {
                "name": "sector",
                "description": "The market sector to scan (e.g. 'ai', 'fintech', 'cybersecurity')",
                "required": True,
            },
            {
                "name": "geography",
                "description": "Country codes or region (e.g. 'US', 'NORDICS', 'US,GB,DE')",
                "required": False,
            },
        ],
    },
    {
        "name": "investor-research",
        "description": "Research investors active in a given sector and geography",
        "arguments": [
            {
                "name": "sector",
                "description": "Investment focus area (e.g. 'ai', 'healthcare')",
                "required": True,
            },
            {
                "name": "investor_type",
                "description": "Type of investor (e.g. 'vc', 'angel', 'pe')",
                "required": False,
            },
        ],
    },
    {
        "name": "sales-prospecting",
        "description": "Find companies likely to buy — recently funded and actively hiring",
        "arguments": [
            {
                "name": "target_sector",
                "description": "Subcategory of companies to target (e.g. 'saas', 'fintech')",
                "required": True,
            },
            {
                "name": "hiring_department",
                "description": "Department they are hiring for (e.g. 'engineering', 'sales')",
                "required": False,
            },
        ],
    },
    {
        "name": "leadership-changes",
        "description": "Monitor C-suite and VP-level job changes at companies in a sector",
        "arguments": [
            {
                "name": "seniority",
                "description": "Seniority level to track (e.g. 'c_level', 'vp', 'director')",
                "required": True,
            },
            {
                "name": "department",
                "description": "Department to focus on (e.g. 'engineering', 'sales')",
                "required": False,
            },
        ],
    },
]

# ──────────────────────────────────────────────────────────────
# Prompt template content
# ──────────────────────────────────────────────────────────────

PROMPT_TEMPLATES = {
    "market-scan": lambda args: {
        "messages": [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        f"Perform a comprehensive market scan of the **{args.get('sector', 'technology')}** sector"
                        f"{' in ' + args['geography'] if args.get('geography') else ''}.\n\n"
                        "Steps:\n"
                        f"1. Search for funding signals in the last 30 days with subcategories={args.get('sector', 'technology')}\n"
                        f"2. Search for acquisition signals in the same sector\n"
                        f"3. Search for hiring signals to see where demand is growing\n"
                        "4. Summarize the key trends: top funded companies, M&A activity, and hiring hotspots"
                    ),
                },
            }
        ],
    },
    "investor-research": lambda args: {
        "messages": [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        f"Research investors active in the **{args.get('sector', 'technology')}** sector.\n\n"
                        "Steps:\n"
                        f"1. Search investors with categories={args.get('investor_type', 'vc')}\n"
                        f"2. Search recent funding signals in subcategories={args.get('sector', 'technology')} to see which investors are active\n"
                        "3. Compile a list of the most active investors with their focus areas and check sizes"
                    ),
                },
            }
        ],
    },
    "sales-prospecting": lambda args: {
        "messages": [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        f"Find sales prospects in the **{args.get('target_sector', 'saas')}** sector.\n\n"
                        "Steps:\n"
                        f"1. Search funding signals with subcategories={args.get('target_sector', 'saas')} and date_preset=last_30d\n"
                        f"2. Search hiring signals with subcategories={args.get('target_sector', 'saas')}"
                        f"{' and departments=' + args['hiring_department'] if args.get('hiring_department') else ''}\n"
                        "3. Cross-reference to find companies that are both recently funded AND actively hiring\n"
                        "4. Rank them by funding amount and hiring volume"
                    ),
                },
            }
        ],
    },
    "leadership-changes": lambda args: {
        "messages": [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        f"Monitor leadership changes at the **{args.get('seniority', 'c_level')}** level"
                        f"{' in ' + args['department'] if args.get('department') else ''}.\n\n"
                        "Steps:\n"
                        f"1. Search job change signals with seniorities={args.get('seniority', 'c_level')}"
                        f"{'&departments=' + args['department'] if args.get('department') else ''}\n"
                        "2. For notable changes, look up the company using search_companies\n"
                        "3. Summarize who moved where, and what it might mean for the company's direction"
                    ),
                },
            }
        ],
    },
}

# ──────────────────────────────────────────────────────────────
# Tool → API endpoint mapping
# ──────────────────────────────────────────────────────────────

TOOL_ENDPOINTS = {
    "search_funding_signals": "/signals/funding",
    "search_acquisition_signals": "/signals/acquisitions",
    "search_job_change_signals": "/signals/job-changes",
    "search_hiring_signals": "/signals/hiring",
    "search_investors": "/signals/investors",
    "search_companies": "/companies",
}

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _build_query_string(params: dict) -> str:
    """Build a URL query string from a dict, skipping None values.
    Converts Python booleans to lowercase strings for the API."""
    parts = []
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, bool):
            v = "true" if v else "false"
        parts.append(f"{_url_encode(str(k))}={_url_encode(str(v))}")
    return "&".join(parts)


def _url_encode(s: str) -> str:
    """Minimal percent-encoding for query parameter keys/values."""
    out = []
    safe = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~")
    for ch in s:
        if ch in safe:
            out.append(ch)
        elif ch == " ":
            out.append("%20")
        elif ch == "&":
            out.append("%26")
        elif ch == "=":
            out.append("%3D")
        elif ch == "+":
            out.append("%2B")
        elif ch == "|":
            out.append("%7C")
        elif ch == ",":
            out.append("%2C")
        else:
            for b in ch.encode("utf-8"):
                out.append(f"%{b:02X}")
    return "".join(out)


def _json_response(data: dict, status: int = 200) -> Response:
    """Create a JSON Response with CORS headers."""
    body = JSON.stringify(to_js(data, dict_converter=Object.fromEntries))
    headers = Headers.new(to_js(
        {**CORS_HEADERS, "Content-Type": "application/json"},
        dict_converter=Object.fromEntries,
    ))
    return Response.new(body, to_js(
        {"status": status, "headers": headers},
        dict_converter=Object.fromEntries,
    ))


def _error_result(message: str) -> dict:
    """Return an MCP tool error result."""
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


def _success_result(data) -> dict:
    """Return an MCP tool success result with JSON-serialized data."""
    import json
    return {
        "content": [{"type": "text", "text": json.dumps(data, indent=2, default=str)}],
    }


# ──────────────────────────────────────────────────────────────
# API proxy
# ──────────────────────────────────────────────────────────────

async def _call_api(endpoint: str, params: dict, api_key: str) -> dict:
    """Make an authenticated GET request to the Signalbase API."""
    import json as json_mod

    qs = _build_query_string(params)
    url = f"{API_BASE}{endpoint}"
    if qs:
        url = f"{url}?{qs}"

    opts = to_js({
        "method": "GET",
        "headers": {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    }, dict_converter=Object.fromEntries)

    resp = await fetch(url, opts)
    text = await resp.text()

    try:
        data = json_mod.loads(text)
    except Exception:
        data = {"raw": text}

    if not resp.ok:
        return {"error": True, "status": resp.status, "body": data}

    return data


# ──────────────────────────────────────────────────────────────
# JSON-RPC handler
# ──────────────────────────────────────────────────────────────

async def _handle_jsonrpc(request_body: dict, api_key: str) -> dict:
    """Route a JSON-RPC 2.0 request to the appropriate handler."""
    method = request_body.get("method", "")
    req_id = request_body.get("id")
    params = request_body.get("params", {})

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
            },
            "instructions": INSTRUCTIONS,
        }

    elif method == "notifications/initialized":
        return None

    elif method == "tools/list":
        result = {"tools": TOOLS}

    elif method == "prompts/list":
        result = {"prompts": PROMPTS}

    elif method == "prompts/get":
        prompt_name = params.get("name", "")
        if prompt_name in PROMPT_TEMPLATES:
            prompt_args = params.get("arguments", {})
            result = PROMPT_TEMPLATES[prompt_name](prompt_args)
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32602,
                    "message": f"Unknown prompt: {prompt_name}",
                },
            }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        if tool_name not in TOOL_ENDPOINTS:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32602,
                    "message": f"Unknown tool: {tool_name}",
                },
            }

        if not api_key:
            result = _error_result(
                "No API key provided. Pass your Signalbase API key as "
                "Authorization: Bearer <key> in the request header."
            )
        else:
            endpoint = TOOL_ENDPOINTS[tool_name]
            api_response = await _call_api(endpoint, tool_args, api_key)

            if isinstance(api_response, dict) and api_response.get("error") is True:
                status = api_response.get("status", "unknown")
                body = api_response.get("body", {})
                msg = body.get("error", body.get("message", str(body))) if isinstance(body, dict) else str(body)
                result = _error_result(f"API error (HTTP {status}): {msg}")
            else:
                result = _success_result(api_response)

    elif method == "ping":
        result = {}

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}",
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": result,
    }


# ──────────────────────────────────────────────────────────────
# Cloudflare Workers entry point
# ──────────────────────────────────────────────────────────────

async def on_fetch(request, env):
    if request.method == "OPTIONS":
        return Response.new("", to_js(
            {
                "status": 204,
                "headers": Headers.new(to_js(CORS_HEADERS, dict_converter=Object.fromEntries)),
            },
            dict_converter=Object.fromEntries,
        ))

    if request.method != "POST":
        return _json_response(
            {"error": "Method not allowed. Use POST for MCP JSON-RPC requests."},
            405,
        )

    auth_header = request.headers.get("Authorization") or ""
    api_key = ""
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:].strip()

    try:
        import json as json_mod
        body_text = await request.text()
        body = json_mod.loads(body_text)
    except Exception as e:
        return _json_response(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}},
            400,
        )

    response = await _handle_jsonrpc(body, api_key)

    if response is None:
        return Response.new("", to_js(
            {
                "status": 204,
                "headers": Headers.new(to_js(CORS_HEADERS, dict_converter=Object.fromEntries)),
            },
            dict_converter=Object.fromEntries,
        ))

    return _json_response(response)
