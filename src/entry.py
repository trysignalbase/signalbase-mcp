"""
Signalbase MCP Server — Cloudflare Workers (Python / Pyodide)
A Model Context Protocol server that proxies the Signalbase API.
Provides funding signals, acquisition signals, job change signals,
hiring signals, investor data, and company search via MCP tools.
"""

import html
import asyncio
import json
import re
import time
from copy import deepcopy
from urllib.parse import unquote, urlsplit
from datetime import datetime, timedelta, timezone
from pyodide.ffi import to_js
from js import Response, Headers, Object, fetch, JSON

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

API_BASE = "https://www.trysignalbase.com/api/v2"
# Overridable per request from the Worker env binding `API_BASE` (wrangler
# `--var API_BASE:http://localhost:3000/api/v2` or `[env.local] vars`) so the
# Worker can be pointed at a local checkout of the app for end-to-end testing.
_api_base_override: str | None = None


def _resolve_api_base(env=None) -> str:
    """Pick the API base: explicit env binding > module default."""
    value = None
    if env is not None:
        try:
            value = getattr(env, "API_BASE", None)
        except Exception:
            value = None
    if value:
        return str(value).rstrip("/")
    return API_BASE
PROTOCOL_VERSION = "2025-03-26"
SERVER_NAME = "signalbase-mcp"
SERVER_VERSION = "1.1.0"

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

COUNTRY_REGIONS = [
    "EU", "EUROPE", "DACH", "BENELUX", "NORDICS", "CEE", "WE", "NORTH_AMERICA", "LATAM",
]

TEAM_SIZE_RANGES = ["1-10", "11-50", "51-200", "201-1000", "1000-plus"]
APPLICANT_RANGES = ["0-25", "26-50", "51-100", "101-200", "201-plus"]

# Opt-in response trimming (verbose=false, see _trim_response)
TRIM_MAX_CHARS = 300
TRIM_TEXT_FIELDS = {
    "descriptionText", "companyDescription", "description",
    "postContent", "personHeadline",
}
TRIM_HTML_FIELDS = TRIM_TEXT_FIELDS | {"title", "name", "companyName", "personName", "investorName", "location", "city"}
TRIM_DROP_FIELDS = {
    "companyLogo", "companyLogoUrl", "logoUrl", "logo_url", "image",
}
# Evidence lists: keep the first few entries in trimmed mode (the API returns up
# to ~20 per row, mostly duplicate coverage of the same announcement).
TRIM_LIST_FIELDS = {"sources": 3}
# Keys dropped from entries of these nested lists in trimmed mode (internal ids
# an agent cannot use through the MCP).
TRIM_NESTED_DROP = {"investors": {"id"}, "sources": {"isPrimary"}}
# Fields the API returns as JSON text inside JSON ("[\"A\",\"B\"]"); decoded
# and de-duplicated in trimmed mode so an LLM sees a real list.
TRIM_JSON_STRING_FIELDS = {"companyCategories", "categories", "countries", "keywords", "specialties", "companySpecialties"}
TRIM_META = {"trimmed": True, "hint": "pass verbose=true for full text"}

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    # Browser MCP clients (e.g. the MCP Inspector) send the protocol/session
    # headers on every request; without them the preflight fails.
    "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept, Mcp-Protocol-Version, Mcp-Session-Id",
}

# ──────────────────────────────────────────────────────────────
# Shared input-schema property snippets
# ──────────────────────────────────────────────────────────────

PAGE_PROP = {
    "type": "integer",
    "description": "Page number (default 1)",
    "minimum": 1,
    "default": 1,
}


def _limit_prop(maximum: int) -> dict:
    return {
        "type": "integer",
        "description": f"Results per page, max {maximum} (default 20)",
        "minimum": 1,
        "maximum": maximum,
        "default": 20,
    }


COUNT_PROP = {
    "type": "boolean",
    "description": (
        "If true, returns only the total matching count. FREE on every tool "
        "(0 credits) — use it to size a query before spending a credit."
    ),
}

VERBOSE_PROP = {
    "type": "boolean",
    "default": True,
    "description": (
        "Worker-only flag, never forwarded to the API. Default true returns the original full payload. Explicit false opts into trimming: long text "
        "fields (descriptions, post content, headlines) are truncated to 300 "
        "characters and logo/image URLs are dropped to save tokens. Pass true "
        "to receive the full, untrimmed API payload."
    ),
}

COUNTRIES_PROP = {
    "type": "string",
    "description": (
        "Comma-separated countries. Improved matching is automatic: ISO 3166-1 alpha-2 codes (US,GB,DE), "
        "English names (Sweden, Germany) or region shortcuts "
        f"{', '.join(COUNTRY_REGIONS)}. Unknown values return HTTP 400 only with filter_version=2."
    ),
}

EXCLUDE_COUNTRIES_PROP = {
    "type": "string",
    "description": (
        "Comma-separated countries to exclude. Same values as `countries` "
        "(ISO codes, English names, or region shortcuts)."
    ),
}

EMPLOYEE_MIN_PROP = {
    "type": "integer",
    "description": "Minimum company employee count (inclusive)",
    "minimum": 0,
}

EMPLOYEE_MAX_PROP = {
    "type": "integer",
    "description": (
        "Maximum company employee count (inclusive). Example: 10 for micro "
        "companies. Rows with unknown headcount are excluded."
    ),
    "minimum": 0,
}

FOUNDED_MIN_PROP = {"type": "integer", "description": "Minimum founded year (e.g. 2020)"}
FOUNDED_MAX_PROP = {"type": "integer", "description": "Maximum founded year (e.g. 2025)"}

COMPANY_DOMAIN_LIST_PROP = {
    "type": "string",
    "description": (
        "Company website domain(s), comma-separated, up to 50 per call "
        "(strict canonical match, e.g. 'stripe.com,vercel.com'). Checking a "
        "whole pool of up to 50 domains costs ONE credit — use this to test a "
        "funded list for open roles."
    ),
}

COMPANY_LINKEDIN_LIST_PROP = {
    "type": "string",
    "description": (
        "Company LinkedIn page URL(s), comma-separated, up to 50 per call "
        "(strict canonical match, e.g. 'https://www.linkedin.com/company/stripe'). "
        "One credit for the whole list."
    ),
}

DATE_FROM_PROP = {"type": "string", "description": "Start date in YYYY-MM-DD format"}
DATE_TO_PROP = {"type": "string", "description": "End date in YYYY-MM-DD format"}
DATE_PRESET_PROP = {
    "type": "string",
    "description": "Relative date shorthand (overrides dateFrom/dateTo)",
    "enum": DATE_PRESETS,
}

CATEGORIES_PIPE_PROP = {
    "type": "string",
    "description": (
        "Pipe-separated LinkedIn industry labels "
        "(e.g. 'Software Development|Financial Services')"
    ),
}

SUBCATEGORIES_PROP = {
    "type": "string",
    "description": (
        "Comma-separated Signalbase categories, multi-select (e.g. 'ai,fintech,saas'). "
        f"Allowed values: {', '.join(SUBCATEGORIES)}."
    ),
}

POSITIONS_PROP = {
    "type": "string",
    "description": (
        "Comma-separated positions matched against the job TITLE "
        "(e.g. 'cto,head of engineering'; 'bdr' also matches SDR / business "
        "development / sales development titles). For a whole function "
        "(any sales role, any engineering role) prefer `departments`: small "
        "companies word titles freely in their hiring posts. "
        f"Known values: {', '.join(POSITIONS)}."
    ),
}

DEPARTMENTS_PROP = {
    "type": "string",
    "description": (
        "Comma-separated departments (e.g. 'sales' or 'engineering,product'). "
        "Matches LinkedIn's job function AND the title, so it covers job-board "
        "rows and free-text hiring posts alike. Use this for 'hiring a BDR / "
        "sales / engineers' questions. "
        f"Allowed values: {', '.join(DEPARTMENTS)}."
    ),
}

SENIORITIES_PROP = {
    "type": "string",
    "description": (
        "Comma-separated seniority levels (e.g. 'c_level,vp,head'). "
        f"Allowed values: {', '.join(SENIORITIES)}."
    ),
}

# ── Intent-level arguments (resolved by the Worker, never sent to the API) ──
ROLE_PROP = {
    "type": "string",
    "description": (
        "What the company is hiring for, in plain words: 'bdr', 'sales', "
        "'account executive', 'engineers', 'marketing', 'product manager', 'cto'. "
        "The Worker maps role families (sales, engineering, marketing, "
        "product, design, finance, people, data, support, legal) to `departments` "
        "so free-text hiring posts match, and exact titles to `positions`. "
        "Prefer this over positions/departments unless you need precise control."
    ),
}
HEADCOUNT_MIN_PROP = {
    "type": "integer",
    "minimum": 0,
    "description": "Minimum company headcount (whole company).",
}
HEADCOUNT_MAX_PROP = {
    "type": "integer",
    "minimum": 1,
    "description": (
        "Maximum company headcount (whole company). 'under 10 people' = 9. "
        "Mapped to team_size / employee_count filters by the Worker."
    ),
}
GROUP_BY_COMPANY_PROP = {
    "type": "boolean",
    "default": False,
    "description": (
        "Hiring only. Add `companies[]` (one entry per company, postings merged by "
        "title with their locations and links) next to the rows. Use for "
        "'which companies are hiring X' questions."
    ),
}
BY_COUNTRY_PROP = {
    "type": "boolean",
    "default": False,
    "description": (
        "Opt in to `byCountry` totals on a free count over several countries "
        "(one extra free probe per country, max 6). Default false makes only one API call."
    ),
}
COUNTRY_SCOPE_PROP = {
    "type": "string",
    "enum": ["hq", "job", "either"],
    "description": (
        "How `countries` is applied on hiring: 'hq' = company headquarters "
        "(use for 'companies in Belgium'), 'job' = where the job is located, "
        "'either' (default) = HQ or job location."
    ),
}

SORT_ORDER_PROP = {
    "type": "string",
    "description": "Sort direction",
    "enum": ["asc", "desc"],
}

AMOUNT_MIN_PROP = {
    "type": "integer",
    "description": "Minimum round amount in whole USD (e.g. 1000000 = $1M)",
    "minimum": 0,
}
AMOUNT_MAX_PROP = {
    "type": "integer",
    "description": "Maximum round amount in whole USD",
    "minimum": 0,
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
            "Costs 1 credit per executed search (even with 0 rows); count=true is free."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "headcount_min": HEADCOUNT_MIN_PROP,
                "headcount_max": HEADCOUNT_MAX_PROP,
                "page": PAGE_PROP,
                "limit": _limit_prop(50),
                "search": {
                    "type": "string",
                    "description": "Free-text search by company name or industry keywords",
                },
                "countries": COUNTRIES_PROP,
                "exclude_countries": EXCLUDE_COUNTRIES_PROP,
                "categories": CATEGORIES_PIPE_PROP,
                "subcategories": SUBCATEGORIES_PROP,
                "round": {
                    "type": "string",
                    "description": (
                        "Comma-separated funding round types (e.g. 'Seed,Series A'). "
                        f"Allowed values: {', '.join(FUNDING_ROUND_TYPES)}."
                    ),
                },
                "amount_min": AMOUNT_MIN_PROP,
                "amount_max": AMOUNT_MAX_PROP,
                "employee_count_min": EMPLOYEE_MIN_PROP,
                "employee_count_max": EMPLOYEE_MAX_PROP,
                "founded_year_min": FOUNDED_MIN_PROP,
                "founded_year_max": FOUNDED_MAX_PROP,
                "company_domain": COMPANY_DOMAIN_LIST_PROP,
                "company_linkedin_url": COMPANY_LINKEDIN_LIST_PROP,
                "dateFrom": DATE_FROM_PROP,
                "dateTo": DATE_TO_PROP,
                "date_preset": DATE_PRESET_PROP,
                "sort_by": {
                    "type": "string",
                    "description": "Sort field (default occurred_at)",
                    "enum": ["occurred_at", "discovered_at", "amount", "employee_count", "founded_year"],
                },
                "sort_order": SORT_ORDER_PROP,
                "count": COUNT_PROP,
                "verbose": VERBOSE_PROP,
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
            "Costs 1 credit per executed search (even with 0 rows); count=true is free."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "headcount_min": HEADCOUNT_MIN_PROP,
                "headcount_max": HEADCOUNT_MAX_PROP,
                "page": PAGE_PROP,
                "limit": _limit_prop(50),
                "search": {
                    "type": "string",
                    "description": "Free-text search by company name or industry keywords",
                },
                "countries": COUNTRIES_PROP,
                "exclude_countries": EXCLUDE_COUNTRIES_PROP,
                "categories": CATEGORIES_PIPE_PROP,
                "subcategories": SUBCATEGORIES_PROP,
                "amount_min": AMOUNT_MIN_PROP,
                "amount_max": AMOUNT_MAX_PROP,
                "employee_count_min": EMPLOYEE_MIN_PROP,
                "employee_count_max": EMPLOYEE_MAX_PROP,
                "founded_year_min": FOUNDED_MIN_PROP,
                "founded_year_max": FOUNDED_MAX_PROP,
                "company_domain": COMPANY_DOMAIN_LIST_PROP,
                "company_linkedin_url": COMPANY_LINKEDIN_LIST_PROP,
                "dateFrom": DATE_FROM_PROP,
                "dateTo": DATE_TO_PROP,
                "date_preset": DATE_PRESET_PROP,
                "sort_by": {
                    "type": "string",
                    "description": "Sort field (default occurred_at)",
                    "enum": ["occurred_at", "discovered_at", "amount", "employee_count"],
                },
                "sort_order": SORT_ORDER_PROP,
                "count": COUNT_PROP,
                "verbose": VERBOSE_PROP,
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
            "LinkedIn URLs. Costs 1 credit per executed search (even with 0 rows); "
            "count=true is free."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "role": ROLE_PROP,
                "page": PAGE_PROP,
                "limit": _limit_prop(50),
                "search": {
                    "type": "string",
                    "description": "Free-text search by company or person keywords",
                },
                "countries": {
                    "type": "string",
                    "description": (
                        "Comma-separated countries matched against the person's country OR "
                        "the company HQ. Accepts ISO codes, English names, or region shortcuts "
                        f"{', '.join(COUNTRY_REGIONS)}. Unknown values return HTTP 400 only with filter_version=2."
                    ),
                },
                "exclude_countries": EXCLUDE_COUNTRIES_PROP,
                "city": {
                    "type": "string",
                    "description": "Free-text city match",
                },
                "company_name": {
                    "type": "string",
                    "description": "Company name match",
                },
                "company_domain": COMPANY_DOMAIN_LIST_PROP,
                "company_linkedin_url": COMPANY_LINKEDIN_LIST_PROP,
                "companyLinkedinUrl": {
                    "type": "string",
                    "description": "Deprecated alias of company_linkedin_url (single exact URL).",
                },
                "person_linkedin_url": {
                    "type": "string",
                    "description": "Exact LinkedIn profile URL of the person",
                },
                "new_role": {
                    "type": "string",
                    "description": "Free-text match on the new role title (e.g. 'Chief Technology Officer')",
                },
                "positions": POSITIONS_PROP,
                "departments": DEPARTMENTS_PROP,
                "seniorities": SENIORITIES_PROP,
                "dateFrom": DATE_FROM_PROP,
                "dateTo": DATE_TO_PROP,
                "date_preset": DATE_PRESET_PROP,
                "sort_by": {
                    "type": "string",
                    "description": "Sort field",
                    "enum": ["occurred_at", "discovered_at", "person_name", "company_name"],
                },
                "sort_order": SORT_ORDER_PROP,
                "count": COUNT_PROP,
                "verbose": VERBOSE_PROP,
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
            "with title, location, jobUrl, validThrough, company details, applicant counts, "
            "and seniority info. Historical postings are included; include_expired=false selects open roles. "
            "Costs 1 credit per executed search (even with 0 rows); count=true is free. "
            "Coverage is ~84% US job locations: for non-US targets filter by company HQ "
            "(company_countries) or by a company_domain list, not by job location alone."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "role": ROLE_PROP,
                "headcount_min": HEADCOUNT_MIN_PROP,
                "headcount_max": HEADCOUNT_MAX_PROP,
                "country_scope": COUNTRY_SCOPE_PROP,
                "group_by_company": GROUP_BY_COMPANY_PROP,
                "by_country": BY_COUNTRY_PROP,
                "page": PAGE_PROP,
                "limit": _limit_prop(100),
                "search": {
                    "type": "string",
                    "description": "Free-text search across company name, industry, job title, location, and city",
                },
                "countries": {
                    "type": "string",
                    "description": (
                        "Comma-separated countries matched against the JOB LOCATION OR the "
                        "COMPANY HQ (either matches). Accepts ISO codes, English names, or "
                        f"region shortcuts {', '.join(COUNTRY_REGIONS)} automatically. With filter_version=2, unknown values return "
                        "HTTP 400. Use job_countries / company_countries to pin one side."
                    ),
                },
                "job_countries": {
                    "type": "string",
                    "description": (
                        "Comma-separated countries matched against the job location only "
                        "(same values as `countries`)."
                    ),
                },
                "company_countries": {
                    "type": "string",
                    "description": (
                        "Comma-separated countries matched against the company HQ only "
                        "(same values as `countries`). Recommended for European targets, "
                        "since most job locations in the index are US."
                    ),
                },
                "exclude_countries": EXCLUDE_COUNTRIES_PROP,
                "states": {
                    "type": "string",
                    "description": "Comma-separated US state codes (e.g. 'CA,NY,TX')",
                },
                "city": {
                    "type": "string",
                    "description": "Free-text city/location search",
                },
                "company_name": {
                    "type": "string",
                    "description": "Company name match",
                },
                "company_domain": COMPANY_DOMAIN_LIST_PROP,
                "company_linkedin_url": COMPANY_LINKEDIN_LIST_PROP,
                "categories": CATEGORIES_PIPE_PROP,
                "subcategories": SUBCATEGORIES_PROP,
                "positions": POSITIONS_PROP,
                "departments": DEPARTMENTS_PROP,
                "seniorities": SENIORITIES_PROP,
                "team_size": {
                    "type": "string",
                    "description": (
                        "Comma-separated COMPANY headcount ranges (whole company). Any "
                        "numeric 'min-max' works ('1-9' = under 10, '1-10', '11-50', "
                        "'51-200') plus '1000-plus'. Combine with company_countries for "
                        "'small companies headquartered in X'. "
                        f"Common values: {', '.join(TEAM_SIZE_RANGES)}."
                    ),
                },
                "applicants": {
                    "type": "string",
                    "description": (
                        "Comma-separated applicant count ranges. "
                        f"Allowed values: {', '.join(APPLICANT_RANGES)}."
                    ),
                },
                "include_expired": {
                    "type": "boolean",
                    "description": "Omitted or true preserves all historical postings. Explicit false filters to open postings (unexpired validThrough, or posted within 60 days when no expiry is known). Applies even with date ranges/presets.",
                },
                "dateFrom": DATE_FROM_PROP,
                "dateTo": DATE_TO_PROP,
                "date_preset": DATE_PRESET_PROP,
                "sort_by": {
                    "type": "string",
                    "description": "Sort field",
                    "enum": ["date_posted", "created_at", "title", "company_name", "location"],
                },
                "sort_order": SORT_ORDER_PROP,
                "count": COUNT_PROP,
                "verbose": VERBOSE_PROP,
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
            "details, and contact info. Costs 1 credit per executed search (even with 0 rows); "
            "count=true is free."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "page": PAGE_PROP,
                "limit": _limit_prop(50),
                "search": {
                    "type": "string",
                    "description": "Free-text search by investor name or description",
                },
                "countries": COUNTRIES_PROP,
                "exclude_countries": EXCLUDE_COUNTRIES_PROP,
                "categories": {
                    "type": "string",
                    "description": (
                        "Comma-separated investor types (e.g. 'vc,angel,pe'). "
                        f"Allowed values: {', '.join(INVESTOR_TYPES)}."
                    ),
                },
                "type": {
                    "type": "string",
                    "description": (
                        "Single investor type filter (alternative to `categories`). "
                        f"Allowed values: {', '.join(INVESTOR_TYPES)}."
                    ),
                },
                "headquarters": {
                    "type": "string",
                    "description": "Free-text headquarters (city/region) match, e.g. 'London'",
                },
                "ticket_size_min": {
                    "type": "integer",
                    "description": "Minimum typical check size in whole USD",
                    "minimum": 0,
                },
                "ticket_size_max": {
                    "type": "integer",
                    "description": "Maximum typical check size in whole USD",
                    "minimum": 0,
                },
                "count": COUNT_PROP,
                "verbose": VERBOSE_PROP,
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
            "Costs 1 credit per executed search (even with 0 rows); count=true is free."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "headcount_min": HEADCOUNT_MIN_PROP,
                "headcount_max": HEADCOUNT_MAX_PROP,
                "page": PAGE_PROP,
                "limit": _limit_prop(100),
                "search": {
                    "type": "string",
                    "description": "Free-text search across name, industry, description, keywords, specialties",
                },
                "countries": COUNTRIES_PROP,
                "exclude_countries": EXCLUDE_COUNTRIES_PROP,
                "categories": CATEGORIES_PIPE_PROP,
                "subcategories": SUBCATEGORIES_PROP,
                "industry": {
                    "type": "string",
                    "description": "Comma-separated LinkedIn industry names (exact match)",
                },
                "domain": {
                    "type": "string",
                    "description": "Company website domain (strict canonical match, e.g. 'stripe.com')",
                },
                "linkedin_url": {
                    "type": "string",
                    "description": "Company LinkedIn page URL (strict canonical match)",
                },
                "employee_count_min": EMPLOYEE_MIN_PROP,
                "employee_count_max": EMPLOYEE_MAX_PROP,
                "founded_year_min": FOUNDED_MIN_PROP,
                "founded_year_max": FOUNDED_MAX_PROP,
                "sort_by": {
                    "type": "string",
                    "description": "Sort field",
                    "enum": ["name", "employee_count", "founded_year", "created_at"],
                },
                "sort_order": SORT_ORDER_PROP,
                "count": COUNT_PROP,
                "verbose": VERBOSE_PROP,
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

INSTRUCTIONS = """Compatibility: existing calls retain full, unmodified payloads and historical results. Improved country, role and seniority matching is automatic. Unknown countries retain legacy literal matching unless filter_version=2 requests strict validation. Optional settings: verbose=false for trimmed responses; include_expired=false for open hiring postings; by_country=true for extra count probes; group_by_company=true for an additional company view.


# Signalbase MCP — Agent Instructions

## Overview
You have access to the Signalbase API through this MCP server. It provides real-time
business intelligence across six domains: funding rounds, acquisitions, job changes,
hiring (open roles), investors, and companies.

## Credits
- Every EXECUTED search costs **1 credit**, including searches that return 0 rows.
- `count=true` is free on ALL six tools (0 credits) and returns only the total count.
- Always size a query with `count=true` before paying for it; refine filters until the
  count is useful, then run the paid search once with the largest sensible `limit`.
- A `company_domain` / `company_linkedin_url` list of up to 50 entries is ONE search
  (one credit) — never loop one credit per company.

## Countries
- `countries` / `exclude_countries` accept ISO 3166-1 alpha-2 codes (`US,GB,DE`),
  English names (`Sweden`), or region shortcuts `EU`, `EUROPE`, `DACH`, `BENELUX`,
  `NORDICS`, `CEE`, `WE`, `NORTH_AMERICA`, `LATAM` (`NA` is Namibia). Values are comma-separated; unknown values
  return HTTP 400 only with `filter_version=2`. Omitted version improves known values and preserves literal matching for unrecognized values.
- Hiring: `countries` matches the JOB LOCATION **or** the COMPANY HQ. Use
  `job_countries` (location only) or `company_countries` (HQ only) to pin one side.
- Job changes: `countries` matches the person's country or the company HQ.

## Hiring coverage warning
- The hiring index is ~84% US job locations. For European or other non-US targets do
  NOT filter by job location alone: use `company_countries=<region>` (+ `team_size`),
  or the funded-pool workflow below (`company_domain` list).
- Historical postings are included by default. Pass `include_expired=false` explicitly for open roles; this applies even with dates or presets. Every row carries `jobUrl` and `validThrough`.

## Key Workflows

### 0. "Companies under N people hiring a <role> in <countries>"
`search_hiring_signals` with `role="<role as the user said it>"`, `headcount_max=N-1`,
`countries="<codes or regions>"`, `country_scope="hq"` (the user means where the company
is), `count=true`, `include_expired=false` first (free; add `by_country=true` for `byCountry` so you can say
which countries are empty), then the same without count plus `group_by_company=true`,
`limit=100`, `sort_by=date_posted`.
The Worker turns `role` into the right filter: role families (sales, engineers,
marketing…) match by department so free-text hiring posts are found; exact titles
(CTO, head of sales) match by title. Use `positions`/`departments` only for precise control.

### 1. Funded pool → who is hiring (recommended for "raised recently AND hiring X")
1. `search_funding_signals` with `countries`, `employee_count_max`, `date_preset`
   and `count=true` (free); then the same filters with `limit=50` (page if needed).
2. Collect each row's `companyWebsite` domain.
3. `search_hiring_signals` with `include_expired=false`, `company_domain=<up to 50 domains>`,
   `departments=<dept>`, `limit=100`, `sort_by=date_posted` — one credit per chunk of 50.
4. Independent lane: `search_hiring_signals` with `include_expired=false`, `company_countries=<region>`,
   `team_size=1-10`, `departments=<dept>` catches companies whose round was missed.
   (The `funded-and-hiring` prompt scripts this.)

### 2. Market Research
`search_funding_signals` filtered by subcategory/date, then `search_companies`
(`domain=` or `search=`) for deeper profiles.

### 3. Investor Lookup
`search_investors` by type/geography; cross-reference `search_funding_signals`.

### 4. Leadership Change Monitoring
`search_job_change_signals` with `seniorities=c_level` (word-boundary matched; a
"Director of Sales" is not c_level). New leaders often bring new vendor relationships.

### 5. Competitive Intelligence
`search_acquisition_signals` for M&A in a sector; profile parties with `search_companies`.

## Filter semantics
- `categories` = LinkedIn industry labels, pipe-separated: `Software Development|Financial Services`
- `subcategories` = Signalbase categories, comma-separated multi-select: `ai,fintech,saas`
- `team_size` (hiring) = whole-company size ranges `1-10,11-50,51-200,201-1000,1000-plus`
- `employee_count_min/max` (funding, acquisitions, companies) = exact headcount bounds
- `date_preset` overrides `dateFrom`/`dateTo`; absolute dates are YYYY-MM-DD
- Amounts are whole USD integers (5000000 = $5M)

## Presenting hiring results
For "which companies are hiring X" pass `group_by_company=true` on hiring: the
response then also carries `companies[]` (one entry per company, `openRoles`,
`postings[]` with the same title in several cities merged into one posting). The flat
rows stay in `data`; `pagination` counts postings, `companiesTotal` counts companies
on this page. `role="bdr"` (or
sdr) means the BDR/SDR role under its spellings and excludes Director/Manager/Head/VP
titles and generic sales titles; use `role="sales"` for any sales role.

## Response size
- With verbose=false responses are trimmed: long text fields are cut to 300 chars, logo/image
  URLs are dropped, `sources` is capped to 3 entries (with `sourcesTotal`), JSON-encoded
  list fields such as `companyCategories` are de-duplicated while remaining strings, and
  `_meta.trimmed=true` is added when something was cut. Links (`jobUrl`, `sources`,
  LinkedIn URLs, `companyWebsite`) and `validThrough` are always kept.
- Pass `verbose=true` to get the full payload. `verbose` is handled by this server and
  never sent to the API.

## Pagination
- Default page size is 20; max is 50 (funding, acquisitions, job changes, investors)
  or 100 (hiring, companies). Check `pagination.hasNextPage` before fetching more —
  every page is a paid search.
"""

# ──────────────────────────────────────────────────────────────
# MCP Prompts
# ──────────────────────────────────────────────────────────────

PROMPTS = [
    {
        "name": "funded-and-hiring",
        "description": (
            "Companies in a geography, under a headcount cap, that raised funding in a "
            "window AND have live job postings in a department — with posting links. "
            "Uses the credit-efficient funding → hiring-by-domain workflow."
        ),
        "arguments": [
            {
                "name": "geography",
                "description": "Country codes, names, or region (default 'EU'; e.g. 'NORDICS', 'DE,AT,CH', 'US')",
                "required": False,
            },
            {
                "name": "max_employees",
                "description": "Maximum company headcount (default 10)",
                "required": False,
            },
            {
                "name": "department",
                "description": "Hiring department to look for (default 'sales'; e.g. 'engineering', 'marketing')",
                "required": False,
            },
            {
                "name": "window",
                "description": "Funding date preset (default 'last_90d'; e.g. 'last_30d', 'last_6m')",
                "required": False,
            },
        ],
    },
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


def _team_size_for_max(max_employees) -> str:
    """Map a headcount cap onto the hiring `team_size` ranges (comma-joined)."""
    try:
        cap = int(str(max_employees).strip())
    except (TypeError, ValueError):
        return "1-10"
    lower_bounds = [1, 11, 51, 201, 1000]
    chosen = [r for r, low in zip(TEAM_SIZE_RANGES, lower_bounds) if low <= cap]
    return ",".join(chosen) if chosen else "1-10"


def _funded_and_hiring_prompt(args: dict) -> dict:
    geo = str(args.get("geography") or "EU").strip()
    max_emp = str(args.get("max_employees") or "10").strip()
    dept = str(args.get("department") or "sales").strip()
    window = str(args.get("window") or "last_90d").strip()
    team_size = _team_size_for_max(max_emp)
    text = (
        f"Find companies in **{geo}** with at most **{max_emp}** employees that raised "
        f"funding in the window `{window}` and are currently hiring in **{dept}**, "
        "with live posting links.\n\n"
        "Credit rules: every executed search costs 1 credit even with 0 rows; "
        "count=true is free on every tool. The hiring index is ~84% US job locations, "
        "so never filter non-US targets by job location alone.\n\n"
        "Steps:\n"
        f"1. Size the funded pool for free: search_funding_signals with countries={geo}, "
        f"employee_count_max={max_emp}, date_preset={window}, count=true. "
        f"Then pull it: search_funding_signals with countries={geo}, "
        f"employee_count_max={max_emp}, date_preset={window}, limit=50 "
        "(page through while pagination.hasNextPage is true).\n"
        "2. From each funding row collect the companyWebsite domain (strip protocol, "
        "www and paths), keeping companyName, roundType, fundingAmount and announcedDate "
        "for the output.\n"
        "3. Check the pool for open roles, one credit per chunk of 50 domains: "
        f"search_hiring_signals with include_expired=false, company_domain=<up to 50 domains, comma-separated>, "
        f"departments={dept}, limit=100, sort_by=date_posted, sort_order=desc. "
        "Explicit include_expired=false selects open postings.\n"
        "4. Independent lane to catch companies whose round we missed: "
        f"search_hiring_signals with include_expired=false, company_countries={geo}, team_size={team_size}, "
        f"departments={dept}, limit=100, sort_by=date_posted, sort_order=desc. "
        "Merge with step 3 and dedupe by domain.\n"
        "5. Output a table with columns: company | domain | round (type, amount, date, "
        "or '-' for lane-4-only rows) | title | location | jobUrl | validThrough. "
        "Keep only rows with a jobUrl, and state how many credits were spent."
    )
    return {"messages": [{"role": "user", "content": {"type": "text", "text": text}}]}


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
PROMPT_TEMPLATES["funded-and-hiring"] = _funded_and_hiring_prompt

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
    Converts Python booleans to lowercase strings and joins lists with commas."""
    parts = []
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, bool):
            v = "true" if v else "false"
        elif isinstance(v, (list, tuple)):
            v = ",".join(str(x) for x in v)
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


def _is_truthy(v) -> bool:
    """Interpret a tool argument as a boolean (accepts 'true'/'false' strings)."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return bool(v)



# ── Intent resolution ────────────────────────────────────────────────────────
# Role families → API `departments`. Anything else becomes a `positions` title
# match. Deterministic, no model involved.

def _reorder_intent_first(tools):
    """Put role / headcount / countries / country_scope / count at the top of
    each tool's properties so an agent reading the schema meets the intent
    arguments before the raw API knobs."""
    first = ["role", "headcount_max", "headcount_min", "countries", "country_scope", "count"]
    for t in tools:
        props = t["inputSchema"]["properties"]
        props["filter_version"] = {
            "type": "integer", "enum": [1, 2],
            "description": "Omit for improved country, role and seniority matching with legacy input tolerance. 1 freezes the original matching; 2 uses strict countries (unknown values return 400). Does not enable trimming or hide expired postings.",
        }
        props["by_country"] = BY_COUNTRY_PROP
        if t["name"] == "search_job_change_signals":
            props["personLinkedinUrl"] = dict(props["person_linkedin_url"])
            props["personLinkedinUrl"]["description"] = "Original supported spelling of person_linkedin_url (exact LinkedIn profile URL)."
        ordered = {k: props[k] for k in first if k in props}
        ordered.update({k: v for k, v in props.items() if k not in ordered})
        t["inputSchema"]["properties"] = ordered
    return tools


_reorder_intent_first(TOOLS)


def _expose_api_filters(tools):
    """Advertise API filters on the search tools of BOTH profiles (additive:
    original arguments and payloads are unchanged). Without them a model on the
    classic endpoint could not filter funding by investor or express "job in
    Poland, HQ elsewhere" in one call."""
    extra = {
        "search_funding_signals": {
            "investor_name": {"type": "string", "description": "Substring match on names of investors in the round."},
            "investors": {"type": "string", "description": "Comma-separated exact investor names (OR), via the investor-to-round links."},
            "investor_type": {"type": "string", "enum": ["pe", "vc"], "description": "A PE / VC investor took part in the round (participation, not ownership)."},
            "date_basis": {"type": "string", "enum": ["announced", "occurred_at"], "description": "Date the window applies to; 'announced' uses the announcement date when recorded."},
        },
        "search_hiring_signals": {
            "role_logic": {"type": "string", "enum": ["and", "or"], "description": "Combine explicit/inferred position and department filters with AND or OR."},
            "job_locations": {"type": "array", "items": {"type": "string"}, "description": "OR of job countries/regions and job metros (Dubai, Berlin, San Francisco, San Francisco Bay Area). Also matches posts stored without a country code by their location text."},
            "exclude_company_countries": {"type": "string", "description": "Exclude company HQ countries only (e.g. jobs in Poland at non-Polish companies: job_locations=[\"Poland\"], exclude_company_countries=PL)."},
            "exclude_staffing_agencies": {"type": "boolean", "description": "Drop companies whose industry is staffing/recruiting."},
            "posted_min_days_ago": {"type": "integer", "minimum": 0, "maximum": 3650, "description": "Original posting at least this many days old (e.g. 31 = open for over a month)."},
            "min_distinct_titles": {"type": "integer", "minimum": 2, "maximum": 100, "description": "Company has at least this many distinct job titles in the filtered set (multiple roles)."},
            "max_company_postings": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Company has at most this many postings in the filtered set. This is not proof of a first hire or office opening."},
            "work_mode": {"type": "string", "enum": ["remote"], "description": "Remote work arrangement stated in title/location; occupational uses do not qualify and description text is checked for negative statements."},
            "open_as_of": {"type": "string", "description": "ISO timestamp anchoring open/freshness evaluation. This does not recreate the historical state of the index."},
            "sector": {"type": "string", "enum": sorted(SECTOR_INDUSTRIES), "description": "Industry preset (fmcg / cpg / consumer goods, food and beverage, beauty / cosmetics / personal care) mapped to stored industry labels."},
            "funding_rounds": {"type": "string", "description": "Only companies with a matching round, e.g. 'Seed,Pre-Seed'. Joined before counting."},
            "funding_date_from": {"type": "string", "description": "Matching round announced on/after this ISO date."},
            "funding_date_to": {"type": "string", "description": "Matching round's stored event dates are on/before this ISO date."},
            "funding_investors": {"type": "string", "description": "Comma-separated exact participant names on a matching round."},
            "funding_investor_type": {"type": "string", "enum": ["pe", "vc"], "description": "Matching round had a PE / VC participant."},
            "workflow_evidence": {"type": "boolean", "description": "Include company growth/update fields used by HR workflows."},
            "count_companies": {"type": "boolean", "description": "With count=true, count distinct companies rather than postings."},
        },
        "search_job_change_signals": {
            "categories": CATEGORIES_PIPE_PROP,
            "subcategories": SUBCATEGORIES_PROP,
            "sector": {"type": "string", "enum": sorted(SECTOR_INDUSTRIES), "description": "Industry preset (e.g. fmcg) mapped to stored company industry labels. FMCG has no subcategory."},
        },
    }
    for tool in tools:
        for name, prop in extra.get(tool["name"], {}).items():
            tool["inputSchema"]["properties"].setdefault(name, prop)
    return tools

ROLE_FAMILIES = {
    "sales": [
        "sales", "business development", "biz dev", "bizdev", "revenue",
        "account manager", "gtm", "go-to-market", "commercial",
    ],
    "engineering": [
        "engineer", "engineers", "engineering", "developer", "developers",
        "software", "backend", "frontend", "full stack", "fullstack", "devops",
        "sre", "swe",
    ],
    "marketing": ["marketing", "marketer", "demand gen", "demand generation", "brand", "content"],
    "product": ["product manager", "product management", "pm", "product owner", "product"],
    "design": ["design", "designer", "ux", "ui"],
    "finance": ["finance", "financial", "accounting", "accountant", "controller", "cfo office"],
    "people": ["hr", "people", "talent", "recruiter", "recruiting", "human resources"],
    "data": ["data", "analytics", "analyst", "data scientist", "machine learning", "ml"],
    "customer_success": ["customer success", "support", "customer support", "csm"],
    "legal": ["legal", "compliance", "counsel"],
    "operations": ["operations", "ops", "operations manager"],
    "growth": ["growth"],
}

# Titles that are precise enough to stay title matches (ordered: longest first).
ROLE_TITLES = [
    # "bdr"/"sdr" → the API's BDR/SDR key: the role under its spellings (BDR,
    # SDR, business/sales development rep or associate), leadership excluded.
    # Account executive is its own title match.
    "bdr", "sdr", "business development representative", "sales development representative",
    "account executive", "ae",
    "founding account executive", "head of business development", "head of sales",
    "vp of sales", "vp sales", "head of growth", "head of marketing", "head of product",
    "head of engineering", "engineering manager", "product manager", "sales manager",
    "marketing manager", "cto", "ceo", "cfo", "coo", "cmo", "cro", "founder", "co-founder",
]


def _resolve_role(role: str) -> dict:
    """'bdr' → {'departments': 'sales'}; 'head of sales' → {'positions': 'head of sales'}."""
    text = (role or "").strip().lower()
    if not text:
        return {}
    parts = [p.strip() for p in re.split(r"[,/]| or | and ", text) if p.strip()]
    departments, positions = [], []
    for part in parts:
        if part in ("gtm engineer", "gtm engineers", "go-to-market engineer", "go to market engineer"):
            positions.extend(["gtm engineer", "go-to-market engineer", "go to market engineer"])
            continue
        if part in ("gtm", "go-to-market", "go to market"):
            departments.extend(["sales", "marketing", "customer_success", "growth"])
            continue
        if part in ROLE_TITLES:
            positions.append(
                "bdr" if part in ("sdr", "sales development representative", "business development representative")
                else "account executive" if part == "ae"
                else part
            )
            continue
        matched = None
        for dept, words in ROLE_FAMILIES.items():
            # Only exact family aliases widen to a whole department. A specific
            # title such as "director of sales", "senior software engineer" or
            # "data engineer" must retain its specialty and seniority.
            if part in words:
                matched = dept
                break
        if matched:
            departments.append(matched)
        else:
            positions.append(part)
    out = {}
    if departments:
        out["departments"] = ",".join(dict.fromkeys(departments))
    if positions:
        out["positions"] = ",".join(dict.fromkeys(positions))
    if departments and positions:
        # "bdr or engineers": title match OR department match. The API ANDs the
        # two by default; role_logic=or keeps full department semantics.
        out["role_logic"] = "or"
    return out


def _resolve_intent_args(tool_name: str, args: dict) -> dict:
    """Translate intent-level arguments into the REST parameters the API accepts.
    Explicit API parameters given alongside always win."""
    args = dict(args)
    role = args.pop("role", None)
    hmin = args.pop("headcount_min", None)
    hmax = args.pop("headcount_max", None)
    scope = args.pop("country_scope", None)

    if role:
        for k, v in _resolve_role(str(role)).items():
            if not args.get(k):
                args[k] = v
            elif k == "role_logic":
                # Scalar operators are not list filters. An explicit "or" must
                # remain "or", never "or,or" (which the API reads as AND).
                continue
            else:
                args[k] = f"{args[k]},{v}"

    if hmin is not None or hmax is not None:
        if tool_name in ("search_hiring_signals",):
            if not args.get("team_size"):
                lo = int(hmin) if hmin is not None else 1
                args["team_size"] = f"{max(lo, 1)}-{int(hmax)}" if hmax is not None else f"{max(lo, 1)}-1000000"
        elif tool_name in ("search_funding_signals", "search_acquisition_signals", "search_companies"):
            if hmin is not None and not args.get("employee_count_min"):
                args["employee_count_min"] = int(hmin)
            if hmax is not None and not args.get("employee_count_max"):
                args["employee_count_max"] = int(hmax)

    if scope and tool_name == "search_hiring_signals" and args.get("countries"):
        value = args.pop("countries")
        key = {"hq": "company_countries", "job": "job_countries"}.get(str(scope).lower(), "countries")
        if not args.get(key):
            args[key] = value
        else:
            args[key] = f"{args[key]},{value}"
    return args


COUNTRY_KEYS = ("countries", "company_countries", "job_countries")
BREAKDOWN_MAX_TOKENS = 6  # combined call + up to 6 free probes per count
BREAKDOWN_TIMEOUT_SECONDS = 5


def _country_breakdown_plan(params: dict):
    """For a free count over several country tokens, return (key, tokens) so the
    Worker can report a per-country breakdown; None when not applicable."""
    # Match the REST API's count=true contract exactly. Other truthy strings
    # (e.g. "yes") are not free API counts and must never trigger extra calls.
    if params.get("count") is not True and params.get("count") != "true":
        return None
    present = [k for k in COUNTRY_KEYS if params.get(k)]
    if len(present) != 1:
        return None
    key = present[0]
    tokens = [t.strip() for t in str(params[key]).split(",") if t.strip()]
    if len(tokens) < 2 or len(tokens) > BREAKDOWN_MAX_TOKENS:
        return None
    return key, tokens


async def _with_country_breakdown(endpoint: str, params: dict, api_key: str, response):
    """Attach `byCountry` to a multi-country count response (all calls are free)."""
    plan = _country_breakdown_plan(params)
    if not plan or not isinstance(response, dict) or response.get("error"):
        return response
    key, tokens = plan
    per = {}
    for token in tokens:
        sub = dict(params)
        sub[key] = token
        total = None
        try:
            r = await asyncio.wait_for(_call_api(endpoint, sub, api_key), timeout=BREAKDOWN_TIMEOUT_SECONDS)
            if isinstance(r, dict) and not r.get("error"):
                total = (r.get("pagination") or {}).get("totalCount")
        except Exception:
            # A failed per-country probe must never spoil the successful
            # combined count; report it as unknown instead.
            total = None
        per[token.upper()] = total
    response["byCountry"] = per
    empty = [c for c, n in per.items() if n == 0]
    unknown = [c for c, n in per.items() if n is None]
    if unknown:
        response["byCountryNote"] = f"Per-country probe failed for {', '.join(unknown)}; the combined total is unaffected."
    if empty:
        response["hint"] = (
            f"No rows for {', '.join(empty)} with these filters. "
            "That usually means we hold few postings for those countries, not that the filter failed."
        )
    return response


def _prepare_tool_args(tool_args, tool_name: str = "", profile: str = "classic") -> tuple:
    """Pre-process tools/call arguments before forwarding to the API.

    - pops the Worker-only `verbose` flag (the API returns 400 on unknown params)
    - joins list-valued arguments with "," (the API takes comma-separated strings)
    - resolves intent-level args (role, headcount_min/max, country_scope)
    Returns (params_for_api, verbose, worker_options).
    """
    args = dict(tool_args or {})
    hr = profile == "hr"
    if hr:
        args.setdefault("filter_version", 2)
        if tool_name == "search_funding_signals":
            args.setdefault("date_basis", "announced")
        # Historical HR analysis remains available without a second flag.
        preset = args.get("date_preset")
        historical = (preset in ("yesterday", "last_week", "last_month", "last_quarter", "last_year")) if preset else bool(args.get("dateTo"))
        if tool_name == "search_hiring_signals" and not historical:
            args.setdefault("include_expired", False)
    verbose = _is_truthy(args.pop("verbose", not hr))
    group_by_company = _is_truthy(args.pop("group_by_company", hr and tool_name == "search_hiring_signals"))
    by_country = _is_truthy(args.pop("by_country", hr))
    sector = args.pop("sector", None)
    if sector and tool_name in ("search_hiring_signals", "search_job_change_signals"):
        # Raises WorkflowError for an unknown preset (returned as a tool error).
        sector_labels = _wf_sector_categories(sector)
        args["categories"] = f"{args['categories']}|{sector_labels}" if args.get("categories") else sector_labels
    if tool_name == "search_hiring_signals" and args.get("job_locations") is not None:
        # The API takes job_locations as a JSON array, not a comma list.
        places = args["job_locations"]
        if isinstance(places, str) and not places.strip().startswith("["):
            places = [p.strip() for p in places.split(",") if p.strip()]
        args["job_locations"] = places if isinstance(places, str) else json.dumps(list(places))
    for k, v in list(args.items()):
        if isinstance(v, (list, tuple)):
            args[k] = ",".join(str(x) for x in v)
    args = _resolve_intent_args(tool_name, args)
    return args, verbose, {"group_by_company": group_by_company, "by_country": by_country}


def _decode_json_list(text: str):
    """'["A","A","B"]' → ["A","B"]; anything else → None."""
    t = text.strip()
    if not (t.startswith("[") and t.endswith("]")):
        return None
    try:
        parsed = json.loads(t)
    except Exception:
        return None
    if not isinstance(parsed, list):
        return None
    seen, out = set(), []
    for item in parsed:
        key = json.dumps(item, sort_keys=True) if not isinstance(item, str) else item
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _trim_value(value, changed: list | None = None):
    """Recursively truncate long text fields, drop logo/image fields, cap
    evidence lists and decode JSON-encoded list strings.
    `changed` (a one-element list) is set to [True] when anything was altered."""
    def mark():
        if changed is not None:
            changed[:] = [True]

    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in TRIM_HTML_FIELDS and isinstance(v, str):
                decoded = html.unescape(v)
                if decoded != v:
                    v = decoded
                    mark()
            if k in TRIM_DROP_FIELDS:
                mark()
                continue
            if k in TRIM_TEXT_FIELDS and isinstance(v, str) and len(v) > TRIM_MAX_CHARS:
                out[k] = v[:TRIM_MAX_CHARS] + "…"
                mark()
            elif k in TRIM_LIST_FIELDS or k in TRIM_NESTED_DROP:
                items = v if isinstance(v, list) else None
                if items is None:
                    out[k] = _trim_value(v, changed)
                    continue
                cap = TRIM_LIST_FIELDS.get(k)
                if cap is not None and len(items) > cap:
                    out[f"{k}Total"] = len(items)
                    items = items[:cap]
                    mark()
                drop = TRIM_NESTED_DROP.get(k, set())
                cleaned = []
                for item in items:
                    if isinstance(item, dict) and any(dk in item for dk in drop):
                        item = {ik: iv for ik, iv in item.items() if ik not in drop}
                        mark()
                    cleaned.append(_trim_value(item, changed))
                out[k] = cleaned
            elif k in TRIM_JSON_STRING_FIELDS and isinstance(v, str):
                # Type-stable: the API returns these as JSON text; a consumer
                # parsing the string must keep working. Only de-duplicate.
                decoded = _decode_json_list(v)
                if decoded is None:
                    out[k] = v
                else:
                    redone = json.dumps(decoded, ensure_ascii=False, separators=(",", ":"))
                    if redone != v.strip():
                        mark()
                    out[k] = redone
            else:
                out[k] = _trim_value(v, changed)
        return out
    if isinstance(value, list):
        return [_trim_value(v, changed) for v in value]
    return value



def _group_hiring_by_company(rows):
    """Collapse posting rows into one entry per company. Postings with the same
    title at the same company are merged and their locations listed, so a
    company advertising one role in three cities is one hire, not three."""
    companies = {}
    for r in rows:
        key = (r.get("companyLinkedin") or r.get("companyWebsite") or r.get("companyName") or "").lower()
        if not key:
            continue
        c = companies.setdefault(key, {
            "company": r.get("companyName"),
            "hq": r.get("companyCountry"),
            "headcount": r.get("companyEmployeeCount"),
            "website": r.get("companyWebsite"),
            "linkedin": r.get("companyLinkedin"),
            "postings": [],
        })
        title = (r.get("title") or "").strip()
        loc = r.get("location") or r.get("city") or r.get("jobCountry")
        existing = next((p for p in c["postings"] if p["title"].lower() == title.lower()), None)
        if existing:
            if loc and loc not in existing["locations"]:
                existing["locations"].append(loc)
            if r.get("jobUrl") and r["jobUrl"] not in existing["links"]:
                existing["links"].append(r["jobUrl"])
            continue
        c["postings"].append({
            "title": title,
            "locations": [loc] if loc else [],
            "posted": (r.get("datePosted") or "")[:10] or None,
            "validThrough": (r.get("validThrough") or "")[:10] or None,
            "links": [r["jobUrl"]] if r.get("jobUrl") else [],
        })
    out = list(companies.values())
    for c in out:
        c["openRoles"] = len(c["postings"])
    return out


def _with_company_groups(data):
    if not isinstance(data, dict):
        return data
    rows = data.get("data")
    if (data.get("meta") or {}).get("endpoint") != "signals.hiring" or not isinstance(rows, list) or not rows:
        return data
    grouped = dict(data)
    grouped["companies"] = _group_hiring_by_company(rows)
    grouped["companiesTotal"] = len(grouped["companies"])
    grouped["note"] = "Grouped from this page's rows; companies may occur on multiple pages. Pagination counts postings."
    return grouped


def _trim_response(data, group_by_company: bool = False):
    """Opt-in compact response; the default tool response never calls this."""
    changed = [False]
    trimmed = _trim_value(data, changed)
    if isinstance(trimmed, dict) and changed[0]:
        trimmed["_meta"] = dict(TRIM_META)
    return _with_company_groups(trimmed) if group_by_company else trimmed


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


def _success_result(data, verbose: bool = True, group_by_company: bool = False) -> dict:
    """Return an MCP tool success result with JSON-serialized data.
    Default: full payload, indented. Explicit verbose=false: trimmed, compact JSON."""
    import json
    if verbose:
        if group_by_company:
            data = _with_company_groups(data)
        text = json.dumps(data, indent=2, default=str)
    else:
        text = json.dumps(_trim_response(data, group_by_company), indent=None, separators=(",", ":"),
                          default=str, ensure_ascii=False)
    return {
        "content": [{"type": "text", "text": text}],
    }


def _format_api_error(api_response: dict) -> str:
    status = api_response.get("status", "unknown")
    body = api_response.get("body", {})
    if isinstance(body, dict):
        msg = body.get("error", body.get("message", str(body)))
        hint = body.get("hint") or body.get("details")
        if hint and str(hint) not in str(msg):
            msg = f"{msg} ({hint})"
    else:
        msg = str(body)
    return f"API error (HTTP {status}): {msg}"


# ──────────────────────────────────────────────────────────────
# API proxy
# ──────────────────────────────────────────────────────────────

async def _call_api(endpoint: str, params: dict, api_key: str) -> dict:
    """Make an authenticated GET request to the Signalbase API."""
    import json as json_mod

    qs = _build_query_string(params)
    url = f"{_api_base_override or API_BASE}{endpoint}"
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


class WorkflowError(Exception):
    pass


def _validate_value(name, value, schema, *, allow_string_lists=False):
    """Small JSON-Schema subset used by every tools/call before I/O.

    The Worker intentionally accepts list/tuple shorthand for REST string lists
    because that is long-standing client behaviour; item types and enums are
    still checked before the value is joined.
    """
    kind = schema.get("type")
    string_list = allow_string_lists and kind == "string" and isinstance(value, (list, tuple))
    array_string = allow_string_lists and kind == "array" and isinstance(value, str)
    valid = (
        (kind == "boolean" and isinstance(value, bool))
        or (kind == "integer" and isinstance(value, int) and not isinstance(value, bool))
        or (kind == "string" and (isinstance(value, str) or string_list))
        or (kind == "array" and (isinstance(value, (list, tuple)) or array_string))
        or kind is None
    )
    if not valid:
        raise WorkflowError(f"Invalid {name}; expected {kind}")
    values = ([part.strip() for part in value.split(",")] if array_string else list(value)) if kind == "array" or string_list else [value]
    item_schema = schema.get("items", {}) if kind == "array" else {}
    for item in values:
        if (kind == "array" or string_list) and not isinstance(item, str):
            raise WorkflowError(f"Invalid {name}; every item must be a string")
        if item_schema.get("type") == "string" and not isinstance(item, str):
            raise WorkflowError(f"Invalid {name}; every item must be a string")
        item_enum = item_schema.get("enum")
        if item_enum is not None and item not in item_enum:
            raise WorkflowError(f"Invalid {name} item {item!r}; expected one of {item_enum}")
        if isinstance(item, str) and (kind == "array" or string_list) and (not item.strip() or len(item) > 300):
            raise WorkflowError(f"{name} values must be nonempty strings of at most 300 characters")
    if "enum" in schema:
        for item in values:
            if item not in schema["enum"]:
                raise WorkflowError(f"Invalid {name}; expected one of {schema['enum']}")
    if kind == "integer":
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            raise WorkflowError(f"{name} is outside its supported range")
    if kind == "array" and len(values) > schema.get("maxItems", 50):
        raise WorkflowError(f"{name} accepts at most {schema.get('maxItems', 50)} items")


def _validate_tool_arguments(descriptor, args, *, allow_unknown=False, allow_string_lists=False):
    if not isinstance(args, dict):
        raise WorkflowError("Tool arguments must be an object.")
    schema = descriptor.get("inputSchema", {})
    props = schema.get("properties", {})
    missing = [name for name in schema.get("required", []) if name not in args]
    if missing:
        raise WorkflowError("Missing required arguments: " + ", ".join(missing))
    unknown = sorted(set(args) - set(props))
    if unknown and not allow_unknown:
        raise WorkflowError("Unknown arguments: " + ", ".join(unknown))
    for name, value in args.items():
        if name in props:
            _validate_value(name, value, props[name], allow_string_lists=allow_string_lists)


def _wf_int(args, name, default, minimum=0, maximum=3650):
    value = args.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise WorkflowError(f"{name} must be an integer between {minimum} and {maximum}.")
    return value


def _wf_strings(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    if isinstance(value, list) and all(isinstance(s, str) and s.strip() for s in value):
        return [s.strip() for s in value]
    raise WorkflowError("List arguments must contain nonempty strings.")


def _wf_date(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _wf_now(args):
    # A fixed as_of date makes paired evals reproducible without modifying data.
    if args.get("as_of"):
        parsed = _wf_date(args["as_of"])
        if not parsed:
            raise WorkflowError("as_of must be an ISO date or timestamp.")
        return parsed
    return datetime.now(timezone.utc)


def _wf_day(value):
    return value.date().isoformat()


def _wf_domain(row):
    value = row.get("companyWebsite") or row.get("website")
    if not value:
        return None
    try:
        host = urlsplit(value if "://" in value else "https://" + value).hostname
        return host.lower().removeprefix("www.").rstrip(".") if host and "." in host else None
    except (ValueError, TypeError):
        return None


async def _wf_fetch(endpoint, params, api_key, ledger):
    if ledger["api_calls"] >= ledger["max_api_calls"]:
        raise WorkflowError("Workflow API-call budget reached; use the continuation page or a larger max_api_calls.")
    remaining = ledger.get("_deadline", time.monotonic() + 45) - time.monotonic()
    if remaining <= 0:
        raise WorkflowError("Workflow time budget reached; resume using the continuation fields.")
    ledger["api_calls"] += 1
    try:
        result = await asyncio.wait_for(_call_api(endpoint, params, api_key), timeout=min(40, remaining))
    except Exception as error:
        raise WorkflowError(f"Upstream request failed ({type(error).__name__}); no result inferred.") from error
    if isinstance(result, dict):
        usage_meta = result.get("meta") or ((result.get("body") or {}).get("meta") if isinstance(result.get("body"), dict) else {}) or {}
        ledger["credits_used"] += usage_meta.get("creditsUsed", 0)
    if not isinstance(result, dict) or result.get("error"):
        raise WorkflowError(_format_api_error(result) if isinstance(result, dict) else "Unexpected API response")
    if not isinstance(result.get("pagination"), dict) or not isinstance(result.get("data"), list):
        raise WorkflowError("Unexpected API envelope; data and pagination are required.")
    return result


UNOBSERVED_REQUIREMENTS = {
    "founder_led_sales": "No structured evidence of the founder currently doing sales.",
    "founder_origin": "Founder nationality/origin is not indexed; never infer it from names.",
    "office_presence": "A job location does not establish that the company has an office there.",
    "first_hire": "A founding title does not establish a first company or first regional hire.",
    "expansion_budget": "A foreign job posting or funding round does not establish an expansion budget.",
    "company_scaling": "Current vacancies do not distinguish growth from replacement hiring.",
    "pe_ownership": "PE round participation can be observed; current ownership/control is not established.",
    "continuous_vacancy": "Posting age and validThrough do not prove a job was continuously unfilled.",
    "verified_live_vacancy": "Open means indexed freshness, not a live check of the employer's application page.",
    "role_specific_future_hire": "The supplied benchmark measures any first visible hire, not a specific future role.",
    "current_funding_stage": "A historical round does not establish the company's current funding stage.",
    "startup_status": "There is no universal startup flag; size, founding date and funding are evidence to review, not a guaranteed classification.",
}


# Sector presets -> the company industry labels actually stored (live labels,
# 2026-09-11). FMCG has no subcategory; an FMCG CFO sits on "Personal Care
# Product Manufacturing" or "Food and Beverage Manufacturing".
FMCG_INDUSTRIES = [
    "Food and Beverage Manufacturing", "Food & Beverages", "Food & Beverage", "Food and Beverage",
    "Personal Care Product Manufacturing", "Consumer Goods", "Beverage Manufacturing", "Beverages",
    "Food Production", "Dairy Product Manufacturing", "Dairy", "Cosmetics", "Beauty",
    "Wine & Spirits", "Wineries", "Breweries", "Tobacco Manufacturing", "Tobacco",
    "Wholesale Food and Beverage", "Wholesale Alcoholic Beverages", "Seafood Product Manufacturing",
    "Sugar and Confectionery Product Manufacturing", "Trading in consumer goods",
    "Retail Health and Personal Care Products", "Retail Groceries", "Grocery Retail", "Food and Beverage Retail",
]
SECTOR_INDUSTRIES = {
    "fmcg": FMCG_INDUSTRIES, "cpg": FMCG_INDUSTRIES, "consumer goods": FMCG_INDUSTRIES,
    "consumer packaged goods": FMCG_INDUSTRIES, "fast moving consumer goods": FMCG_INDUSTRIES,
    "food and beverage": [i for i in FMCG_INDUSTRIES if "food" in i.lower() or "beverage" in i.lower() or "dairy" in i.lower()],
    "beauty": ["Personal Care Product Manufacturing", "Cosmetics", "Beauty", "Retail Health and Personal Care Products"],
}
SECTOR_INDUSTRIES["cosmetics"] = SECTOR_INDUSTRIES["beauty"]
SECTOR_INDUSTRIES["personal care"] = SECTOR_INDUSTRIES["beauty"]


def _wf_sector_categories(sector):
    """'fmcg' -> pipe-separated industry labels for the API `categories` filter."""
    labels = SECTOR_INDUSTRIES.get(str(sector or "").strip().lower())
    if not labels:
        raise WorkflowError(f"Unknown sector '{sector}'. Known sectors: {', '.join(sorted(SECTOR_INDUSTRIES))}. For other sectors use subcategories (e.g. legal, cybersecurity, ai).")
    return "|".join(labels)


# A narrow title and the broader function to probe when it finds nothing in a place.
TITLE_FAMILY = {"bdr": "sales", "sdr": "sales", "business development representative": "sales",
                "sales development representative": "sales", "account executive": "sales", "ae": "sales",
                "founding account executive": "sales", "gtm engineer": "gtm", "founding engineer": "engineers",
                "cfo": "finance", "head of sales": "sales", "head of growth": "growth", "head of marketing": "marketing"}


def _wf_broader_role(role):
    text = str(role or "").strip().lower()
    if not text or _resolve_role(text).get("positions") is None:
        return None  # already a family (departments) or nothing to widen
    return TITLE_FAMILY.get(text)


async def _wf_place_breakdown(args, params, key, ledger):
    """Free per-place counts for the requested role and, for a narrow title, its
    broader function, so '0 BDR in Dubai' is reported next to '5 sales/BD
    postings in Dubai' instead of silently looking like an empty market."""
    places = _wf_strings(args.get("job_locations"))
    if not places or len(places) > 6:
        return None, []
    broader = _wf_broader_role(args.get("role"))
    role_keys = ("positions", "departments", "role_logic")
    base = {k: v for k, v in params.items() if k not in ("job_locations",)}
    broader_params = {k: v for k, v in base.items() if k not in role_keys}
    if broader:
        broader_params.update(_resolve_role(broader))
    jobs = []
    for place in places:
        jobs.append(("role", place, {**base, "job_locations": json.dumps([place]), "count": True}))
        if broader:
            jobs.append(("broader", place, {**broader_params, "job_locations": json.dumps([place]), "count": True}))
    jobs = jobs[: max(0, ledger["max_api_calls"] - ledger["api_calls"])]
    results = await asyncio.gather(*(_wf_fetch("/signals/hiring", p, key, ledger) for _, _, p in jobs), return_exceptions=True)
    by_place, hints = {}, []
    for (kind, place, _), result in zip(jobs, results):
        total = None if isinstance(result, BaseException) else result["pagination"]["totalCount"]
        entry = by_place.setdefault(place, {})
        entry["postings" if kind == "role" else f"broader_{broader}_postings"] = total
    for place, entry in by_place.items():
        wide = entry.get(f"broader_{broader}_postings") if broader else None
        if entry.get("postings") == 0 and wide:
            hints.append(f"No {args.get('role')}-titled postings in {place}, but {wide} {broader} postings: small companies there often use other titles for this role (e.g. 'Business Development Executive'). To list them call find_hiring_companies with role='{broader}' and job_locations=['{place}'] and present them as the same function under a different title.")
    return by_place, hints


def _wf_requirements(args):
    requested = _wf_strings(args.get("required_evidence"))
    unknown = [key for key in requested if key not in UNOBSERVED_REQUIREMENTS]
    if unknown:
        raise WorkflowError("Unknown required_evidence: " + ", ".join(unknown))
    return [{"requirement": key, "status": "unknown", "reason": UNOBSERVED_REQUIREMENTS[key]} for key in requested]


def _wf_hiring_params(args, funded=False):
    now = _wf_now(args)
    params = {"filter_version": 2, "include_expired": False, "sort_by": "date_posted", "sort_order": "desc", "workflow_evidence": True}
    if args.get("as_of"):
        params["open_as_of"] = now.isoformat()
    places = _wf_strings(args.get("job_locations"))
    if places:
        params["job_locations"] = json.dumps(places)
    for field in ("company_countries", "exclude_company_countries", "subcategories", "company_domain"):
        if args.get(field):
            params[field] = ",".join(_wf_strings(args[field]))
    if args.get("role"):
        params.update(_resolve_role(args["role"]))
    if args.get("min_distinct_role_titles") is not None:
        params["min_distinct_titles"] = _wf_int(args, "min_distinct_role_titles", 2, 2, 100)
    if args.get("max_postings_per_company") is not None:
        params["max_company_postings"] = _wf_int(args, "max_postings_per_company", 3, 1, 100)
    if args.get("sector"):
        params["categories"] = _wf_sector_categories(args["sector"])
    if args.get("headcount_min") is not None or args.get("headcount_max") is not None:
        low = _wf_int(args, "headcount_min", 1, 1, 10000000)
        high = _wf_int(args, "headcount_max", 10000000, 1, 10000000)
        if low > high:
            raise WorkflowError("headcount_min cannot exceed headcount_max")
        params["team_size"] = f"{low}-{high}"
    params["exclude_staffing_agencies"] = args.get("exclude_staffing_agencies", True)
    if args.get("posted_within_days") is not None:
        params["dateFrom"] = _wf_day(now - timedelta(days=_wf_int(args, "posted_within_days", 30)))
    if args.get("posting_age_days_min") is not None:
        days = _wf_int(args, "posting_age_days_min", 30)
        # Use a fixed explicit UTC bound for evals. The API's age predicate
        # additionally excludes postings whose original date is unknown.
        params["posted_min_days_ago"] = days
        params["dateTo"] = _wf_day(now - timedelta(days=days))
    for field, target in (("posted_from", "dateFrom"), ("posted_to", "dateTo")):
        if args.get(field):
            value = _wf_date(args[field])
            if not value:
                raise WorkflowError(f"{field} must be an ISO date")
            params[target] = _wf_day(value)
    if params.get("dateFrom") and params.get("dateTo") and params["dateFrom"] > params["dateTo"]:
        raise WorkflowError("Posting date range is inverted")
    if args.get("work_mode"):
        if args["work_mode"] != "remote":
            raise WorkflowError("work_mode currently supports remote only (advertised in job title/location).")
        params["work_mode"] = "remote"
    if args.get("description_keywords"):
        params["description"] = args["description_keywords"]
    if funded or args.get("funding_within_days") is not None or args.get("funding_rounds") or args.get("funding_investor_type") or args.get("funding_investors"):
        params["funding_date_from"] = _wf_day(now - timedelta(days=_wf_int(args, "funding_within_days", 90)))
        params["funding_date_to"] = now.isoformat()
        if args.get("funding_rounds"):
            params["funding_rounds"] = ",".join(_wf_strings(args["funding_rounds"]))
        if args.get("funding_investors"):
            params["funding_investors"] = ",".join(_wf_strings(args["funding_investors"]))
        if args.get("funding_investor_type"):
            params["funding_investor_type"] = args["funding_investor_type"]
    return params


def _wf_company_results(rows, args):
    companies = {}
    for row in rows:
        domain = _wf_domain(row)
        key = row.get("companyId") or domain or row.get("companyLinkedin")
        if not key:
            continue
        company = companies.setdefault(str(key), {
            "company": row.get("companyName"), "domain": domain,
            "hq_country": row.get("companyCountry"), "headcount": row.get("companyEmployeeCount"),
            "headcount_evidence": {"value": row.get("companyEmployeeCount"), "precision": "stored_or_estimated", "verified_exact": False},
            "industry": row.get("companyIndustry"), "subcategory": row.get("companySubcategory"), "founded_year": row.get("companyFoundedYear"),
            "description_excerpt": (row.get("companyDescription") or "")[:400], "growth_info": row.get("companyGrowthInfo"), "company_record_updated_at": row.get("companyUpdatedAt"),
            "postings": [], "funding": [], "funding_evidence_review": [], "criteria": [],
            "qualification": "partial" if _wf_requirements(args) else "matches_indexed_filters",
            "unverified_requirements": _wf_requirements(args),
            "data_quality": "Headcount is stored and may be estimated from a range; company/job associations were not repaired or externally verified.",
        })
        if not any(p["id"] == row.get("id") for p in company["postings"]):
            description = row.get("descriptionText") or ""
            terms = re.findall(r"\w+", args.get("description_keywords") or "")
            first = min((description.lower().find(term.lower()) for term in terms if term.lower() in description.lower()), default=0)
            excerpt = description[max(0, first - 100):first + 400] if terms else None
            company["postings"].append({"id": row.get("id"), "title": html.unescape(row.get("title") or ""), "location": row.get("location"), "job_country": row.get("jobCountry"), "posted": row.get("datePosted"), "valid_through": row.get("validThrough"), "url": row.get("jobUrl"), "open_status": "indexed_open", "indexed_open_as_of": args.get("as_of") or "request_time", "source_verified_open": None, **({"description_excerpt": excerpt} if excerpt else {})})
        for funding in row.get("matchedFunding") or []:
            if not any(f.get("signalId") == funding.get("signalId") for f in company["funding"]):
                company["funding"].append(funding)
                sources = funding.get("sources") or []
                source_evidence = [s if isinstance(s, dict) else {"url": s} for s in sources]
                company["funding_evidence_review"].append({
                    "signal_id": funding.get("signalId"),
                    "stored_verification_status": funding.get("verificationStatus"),
                    "date_qualification": funding.get("dateQualification"),
                    "source_identity_status": "not_verified_by_index",
                    "evidence_status": funding.get("evidenceStatus") or "requires_source_review",
                    "sources": source_evidence,
                    "uncertainty": "The indexed company-to-round association and current funding stage require source verification.",
                })
    for company in companies.values():
        for name in ("role", "headcount_min", "headcount_max", "company_countries", "job_locations", "posting_age_days_min", "min_distinct_role_titles", "posted_within_days", "posted_from", "posted_to", "work_mode", "description_keywords"):
            if args.get(name) is not None:
                company["criteria"].append({"requirement": name, "status": "matched_indexed_filter", "requested": args[name]})
        if company["funding"]:
            company["criteria"].append({"requirement": "funding", "status": "indexed_round_needs_source_review", "evidence_signal_ids": [f.get("signalId") for f in company["funding"]]})
            company["qualification"] = "partial_pending_funding_source_verification"
        company["posting_count_in_batch"] = len(company["postings"])
    return list(companies.values())


HQ_CITY_REASON = "Company HQ city/metro is not indexed. job_locations filters jobs and cannot substitute for HQ."
# Job metros the API can filter (mirrors JOB_METROS in the app) and their country.
JOB_METRO_COUNTRIES = {"san francisco bay area": "US", "bay area": "US", "sf bay area": "US", "san francisco": "US", "dubai": "AE", "berlin": "DE"}
WORKFLOW_ONLY_ARGS = ("company_hq_city", "as_of", "max_api_calls", "page", "count", "candidate_offset", "horizon_days", "quiet_lookback_days", "max_companies")


def _wf_hq_city_alternatives(args, tool):
    """Labelled substitutes for an unsupported HQ-city request. Nothing is run:
    the caller decides whether a proxy answers the user's question."""
    city = str(args.get("company_hq_city") or "").strip()
    country = JOB_METRO_COUNTRIES.get(city.lower())
    base = {k: v for k, v in args.items() if k not in WORKFLOW_ONLY_ARGS}
    alternatives = []
    if country:
        funded = any(base.get(k) for k in ("funding_rounds", "funding_investor_type", "funding_investors", "funding_within_days"))
        proxy = {k: v for k, v in base.items() if k in WF_HIRING_PROPS}
        proxy["job_locations"] = [city]
        if funded and proxy.get("funding_rounds") and "funding_within_days" not in proxy:
            # A round label ("seed-stage") is a stage question, not a 90-day recency one.
            proxy["funding_within_days"] = 365
        alternatives.append({
            "tool": "find_funded_hiring_companies" if funded else "find_hiring_companies",
            "arguments": proxy,
            "answers": f"Companies with indexed open roles located in {city}. Job location is not HQ evidence, and these companies are already hiring rather than about to hire.",
        })
    if tool == "find_hiring_outlook":
        outlook = {k: v for k, v in args.items() if k != "company_hq_city"}
        if country:
            outlook["company_countries"] = [country]
        alternatives.append({
            "tool": "find_hiring_outlook",
            "arguments": outlook,
            "answers": "Previously quiet companies with recent triggers" + (f" headquartered in {country}" if country else "") + "; HQ city is unverified for every candidate.",
        })
    return alternatives


def _wf_hq_city_unsupported(args, tool, key="companies"):
    return {
        "status": "unsupported", key: [],
        "unverified_requirements": _wf_requirements(args) + [{"requirement": "company_hq_city", "status": "unknown", "requested": args["company_hq_city"], "reason": HQ_CITY_REASON}],
        "alternatives": _wf_hq_city_alternatives(args, tool),
        "next_step": "Tell the user HQ city is unavailable. If a labelled alternative still helps, run it and present its results with that label; never call them HQ-verified.",
        "coverage": {"complete": False, "rows_scanned": 0},
    }


async def _wf_hiring(args, key, ledger, funded=False):
    requirements = _wf_requirements(args)
    if args.get("company_hq_city"):
        return _wf_hq_city_unsupported(args, "find_funded_hiring_companies" if funded else "find_hiring_companies")
    params = _wf_hiring_params(args, funded)
    if args.get("count") is True:
        # Two independent free counts; running them together halves the wait on
        # broad cohorts (a metro regex count can take ~30 s).
        postings, companies = await asyncio.gather(
            _wf_fetch("/signals/hiring", {**params, "count": True}, key, ledger),
            _wf_fetch("/signals/hiring", {**params, "count": True, "count_companies": True}, key, ledger),
            return_exceptions=True,
        )
        if isinstance(postings, BaseException):
            raise postings
        if isinstance(companies, BaseException):
            if not isinstance(companies, WorkflowError):
                raise companies
            return {"status": "partial", "interpreted_query": params, "totals": {"postings": postings["pagination"]["totalCount"], "companies": None}, "errors": [str(companies)], "coverage": {"complete_for_indexed_filters": False, "count_only": True}}
        totals = {"postings": postings["pagination"]["totalCount"], "companies": companies["pagination"]["totalCount"]}
        result = {"status": "partial" if requirements else "complete", "interpreted_query": params, "totals": totals, "unverified_requirements": requirements, "coverage": {"complete_for_indexed_filters": True, "count_only": True}}
        by_place, hints = await _wf_place_breakdown(args, params, key, ledger)
        if by_place:
            result["by_place"] = by_place
        if hints:
            result["hints"] = hints
        if totals["postings"]:
            tool = "find_funded_hiring_companies" if funded else "find_hiring_companies"
            result["next_step"] = f"Count only: no company is named yet. If the user asked for companies, call {tool} again with the same arguments and count omitted; it returns company groups with posting URLs (1 credit per page)."
        return result
    page = _wf_int(args, "page", 1, 1, 100000)
    start_page = page
    # One 50-row page by default: one credit and a payload a model can read;
    # continuation is explicit via next_page.
    pages = _wf_int(args, "max_pages", 1, 1, 5)
    size = _wf_int(args, "page_size", 50, 1, 100)
    rows, seen = [], set()
    has_more, total, errors = False, None, []
    for _ in range(pages):
        try:
            response = await _wf_fetch("/signals/hiring", {**params, "page": page, "limit": size}, key, ledger)
        except WorkflowError as error:
            if not rows:
                raise
            errors.append(str(error))
            has_more = True
            break
        for row in response.get("data") or []:
            identity = row.get("id") or row.get("jobUrl")
            if identity not in seen:
                seen.add(identity)
                rows.append(row)
        pagination = response.get("pagination") or {}
        total = pagination.get("totalCount")
        has_more = bool(pagination.get("hasNextPage"))
        page += 1
        if not has_more or ledger["api_calls"] >= ledger["max_api_calls"]:
            break
    return {"status": "partial" if funded or requirements or has_more or start_page != 1 else "complete", "interpreted_query": params, "companies": _wf_company_results(rows, args), "unverified_requirements": requirements, "errors": errors,
            "coverage": {"matching_postings": total, "rows_scanned": len(rows), "start_page": start_page, "complete_for_indexed_filters": not has_more and start_page == 1, "query_exhausted": not has_more, "complete_flag_scope": "this response, not pages accumulated by the caller", "next_page": page if has_more else None, "company_groups_span_pages": True, "funding_evidence_limit_per_posting": 5, "staffing_exclusion": "known staffing/recruitment industry labels only; unknown company types remain"}}


BENCHMARK_FLOORS = {"new_vp": {30: .20, 60: .30, 90: .36}, "new_head": {30: .15, 60: .23, 90: .28}, "new_c_level": {30: .07, 60: .11, 90: .13}, "series_a": {30: .05, 60: .08, 90: .10}, "seed": {30: .03, 60: .04, 90: .05}}


def _wf_trigger(row, kind, now, horizon):
    if kind == "funding":
        signal = {"seed": "seed", "series a": "series_a"}.get(str(row.get("roundType", "")).lower())
        announced = _wf_date(row.get("announcedDate"))
        occurred = _wf_date(row.get("occurredAt"))
        stored_dates = [date for date in (announced, occurred) if date]
        # Every stored event date must support recency. This rejects records
        # whose edited announcement date conflicts with an old occurredAt.
        if stored_dates and any(not 0 <= (now - date).days < horizon for date in stored_dates):
            return None
        date = announced or occurred
    else:
        title = str(row.get("newRole", "")).lower()
        signal = "new_vp" if re.search(r"\b(vp|svp|evp|vice[ -]?president)\b", title) else "new_head" if "head of" in title else "new_c_level" if re.search(r"\b(ceo|cto|cfo|coo|cmo|cpo|cro|cio|chro|ciso)\b|chief.*officer", title) else None
        if re.search(r"advisory|assistant|fractional|interim|consultant", title):
            return None
        date = _wf_date(row.get("startDate") or row.get("occurredAt"))
    if not signal or not date or not 0 <= (now - date).days < horizon:
        return None
    domain = _wf_domain(row)
    if not domain:
        return None
    source_rows = [s if isinstance(s, dict) else {"url": s} for s in (row.get("sources") or [])[:3]]
    if not source_rows and row.get("takenFrom"):
        source_rows = [{"url": row["takenFrom"]}]
    return {"company": row.get("companyName"), "domain": domain, "hq_country": row.get("companyCountry"), "headcount": row.get("companyEmployeeCount"), "headcount_evidence": {"value": row.get("companyEmployeeCount"), "precision": "stored_or_estimated", "verified_exact": False}, "signal": signal, "signal_date": _wf_day(date), "role": row.get("newRole"), "sources": [s.get("url") for s in source_rows if s.get("url")], "source_evidence": _trim_value(source_rows), "record_id": row.get("signalId"), "stored_dates": {"startDate": row.get("startDate"), "announcedDate": row.get("announcedDate"), "occurredAt": row.get("occurredAt")}, **({"funding": {"round": row.get("roundType"), "amount": row.get("amount"), "currency": row.get("currency"), "investors": _trim_value(row.get("investors") or []), "verification_status": row.get("verificationStatus"), "source_identity_status": "not_verified_by_index"}} if kind == "funding" else {})}


async def _wf_outlook(args, key, ledger):
    now = _wf_now(args)
    horizon = _wf_int(args, "horizon_days", 90, 30, 90)
    if horizon not in (30, 60, 90):
        raise WorkflowError("horizon_days must be 30, 60 or 90")
    if args.get("company_hq_city"):
        return _wf_hq_city_unsupported(args, "find_hiring_outlook", "candidates")
    if args.get("job_locations"):
        return {"status": "unsupported", "candidates": [], "unverified_requirements": [{"requirement": "future_job_location", "status": "unknown", "reason": "No job exists yet to filter its location. Supply company_countries to find potential company-level hiring."}]}
    quiet_days = _wf_int(args, "quiet_lookback_days", 90, 1, 365)
    common = {"filter_version": 2, "dateFrom": _wf_day(now - timedelta(days=horizon)), "dateTo": _wf_day(now), "limit": 50, "page": _wf_int(args, "page", 1, 1, 100000), "sort_by": "occurred_at", "sort_order": "desc"}
    countries = ",".join(_wf_strings(args.get("company_countries")))
    if countries:
        common["countries"] = countries
    funding_params = {**common, "date_basis": "announced", "round": ",".join(_wf_strings(args.get("funding_rounds")) or ["Seed", "Series A"])}
    for source, target in (("headcount_min", "employee_count_min"), ("headcount_max", "employee_count_max")):
        if args.get(source) is not None:
            funding_params[target] = _wf_int(args, source, 1, 1, 10000000)
    if args.get("funding_investor_type"):
        funding_params["investor_type"] = args["funding_investor_type"]
    funding = await _wf_fetch("/signals/funding", funding_params, key, ledger)
    sources = [("funding", funding)]
    if not args.get("funding_rounds"):
        changes = await _wf_fetch("/signals/job-changes", {**common, "seniorities": "vp,head,c_level"}, key, ledger)
        sources.append(("job_change", changes))
    candidates = {}
    for kind, response in sources:
        for row in response.get("data") or []:
            trigger = _wf_trigger(row, kind, now, horizon)
            if not trigger:
                continue
            n = trigger["headcount"]
            if args.get("headcount_min") is not None and (n is None or n < args["headcount_min"]):
                continue
            if args.get("headcount_max") is not None and (n is None or n > args["headcount_max"]):
                continue
            if countries and kind == "job_change":
                # The job-change countries filter is person-country OR company-HQ.
                # Verify HQ through company search rather than treating person location as HQ.
                trigger["hq_requires_check"] = True
            candidates.setdefault(trigger["domain"], []).append(trigger)
    ranked = sorted(candidates.values(), key=lambda ts: max(BENCHMARK_FLOORS[t["signal"]][horizon] for t in ts), reverse=True)
    offset = _wf_int(args, "candidate_offset", 0, 0, 10000)
    qualified, already_hiring, checked, errors = [], [], 0, []
    limit = _wf_int(args, "max_companies", 3, 1, 10)
    for triggers in ranked[offset:]:
        trigger = max(triggers, key=lambda t: BENCHMARK_FLOORS[t["signal"]][horizon])
        needs_backing_check = bool(args.get("funding_investor_type")) and trigger["signal"].startswith("new_")
        needed = 4 + int(bool(trigger.get("hq_requires_check"))) + int(needs_backing_check)
        if ledger["max_api_calls"] - ledger["api_calls"] < needed or len(qualified) >= limit:
            break
        try:
            if trigger.get("hq_requires_check"):
                hq = await _wf_fetch("/companies", {"filter_version": 2, "domain": trigger["domain"], "countries": countries, "count": True}, key, ledger)
                if hq["pagination"]["totalCount"] == 0:
                    checked += 1
                    continue
            if needs_backing_check:
                backing = await _wf_fetch("/signals/funding", {"filter_version": 2, "company_domain": trigger["domain"], "investor_type": args["funding_investor_type"], "count": True}, key, ledger)
                if backing["pagination"]["totalCount"] == 0:
                    checked += 1
                    continue
            signal_day = _wf_date(trigger["signal_date"])
            history_args = {"filter_version": 2, "company_domain": trigger["domain"], "dateFrom": _wf_day(signal_day - timedelta(days=quiet_days)), "dateTo": _wf_day(signal_day - timedelta(days=1)), "count": True}
            # Postings through today, expired ones included: a job posted after the
            # trigger (even one that has since closed) is already an observed outcome.
            postings = await _wf_fetch("/signals/hiring", {**history_args, "dateTo": _wf_day(now), "include_expired": True}, key, ledger)
            joins = await _wf_fetch("/signals/job-changes", history_args, key, ledger)
            current = await _wf_fetch("/signals/hiring", {"filter_version": 2, "company_domain": trigger["domain"], "include_expired": False, "open_as_of": now.isoformat(), "dateTo": _wf_day(now), "count": True}, key, ledger)
            outcome_args = {"filter_version": 2, "company_domain": trigger["domain"], "dateFrom": _wf_day(signal_day), "dateTo": _wf_day(now), "count": True}
            # Only the selected event is excluded. Another leadership join after
            # that event is an observed outcome, even if it was also a trigger candidate.
            trigger_ids = [trigger["record_id"]] if trigger.get("record_id") else []
            if trigger_ids:
                outcome_args["exclude_signal_ids"] = ",".join(trigger_ids)
            subsequent_joins = await _wf_fetch("/signals/job-changes", outcome_args, key, ledger)
        except WorkflowError as error:
            errors.append({"domain": trigger["domain"], "reason": str(error), "qualification": "unknown"})
            break
        checked += 1
        evidence = {"postings_from_lookback_start_to_today": postings["pagination"]["totalCount"], "pre_trigger_announced_joins": joins["pagination"]["totalCount"], "current_open_postings": current["pagination"]["totalCount"], "post_trigger_announced_joins_excluding_triggers": subsequent_joins["pagination"]["totalCount"]}
        if any(evidence.values()):
            already_hiring.append({"company": trigger["company"], "domain": trigger["domain"], "reason": "Does not satisfy the operational quiet-company definition", "evidence": evidence})
            continue
        requirements = _wf_requirements(args)
        if args.get("role"):
            requirements.append({"requirement": "role_specific_future_hire", "status": "unknown", "requested": args["role"], "reason": UNOBSERVED_REQUIREMENTS["role_specific_future_hire"]})
        qualified.append({**trigger, "status": "potential_company_level_hiring", "triggers": triggers, "benchmark": {"floor": BENCHMARK_FLOORS[trigger["signal"]][horizon], "horizon_days_from_trigger": horizon, "window_end": _wf_day(signal_day + timedelta(days=horizon)), "source": "user_supplied_screenshot", "cohort_definition_and_sample_size": "unknown", "individual_probability": False, "combined_signals": False}, "quiet_evidence": evidence, "unverified_requirements": requirements})
    return {"status": "partial", "candidates": qualified, "excluded_examples": already_hiring, "interpreted_query": args, "errors": errors,
            "coverage": {"candidate_domains_in_source_pages": len(ranked), "candidates_checked": checked, "source_pages_complete": all(not (r.get("pagination") or {}).get("hasNextPage") for _, r in sources), "complete": False, "source_page": common["page"], "next_candidate_offset": offset + checked if offset + checked < len(ranked) else None, "next_source_page": common["page"] + 1 if offset + checked >= len(ranked) and any((r.get("pagination") or {}).get("hasNextPage") for _, r in sources) else None, "quiet_definition": f"No indexed postings from {quiet_days} calendar days before the trigger day through the as_of day (expired included), no announced joins in those {quiet_days} days or after the trigger (the trigger itself excluded), and no postings considered open at as_of.", "as_of_semantics": "Anchors query windows and posting freshness only. It is not a historical index snapshot; later-indexed backdated records can change a replay.", "benchmark_applicability": "Operational quiet definition is not validated against the screenshot's unknown cohort. Use rates as supplied reference floors only."}}


async def _wf_investors(args, key, ledger):
    now = _wf_now(args)
    headquarters = str(args.get("investor_headquarters") or "").strip()
    if not headquarters:
        raise WorkflowError("investor_headquarters is required: the investor's city or region text, e.g. Toronto.")
    params = {"filter_version": 2, "headquarters": headquarters, "limit": 50, "page": _wf_int(args, "page", 1, 1, 100000)}
    investors = await _wf_fetch("/signals/investors", params, key, ledger)
    names = list(dict.fromkeys(r.get("name") for r in investors.get("data", []) if r.get("name")))
    if not names:
        return {"status": "complete", "investors_with_matching_rounds": [], "investors_without_matching_rounds": [], "rounds": [], "coverage": {"investors_checked": 0, "no_observed_matches": True}}
    ordinary_names = [name for name in names if "," not in name]
    if not ordinary_names:
        return {"status": "partial", "investors_with_matching_rounds": [], "investors_without_matching_rounds": [], "investors_not_checked": names, "rounds": [], "coverage": {"reason": "Investor names contain commas; exact-name list lookup cannot represent them without ambiguity."}}
    funding_args = {"filter_version": 2, "investors": ",".join(ordinary_names), "dateFrom": _wf_day(now - timedelta(days=_wf_int(args, "funding_within_days", 365))), "limit": 50, "sort_by": "amount", "sort_order": "desc"}
    amount_min = _wf_int(args, "round_amount_min", 10000000, 0, 1000000000000)
    if amount_min:
        # Amounts are stored in the round's own currency; a USD floor can only be
        # compared with USD rounds. Disclosed in coverage.amount_filter.
        funding_args["amount_min"] = amount_min
        funding_args["currency"] = "USD"
    countries = ",".join(_wf_strings(args.get("company_countries")))
    if countries:
        funding_args["countries"] = countries
    funding_args["date_basis"] = "announced"
    funding_args["dateTo"] = _wf_day(now)
    rounds, rejected_rounds, more, errors = [], [], True, []
    window_start = now - timedelta(days=_wf_int(args, "funding_within_days", 365))
    page = _wf_int(args, "funding_page", 1, 1, 100000)
    for _ in range(_wf_int(args, "max_pages", 2, 1, 5)):
        try:
            result = await _wf_fetch("/signals/funding", {**funding_args, "page": page}, key, ledger)
        except WorkflowError as error:
            errors.append(str(error))
            break
        for round_row in result.get("data") or []:
            stored_dates = [date for date in (
                _wf_date(round_row.get("announcedDate")),
                _wf_date(round_row.get("occurredAt")),
            ) if date]
            if len(stored_dates) > 1 and any(date < window_start or date > now for date in stored_dates):
                rejected_rounds.append({
                    "company": round_row.get("companyName"),
                    "company_domain": _wf_domain(round_row),
                    "round": round_row.get("roundType"),
                    "stored_dates": {"announcedDate": round_row.get("announcedDate"), "occurredAt": round_row.get("occurredAt")},
                    "reason": "Conflicting stored dates do not all support the requested funding window.",
                    "sources": [s if isinstance(s, dict) else {"url": s} for s in (round_row.get("sources") or [])[:3]],
                })
            else:
                rounds.append(round_row)
        more = bool((result.get("pagination") or {}).get("hasNextPage"))
        page += 1
        if not more or ledger["api_calls"] >= ledger["max_api_calls"]:
            break
    checked = [p for p in investors.get("data") or [] if p.get("name") in ordinary_names]
    matched, unmatched = _wf_investor_matches(checked, rounds)
    return {"status": "partial" if more or errors or investors.get("pagination", {}).get("hasNextPage") or len(ordinary_names) != len(names) else "complete",
            "investors_with_matching_rounds": matched,
            "investors_without_matching_rounds": unmatched,
            "investors_not_checked": [n for n in names if n not in ordinary_names],
            "summary": f"{len(matched)} of {len(ordinary_names)} checked investors headquartered in {params['headquarters']} appear in a date-consistent matching round; the rest had no supported match in the rounds returned."
            + (f" {len(rejected_rounds)} round(s) were rejected because their stored dates conflict with the requested window." if rejected_rounds else "")
            + (" More rounds exist on next_funding_page." if more else ""),
            "rounds": _trim_response({"data": rounds})["data"], "rejected_rounds": rejected_rounds, "interpreted_query": funding_args, "errors": errors,
            "coverage": {"investors_checked": len(ordinary_names), "investors_matching_headquarters": investors.get("pagination", {}).get("totalCount"), "investors_with_matching_rounds": len(matched),
                         "amount_filter": f"USD-denominated rounds of at least {amount_min:,} USD only; rounds in other currencies are not compared." if amount_min else "none", "next_investor_page": params["page"] + 1 if investors.get("pagination", {}).get("hasNextPage") else None, "next_funding_page": page if more else None, "evidence_meaning": "Indexed participation in a funding round; not evidence of current ownership. No matching rounds is a coverage result, not proof of no investments."}}


def _source_named_lead(round_row):
    for source in round_row.get("sources") or []:
        if isinstance(source, dict):
            url_text = unquote(str(source.get("url") or ""))
            candidates = [source.get("title"), urlsplit(url_text).path.replace("-", " ")]
        else:
            url_text = unquote(str(source or ""))
            candidates = [urlsplit(url_text).path.replace("-", " ")]
        for candidate in candidates:
            match = re.search(r"\bled by\s+(.+?)(?:\s+to\b|[,;:|/]|$)", str(candidate or ""), re.I)
            if match:
                return match.group(1).strip(" .-")
    return None


def _wf_investor_matches(profiles, rounds):
    """Split the HQ-matched investors into those that appear in a returned round
    (with those rounds) and those that do not, so a headquarters match is never
    read as round participation."""
    by_name = {}
    for r in rounds:
        for inv in r.get("investors") or []:
            name = (inv.get("name") if isinstance(inv, dict) else str(inv or "")).strip().lower()
            if name:
                by_name.setdefault(name, []).append((r, inv if isinstance(inv, dict) else {}))
    matched, unmatched = [], []
    for profile in profiles:
        name = profile.get("name") or ""
        hits = by_name.get(name.strip().lower(), [])
        if not hits:
            unmatched.append(name)
            continue
        matching_rounds = []
        for r, inv in hits:
            source_evidence = [s if isinstance(s, dict) else {"url": s} for s in (r.get("sources") or [])[:3]]
            source_named_lead = _source_named_lead(r)
            normalized_investor = re.sub(r"[^a-z0-9]", "", name.lower())
            normalized_source_lead = re.sub(r"[^a-z0-9]", "", (source_named_lead or "").lower())
            if source_named_lead and normalized_investor and normalized_investor in normalized_source_lead:
                lead_status = "supported_by_source_title"
                lead = True
            elif source_named_lead and inv.get("isLead"):
                lead_status = "contradicted_by_source_title"
                lead = None
            else:
                lead_status = "not_source_verified"
                lead = None
            matching_rounds.append({
                "company": r.get("companyName"), "company_domain": _wf_domain(r), "company_hq": r.get("companyCountry"),
                "round": r.get("roundType"), "amount": r.get("amount"), "currency": r.get("currency"),
                "announced": r.get("announcedDate"), "occurred_at": r.get("occurredAt"),
                "lead": lead, "stored_lead_flag": inv.get("isLead"), "lead_status": lead_status,
                "source_named_lead": source_named_lead, "sources": source_evidence,
                "funding_verification_status": r.get("verificationStatus"),
                "source_identity_status": "not_verified_by_index",
            })
        matched.append({
            "investor": name, "headquarters": profile.get("headquarters"), "type": profile.get("type"), "website": profile.get("website"),
            "matching_rounds": matching_rounds,
        })
    return matched, unmatched


def _wf_prop(kind, description, **extra):
    return {"type": kind, "description": description, **extra}


WF_COMMON_PROPS = {
    "company_countries": _wf_prop("array", "Company HQ countries/regions. Leave empty unless the user restricts where companies are headquartered; places the user lists for the job itself go in job_locations only.", items={"type": "string"}),
    "company_hq_city": _wf_prop("string", "Only if HQ city/metro is a hard requirement. Currently returns unsupported; never substitutes job location."),
    "role": _wf_prop("string", "Role or alternatives: bdr, engineers, bdr or engineers, GTM, GTM engineer, CFO."),
    "headcount_min": _wf_prop("integer", "Minimum company employees, inclusive.", minimum=1),
    "headcount_max": _wf_prop("integer", "Maximum company employees, inclusive. Under 10 means 9.", minimum=1),
    "required_evidence": _wf_prop("array", "Additional claims the user requires. Every unsupported claim is explicitly returned as unknown; never silently ignored.", items={"type": "string", "enum": list(UNOBSERVED_REQUIREMENTS)}),
    "as_of": _wf_prop("string", "Optional ISO reference for relative windows and indexed-open freshness. Not a historical index snapshot; later-indexed backdated rows can change a replay."),
    "max_api_calls": _wf_prop("integer", "Maximum upstream requests this workflow may use; result includes exact consumption. Data requests cost 1 credit each; counts are free.", minimum=2, maximum=30, default=12),
    "page": PAGE_PROP,
}

WF_HIRING_PROPS = {
    **WF_COMMON_PROPS,
    "job_locations": _wf_prop("array", "OR of job countries/regions and supported cities/metros. E.g. [Belgium, US, Netherlands, Luxembourg, Dubai]. Dubai restricts UAE jobs to Dubai; Bay Area means job metro, not HQ. Also supports Berlin and San Francisco. Do not copy these places into company_countries as well: that ANDs an HQ filter.", items={"type": "string"}),
    "exclude_company_countries": _wf_prop("array", "Exclude company HQ countries only; can combine Poland jobs with excluding Polish HQ.", items={"type": "string"}),
    "subcategories": _wf_prop("array", "Company sector labels such as legal, cybersecurity, ai.", items={"type": "string"}),
    "company_domain": _wf_prop("array", "Optional company-domain pool.", items={"type": "string"}),
    "exclude_staffing_agencies": _wf_prop("boolean", "Exclude known staffing/recruiting industry labels. Unknown classifications remain, clearly disclosed.", default=True),
    "work_mode": _wf_prop("string", "Remote work arrangement advertised in title/location. Occupational uses such as remote sensing do not qualify; description text is checked for negative statements. Does not imply worldwide eligibility.", enum=["remote"]),
    "description_keywords": _wf_prop("string", "Optional full-text job-description keywords. Returns a source excerpt around matches. Wording is evidence of an advertised claim, not independent confirmation."),
    "posted_within_days": _wf_prop("integer", "Posting recency, e.g. 30. Omit for all indexed open postings.", minimum=0, maximum=3650),
    "min_distinct_role_titles": _wf_prop("integer", "For multiple roles, set 2. Company must have this many distinct normalized titles in the SAME filtered cohort, before counts/paging. These are advertised titles, not verified seats.", minimum=2, maximum=100),
    "max_postings_per_company": _wf_prop("integer", "Keep companies with at most this many postings in the SAME filtered cohort. This is only a posting-count proxy; it does not establish a first hire, employee count or office opening.", minimum=1, maximum=100),
    "sector": _wf_prop("string", "Industry preset mapped to stored company industry labels: fmcg / cpg / consumer goods, food and beverage, beauty / cosmetics / personal care. Use subcategories for tech sectors (legal, cybersecurity, ai).", enum=sorted(SECTOR_INDUSTRIES)),
    "posted_from": _wf_prop("string", "Explicit ISO posting start date; overrides posted_within_days."),
    "posted_to": _wf_prop("string", "Explicit ISO posting end date; combines with minimum posting age. Open-only filtering still applies."),
    "posting_age_days_min": _wf_prop("integer", "At least this many days since original posting, e.g. 31 for over a month. Missing original dates excluded. Does not prove continuously unfilled.", minimum=0, maximum=3650),
    "funding_within_days": _wf_prop("integer", "Funding recency for joined funding criteria, default 90.", minimum=0, maximum=3650),
    "funding_rounds": _wf_prop("array", "Recorded round types such as Seed, Pre-Seed, Series A. A prior round does not establish the company's current stage.", items={"type": "string"}),
    "funding_investors": _wf_prop("array", "Exact investor names in an observed funding round.", items={"type": "string"}),
    "funding_investor_type": _wf_prop("string", "Recorded PE/VC participation, not current ownership/control.", enum=["pe", "vc"]),
    "count": _wf_prop("boolean", "Free count of the full indexed intersection: separate posting and unique-company totals. Uses two free API calls."),
    "page_size": _wf_prop("integer", "Source posting rows per page, default 50.", minimum=1, maximum=100),
    "max_pages": _wf_prop("integer", "Pages of the already joined result to fetch in this call, default 1 (one credit each). Returns next_page and completeness.", minimum=1, maximum=5),
}


def _wf_tool(name, description, properties, required=()):
    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = list(required)
    return {"name": name, "description": description, "inputSchema": schema, "annotations": {"readOnlyHint": True, "openWorldHint": True}}


HR_WORKFLOW_TOOLS = [
    _wf_tool("find_hiring_companies", "Find companies with indexed open roles using explicit HQ/job geography, employee size, posting age and optional funding criteria. Returns company groups, posting/source evidence, exact interpreted filters, unsupported requirements and honest pagination. Prefer over assembling generic searches.", WF_HIRING_PROPS),
    _wf_tool("find_funded_hiring_companies", "Find the actual intersection of funding and current hiring. The API joins BEFORE counts/pagination, so no manual domain batching or guessing the efficient search direction. Same evidence and coverage as find_hiring_companies. Funding defaults to last 90 days.", WF_HIRING_PROPS),
    _wf_tool("find_hiring_outlook", "Potential company-level first visible hiring after leadership/funding triggers. Automatically checks prior posting AND announced-join history plus current jobs. Returns supplied cohort floors, never individualized probabilities or promised specific roles. A bounded sample with explicit coverage, not an exhaustive forecast.", {**WF_COMMON_PROPS, "candidate_offset": _wf_prop("integer", "Resume unchecked candidates on the same source page using coverage.next_candidate_offset.", minimum=0), "horizon_days": _wf_prop("integer", "Days from trigger; expired forecast windows excluded.", enum=[30, 60, 90], default=90), "quiet_lookback_days": _wf_prop("integer", "Operational pre-trigger quiet window; screenshot cohort definition is unknown.", minimum=1, maximum=365, default=90), "max_companies": _wf_prop("integer", "Maximum qualifying candidates in a bounded call.", minimum=1, maximum=10, default=3), "funding_rounds": WF_HIRING_PROPS["funding_rounds"], "funding_investor_type": WF_HIRING_PROPS["funding_investor_type"]}),
    _wf_tool("research_investor_activity", "Find investors by headquarters and join their exact names to observed funding rounds. E.g. Toronto investors in US rounds >= $10M. Uses existing investor-to-round links; reports missing coverage and continuation pages.", {**{k: WF_COMMON_PROPS[k] for k in ("company_countries", "as_of", "max_api_calls", "page", "required_evidence")}, "investor_headquarters": _wf_prop("string", "Required. Investor city/region text, e.g. Toronto."), "round_amount_min": _wf_prop("integer", "Minimum round size in whole USD; default $10M. Only USD-denominated rounds can be compared; 0 disables the floor and the USD restriction.", minimum=0), "funding_within_days": _wf_prop("integer", "Funding window, default 365 days.", minimum=0, maximum=3650), "funding_page": PAGE_PROP, "max_pages": _wf_prop("integer", "Funding result pages of up to 50 rounds, default 2 (one credit each).", minimum=1, maximum=5)}, required=["investor_headquarters"]),
]


WORKFLOW_ARG_HINTS = {
    "count": "{tool} has no count mode: it returns a bounded evidence batch. Remove count.",
    "countries": "Use company_countries for company HQ and job_locations for where the job is.",
    "job_countries": "Use job_locations for where the job is.",
    "limit": "Use page_size/max_pages on the hiring workflows, max_companies on find_hiring_outlook.",
}
INVESTOR_ARG_HINTS = {
    "countries": "Use company_countries for the funded companies' HQ.",
    "city": "Use investor_headquarters for the investor's city.",
    "headquarters": "Use investor_headquarters for the investor's city.",
    "amount_min": "Use round_amount_min (whole USD).",
}


def _wf_arg_hint(tool, arg):
    hint = (INVESTOR_ARG_HINTS.get(arg) if tool == "research_investor_activity" else None) or WORKFLOW_ARG_HINTS.get(arg)
    return hint.format(tool=tool) if hint else None


async def _run_hr_workflow(name, args, api_key):
    descriptor = next(t for t in HR_WORKFLOW_TOOLS if t["name"] == name)
    props = descriptor["inputSchema"]["properties"]
    if "count" not in props and args.get("count") is False:
        # "count": false asks for the default behaviour; nothing to reject.
        args = {k: v for k, v in args.items() if k != "count"}
    unknown = sorted(set(args) - set(props))
    if unknown:
        hints = [h for h in (_wf_arg_hint(name, k) for k in unknown) if h]
        raise WorkflowError(
            f"Unknown {name} arguments: {', '.join(unknown)}. " + " ".join(hints)
            + (" " if hints else "") + "Accepted: " + ", ".join(props) + "."
        )
    for required in descriptor["inputSchema"].get("required", []):
        if required not in args:
            raise WorkflowError(f"{required} is required")
    for field, value in args.items():
        _validate_value(field, value, props[field])
    if args.get("headcount_min") is not None and args.get("headcount_max") is not None and args["headcount_min"] > args["headcount_max"]:
        raise WorkflowError("headcount_min cannot exceed headcount_max")
    ledger = {"api_calls": 0, "credits_used": 0, "max_api_calls": _wf_int(args, "max_api_calls", 12, 2, 30), "_deadline": time.monotonic() + 45}
    try:
        if name == "find_hiring_outlook":
            payload = await _wf_outlook(args, api_key, ledger)
        elif name == "research_investor_activity":
            payload = await _wf_investors(args, api_key, ledger)
        else:
            payload = await _wf_hiring(args, api_key, ledger, name == "find_funded_hiring_companies")
        payload["usage"] = {k: v for k, v in ledger.items() if not k.startswith("_")}
        payload.setdefault("unverified_requirements", _wf_requirements(args))
        if payload["unverified_requirements"] and payload.get("status") == "complete":
            payload["status"] = "partial"
        return payload
    except WorkflowError as error:
        error.usage = {k: v for k, v in ledger.items() if not k.startswith("_")}
        raise


HR_INSTRUCTIONS = """Signalbase MCP v2 for HR and recruiting teams.

What a good answer looks like: a shortlist of named companies, each with the
matching role(s), posting/source links, and one line on why it is a prospect
(size, funding, role, geography). Counts alone are not an answer. When the exact
requirement is not in the data (HQ city, founder nationality, office presence,
budget), say so in one line and still deliver the closest useful leads under a
clear label ("already hiring in the Bay Area; HQ city not verified"). Never relax
a requirement silently. Flag questionable matches instead of presenting them as
clean: a headcount that contradicts the company description, a Seed/Series A
label on a large company, a recruiting platform posting for clients.
- If a narrow role (bdr, sdr, account executive) finds nothing in a requested
  place, read by_place and hints: small companies abroad often title the same job
  "Business Development Executive/Manager" or "Sales Specialist". List those as
  "same function, different title".
- Never use a company-name blacklist or an arbitrary headcount cap to validate a
  funding record. Review the returned verification status, both stored dates and
  source identity; keep contradicted or unverified rounds out of exact matches.
- sector=fmcg (or cpg, consumer goods, food and beverage, beauty) maps to the
  stored industry labels; FMCG has no subcategory.
- max_postings_per_company can surface companies with few matching regional
  postings, but this does not prove a first hire, office opening or employee count.

Prefer these complete workflows to manual multi-call joins:
- find_hiring_companies: actual open roles; explicit company_countries (HQ) and
  job_locations (job location). Never silently replace one geography with the other.
  Mixed [Belgium, US, Netherlands, Luxembourg, Dubai] job_locations are an OR; Dubai
  stays a city. San Francisco Bay Area filters job metro only; company HQ city is unavailable.
- find_funded_hiring_companies: funding/hiring intersection computed BEFORE pagination,
  with matched funding evidence. Use posting_age_days_min=31 for over one month.
- research_investor_activity: investors in a city who participated in rounds elsewhere.
  Existing round-participation edges ARE available. Do not claim the graph is missing.
  Participation is not leadership: use lead_status/source_named_lead, never promote a
  stored_lead_flag to a sourced lead-investor claim.
- find_hiring_outlook: bounded trigger search and quiet-company checks for potential
  future hiring; use only for might/about-to-hire asks, not existing job listings.
Both hiring workflows offer count=true with separate exact company/posting totals.
If the user requests company names, a positive count is only the first step: fetch a
data page and cite posting/source URLs. For multiple roles use min_distinct_role_titles=2.
For recently funded remote startups use the funded-hiring workflow with work_mode=remote;
retain the funding constraint. For VC-backed hiring use funding_investor_type=vc and
disclose that this establishes indexed participation, not current ownership.
Use the outlook tool for "might hire soon" or "about to hire" requests. Cross-border
recruiting and advertised founding/regional hires belong in the current-hiring workflow
with separate company_countries and job_locations; they do not establish an office,
budget or a first actual hire. Do not substitute generic quiet-company forecasts.
They disclose interpreted_query, coverage/next_page, usage and unverified_requirements.
Never present a partial sample as exhaustive. A company can meet indexed filters while
historical headcount or job/company matching is inaccurate; no records were repaired.
Treat headcount as stored or estimated, never verified exact headcount. A posting is
only indexed-open under the stated freshness rule until its source is checked live.
Use required_evidence for founder-led sales, founder origin, office presence, first hire,
budget, scaling or PE ownership when those are in the request. Unknown means unknown;
do not treat Polish HQ as Polish founders or a Polish job as proof of a Polish office.
GTM means sales/marketing/customer-success/growth; GTM engineer is a specific title.
Staffing exclusions use known industry labels and cannot eliminate unknown/misclassified
agencies. Remote requires work-arrangement language; "remote sensing" and negated remote
work do not qualify. Remote never implies worldwide eligibility. Past Seed/Series A
rounds are observed records, not proof of current stage. Preserve their source links,
stored dates, verification status and uncertainty. A related posting never proves
founder nationality, founder-led sales, first employee, office opening, ownership or budget.

Use the six search tools to map hiring demand, find recruiting prospects and monitor
leadership changes. The same API key works here and on the classic endpoint.

## Possible first visible hires at quiet companies
For "might hire soon" or "about to hire" requests, use this supplied benchmark table.
It measures the observed odds of a first visible hire after a signal at a previously
quiet company. The figures are floors from announced joins:

| Signal | 30 days | 60 days | 90 days |
| Baseline | 2-6% | 4-9% | 4-10% |
| New VP | 20% | 30% | 36% |
| New Head of | 15% | 23% | 28% |
| New C-level | 7% | 11% | 13% |
| Series A | 5% | 8% | 10% |
| Seed | 3% | 4% | 5% |

Treat these as cohort-level benchmark floors, not a probability calculated for an
individual company. Never add rates when several signals overlap; report the strongest
applicable benchmark and list every observed signal separately. The table predicts any
first visible hire, not a particular role. Only suggest a role such as engineer when
Signalbase contains separate role-specific evidence. State that cohort definition,
sample size, measurement date and methodology were not supplied with the table.

To find these leads, search recent job changes for VP, Head-of and C-level joins and
recent funding for Seed or Series A. Then check hiring signals and label a company
"quiet" only when Signalbase shows no visible hiring before/at the trigger. Absence in
Signalbase is evidence coverage, not proof that the company has no jobs elsewhere.

Start a hiring search with role, countries, country_scope=hq for company HQ,
and headcount_min/max when requested. Role alternatives such as 'bdr or engineers'
retain OR semantics. These improved filters are automatic; no version flag is needed.
Count first: count=true is free. Multi-country counts include a best-effort breakdown
(up to six probes); by_country=false skips it. A null breakdown means the probe failed,
not zero results. Posting counts are not unique company counts.

Hiring searches default to indexed-open postings: unexpired listings, or posts within
60 days when expiry is unknown. This is an estimate, not source verification. `as_of`
anchors relative windows and this freshness rule, but it is not a historical snapshot:
later-indexed backdated records can change a replay. Historical end dates/calendar
presets retain history; include_expired=true is also available. Results always retain data rows, and hiring also includes companies
from the current page. Grouping merges titles and does not count individual vacancies.
Pagination still counts postings; check hasNextPage and deduplicate companies by domain.

Responses are compact by default; verbose=true returns all text and source fields.
Use jobUrl and source links as evidence. Do not invent roles, contacts or personal
identities when absent from the data. Country names, ISO codes and regions are accepted;
NORTH_AMERICA is the region and NA is Namibia. Unknown countries return a tool error
with guidance. Every executed data search costs one credit, even for zero results.
"""

HR_PROMPT = {
    "name": "recruiting-market",
    "description": "Find companies hiring a role in a geography, with evidence and a company-level summary.",
    "arguments": [
        {"name": "role", "description": "Role or family, e.g. engineers, BDR, or head of sales", "required": True},
        {"name": "geography", "description": "Company HQ countries or region, e.g. EU or US", "required": True},
    ],
}

HIRING_OUTLOOK_PROMPT = {
    "name": "likely-first-hire",
    "description": "Rank quiet companies with recent leadership or funding signals that may show a first visible hire.",
    "arguments": [
        {"name": "geography", "description": "Company HQ countries or region, e.g. US, EU, or NORDICS", "required": True},
        {"name": "horizon", "description": "Benchmark horizon: 30, 60, or 90 days (default 90)", "required": False},
        {"name": "role", "description": "Optional role hypothesis; only use when separate role evidence exists", "required": False},
    ],
}


def _hr_market_prompt(args):
    return {"messages": [{"role": "user", "content": {"type": "text", "text": (
        f"Map recruiting demand for {args.get('role', 'engineers')} at companies headquartered in "
        f"{args.get('geography', 'EU')}. Use find_hiring_companies with role and company_countries, "
        "count=true first. Then fetch the company groups and source evidence with the same "
        "filters and count omitted. Use the posting links, paginate when "
        "needed, and distinguish posting counts from unique companies. Report evidence "
        "dates and uncertainty about whether vacancies remain open."
    )}}]}


def _hiring_outlook_prompt(args):
    horizon = str(args.get("horizon") or "90").strip()
    if horizon not in ("30", "60", "90"):
        horizon = "90"
    role = str(args.get("role") or "").strip()
    role_note = (
        f" The user is interested in {role}, but do not infer that role from the benchmark; "
        "require separate role-specific evidence."
        if role else ""
    )
    return {"messages": [{"role": "user", "content": {"type": "text", "text": (
        f"Find quiet companies headquartered in {args.get('geography', 'US')} with a recent "
        f"New VP, New Head of, New C-level, Series A or Seed signal, and evaluate possible "
        f"first visible hiring within {horizon} days. Use find_hiring_outlook with company_countries "
        f"and horizon_days={horizon}; it searches triggers and checks both hiring and announced-join history. "
        "Rank by the strongest "
        "applicable supplied benchmark floor; never combine rates. Return trigger, trigger "
        "date, benchmark horizon/rate, supporting URLs, coverage limits and current visible "
        f"hiring status.{role_note}"
    )}}]}


_expose_api_filters(TOOLS)


def _tools_for_profile(profile):
    if profile != "hr":
        return TOOLS
    tools = deepcopy(TOOLS)
    for tool in tools:
        props = tool["inputSchema"]["properties"]
        props["filter_version"]["default"] = 2
        props["filter_version"]["description"] = "Enhanced strict filtering is automatic on MCP v2. Set 1 only for original matching."
        props["verbose"]["default"] = False
        props["verbose"]["description"] = "Default false: compact text and source lists. True returns the full API payload."
        props["by_country"]["default"] = True
        props["by_country"]["description"] = "Default true: add up to six best-effort country count probes on free counts. False skips probes."
        if tool["name"] == "search_hiring_signals":
            props["group_by_company"]["default"] = True
            props["include_expired"]["description"] = "Open postings by default. True includes history; explicit end dates/calendar presets also include history unless false is explicitly supplied."
            props["description"] = _wf_prop("string", "Full-text job-description search.")
            props["exclude_company_countries"] = COUNTRIES_PROP
        if tool["name"] == "search_funding_signals":
            props["date_basis"] = _wf_prop("string", "HR defaults to announced date (occurredAt only when no announced date exists). Stored dates are never modified.", enum=["announced", "occurred_at"], default="announced")
            props["investor_name"] = _wf_prop("string", "Substring match on actual funding-round investor names.")
            props["investors"] = _wf_prop("string", "Comma-separated exact investor names, OR. Uses existing investor-to-round relationships.")
            props["investor_type"] = _wf_prop("string", "Observed round participation by PE or VC investors, not current ownership.", enum=["pe", "vc"])
        if tool["name"] == "search_job_change_signals":
            props["categories"] = CATEGORIES_PIPE_PROP
            props["subcategories"] = SUBCATEGORIES_PROP
    # The workflow tools are exclusive to HR v2; classic clients keep their six tools.
    return deepcopy(HR_WORKFLOW_TOOLS) + tools


# ──────────────────────────────────────────────────────────────
# JSON-RPC handler
# ──────────────────────────────────────────────────────────────

async def _handle_jsonrpc(request_body: dict, api_key: str, profile: str = "classic") -> dict:
    """Route a JSON-RPC 2.0 request to the appropriate handler."""
    method = request_body.get("method", "")
    req_id = request_body.get("id")
    raw_params = request_body.get("params", {})
    if raw_params is None:
        params = {}
    elif not isinstance(raw_params, dict):
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32602, "message": "Invalid params: expected an object"},
        }
    else:
        params = raw_params

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {
                "name": "signalbase-hr-mcp" if profile == "hr" else SERVER_NAME,
                "version": "2.0.0" if profile == "hr" else SERVER_VERSION,
            },
            "instructions": HR_INSTRUCTIONS if profile == "hr" else INSTRUCTIONS,
        }

    elif method == "notifications/initialized":
        return None

    elif method == "tools/list":
        result = {"tools": _tools_for_profile(profile)}

    elif method == "prompts/list":
        result = {"prompts": PROMPTS + ([HR_PROMPT, HIRING_OUTLOOK_PROMPT] if profile == "hr" else [])}

    elif method == "prompts/get":
        prompt_name = params.get("name", "")
        if profile == "hr" and prompt_name == HR_PROMPT["name"]:
            result = _hr_market_prompt(params.get("arguments", {}) or {})
        elif profile == "hr" and prompt_name == HIRING_OUTLOOK_PROMPT["name"]:
            result = _hiring_outlook_prompt(params.get("arguments", {}) or {})
        elif prompt_name in PROMPT_TEMPLATES:
            prompt_args = params.get("arguments", {}) or {}
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
        raw_tool_args = params.get("arguments", {})
        if raw_tool_args is None:
            tool_args = {}
        elif not isinstance(raw_tool_args, dict):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": "Invalid tool arguments: expected an object"},
            }
        else:
            tool_args = raw_tool_args

        if profile == "hr" and tool_name in {t["name"] for t in HR_WORKFLOW_TOOLS}:
            if not api_key:
                result = _error_result("No API key provided. Pass Authorization: Bearer <key>.")
            else:
                try:
                    payload = await _run_hr_workflow(tool_name, tool_args, api_key)
                    # Compact JSON: workflow payloads run to tens of KB and indentation
                    # is pure token overhead for the calling model.
                    result = {"content": [{"type": "text", "text": json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str)}]}
                except WorkflowError as error:
                    result = _error_result(str(error))
                    result["_meta"] = {"usage": getattr(error, "usage", {"api_calls": 0, "credits_used": 0})}
            return {"jsonrpc": "2.0", "id": req_id, "result": result}

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
            try:
                descriptor = next(t for t in _tools_for_profile(profile) if t["name"] == tool_name)
                _validate_tool_arguments(
                    descriptor,
                    tool_args,
                    allow_unknown=profile != "hr",
                    allow_string_lists=True,
                )
                api_params, verbose, opts = _prepare_tool_args(tool_args, tool_name, profile)
            except WorkflowError as error:
                invalid = _error_result(str(error))
                invalid["_meta"] = {"usage": {"api_calls": 0, "credits_used": 0}}
                return {"jsonrpc": "2.0", "id": req_id, "result": invalid}
            try:
                api_response = await _call_api(endpoint, api_params, api_key)
                if opts["by_country"]:
                    api_response = await _with_country_breakdown(endpoint, api_params, api_key, api_response)
            except Exception as error:
                failed = _error_result(f"Upstream request failed ({type(error).__name__}); no result inferred.")
                failed["_meta"] = {"usage": {"api_calls": 1, "credits_used": 0, "credits_known": False}}
                return {"jsonrpc": "2.0", "id": req_id, "result": failed}

            if isinstance(api_response, dict) and api_response.get("error") is True:
                result = _error_result(_format_api_error(api_response))
                body = api_response.get("body") if isinstance(api_response.get("body"), dict) else {}
                result["_meta"] = {"usage": {
                    "api_calls": 1,
                    "credits_used": (body.get("meta") or {}).get("creditsUsed", 0),
                }}
            else:
                if (not verbose and api_params.get("count") in (True, "true") and isinstance(api_response, dict)
                        and api_response.get("data") == []):
                    # Compact count: an empty `data` list reads as "no results" to a model.
                    api_response = {k: v for k, v in api_response.items() if k != "data"}
                    api_response["countOnly"] = True
                result = _success_result(api_response, verbose=verbose, group_by_company=opts["group_by_company"])

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


def _invalid_request(message="Invalid Request"):
    return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": message}}


async def _handle_body(body, api_key: str, profile: str = "classic"):
    """Dispatch a parsed JSON-RPC body: one request object or a batch array.
    Returns (response, status); response None means notifications only (204)."""
    if isinstance(body, list):
        if not body:
            return _invalid_request("Invalid Request: empty batch"), 400
        responses = []
        for item in body:
            if not isinstance(item, dict):
                responses.append(_invalid_request())
                continue
            try:
                response = await _handle_jsonrpc(item, api_key, profile)
            except Exception:
                response = {
                    "jsonrpc": "2.0",
                    "id": item.get("id"),
                    "error": {"code": -32603, "message": "Internal error"},
                }
            if response is not None:
                responses.append(response)
        return (responses or None), 200
    if not isinstance(body, dict):
        return _invalid_request(), 400
    try:
        return await _handle_jsonrpc(body, api_key, profile), 200
    except Exception:
        return {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32603, "message": "Internal error"}}, 200


# ──────────────────────────────────────────────────────────────
# Cloudflare Workers entry point
# ──────────────────────────────────────────────────────────────

async def on_fetch(request, env):
    global _api_base_override
    _api_base_override = _resolve_api_base(env)
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

    profile = "hr" if urlsplit(str(request.url)).path.rstrip("/") == "/v2" else "classic"
    response, status = await _handle_body(body, api_key, profile)
    if status != 200:
        return _json_response(response, status)

    if response is None:
        return Response.new("", to_js(
            {
                "status": 204,
                "headers": Headers.new(to_js(CORS_HEADERS, dict_converter=Object.fromEntries)),
            },
            dict_converter=Object.fromEntries,
        ))

    return _json_response(response)
