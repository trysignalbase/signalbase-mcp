"""
Signalbase MCP Server — Cloudflare Workers (Python / Pyodide)
A Model Context Protocol server that proxies the Signalbase API.
Provides funding signals, acquisition signals, job change signals,
hiring signals, investor data, and company search via MCP tools.
"""

import html
import json
import re
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

# Response trimming (default mode, see _trim_response)
TRIM_MAX_CHARS = 300
TRIM_TEXT_FIELDS = {
    "descriptionText", "companyDescription", "description",
    "postContent", "personHeadline",
}
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
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
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
    "description": (
        "Worker-only flag, never forwarded to the API. Default false: long text "
        "fields (descriptions, post content, headlines) are truncated to 300 "
        "characters and logo/image URLs are dropped to save tokens. Pass true "
        "to receive the full, untrimmed API payload."
    ),
}

COUNTRIES_PROP = {
    "type": "string",
    "description": (
        "Comma-separated countries. Accepts ISO 3166-1 alpha-2 codes (US,GB,DE), "
        "English names (Sweden, Germany) or region shortcuts "
        f"{', '.join(COUNTRY_REGIONS)}. Unknown values return HTTP 400."
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
        "The Worker maps role families (sales/BD/SDR/AE, engineering, marketing, "
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
    "default": True,
    "description": (
        "On a free count over several countries, also return `byCountry` totals "
        "(one extra free probe per country, max 6). Set false to skip."
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
                        f"{', '.join(COUNTRY_REGIONS)}. Unknown values return HTTP 400."
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
            "and seniority info. Expired postings are excluded by default. "
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
                        f"region shortcuts {', '.join(COUNTRY_REGIONS)}. Unknown values return "
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
                    "description": (
                        "Default false: postings whose validThrough date has passed are "
                        "excluded. Pass true to include expired postings (historical analysis)."
                    ),
                    "default": False,
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

INSTRUCTIONS = """
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
  return HTTP 400 with a hint — fix the value, do not retry blindly.
- Hiring: `countries` matches the JOB LOCATION **or** the COMPANY HQ. Use
  `job_countries` (location only) or `company_countries` (HQ only) to pin one side.
- Job changes: `countries` matches the person's country or the company HQ.

## Hiring coverage warning
- The hiring index is ~84% US job locations. For European or other non-US targets do
  NOT filter by job location alone: use `company_countries=<region>` (+ `team_size`),
  or the funded-pool workflow below (`company_domain` list).
- Expired postings are excluded by default; pass `include_expired=true` only for
  historical analysis. Every row carries `jobUrl` and `validThrough`.

## Key Workflows

### 0. "Companies under N people hiring a <role> in <countries>"
`search_hiring_signals` with `role="<role as the user said it>"`, `headcount_max=N-1`,
`countries="<codes or regions>"`, `country_scope="hq"` (the user means where the company
is), `count=true` first (free; a multi-country count returns `byCountry` so you can say
which countries are empty), then the same without count plus `group_by_company=true`,
`limit=100`, `sort_by=date_posted`.
The Worker turns `role` into the right filter: role families (sales, BDR, engineers,
marketing…) match by department so free-text hiring posts are found; exact titles
(CTO, head of sales) match by title. Use `positions`/`departments` only for precise control.

### 1. Funded pool → who is hiring (recommended for "raised recently AND hiring X")
1. `search_funding_signals` with `countries`, `employee_count_max`, `date_preset`
   and `count=true` (free); then the same filters with `limit=50` (page if needed).
2. Collect each row's `companyWebsite` domain.
3. `search_hiring_signals` with `company_domain=<up to 50 domains>`,
   `departments=<dept>`, `limit=100`, `sort_by=date_posted` — one credit per chunk of 50.
4. Independent lane: `search_hiring_signals` with `company_countries=<region>`,
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
- By default responses are trimmed: long text fields are cut to 300 chars, logo/image
  URLs are dropped, `sources` is capped to 3 entries (with `sourcesTotal`), JSON-encoded
  list fields such as `companyCategories` are decoded and de-duplicated, and
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
        f"search_hiring_signals with company_domain=<up to 50 domains, comma-separated>, "
        f"departments={dept}, limit=100, sort_by=date_posted, sort_order=desc. "
        "Expired postings are already excluded; do not pass include_expired.\n"
        "4. Independent lane to catch companies whose round we missed: "
        f"search_hiring_signals with company_countries={geo}, team_size={team_size}, "
        f"departments={dept}, limit=100, sort_by=date_posted, sort_order=desc. "
        "Merge with step 3 and dedupe by domain.\n"
        "5. Output a table with columns: company | domain | round (type, amount, date, "
        "or '-' for lane-4-only rows) | title | location | jobUrl | validThrough. "
        "Keep only rows with a jobUrl, and state how many credits were spent."
    )
    return {"messages": [{"role": "user", "content": {"type": "text", "text": text}}]}


PROMPT_TEMPLATES = {
    "funded-and-hiring": _funded_and_hiring_prompt,
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
                        f"1. Search funding signals with subcategories={args.get('target_sector', 'saas')} and date_preset=last_30d (limit=50)\n"
                        "2. Collect the companyWebsite domains and search hiring signals with company_domain=<up to 50 domains>"
                        f"{' and departments=' + args['hiring_department'] if args.get('hiring_department') else ''} — one credit per chunk\n"
                        "3. The intersection is the list of companies that are both recently funded AND actively hiring\n"
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
        ordered = {k: props[k] for k in first if k in props}
        ordered.update({k: v for k, v in props.items() if k not in ordered})
        t["inputSchema"]["properties"] = ordered
    return tools


_reorder_intent_first(TOOLS)

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
        if part in ROLE_TITLES:
            positions.append(
                "bdr" if part in ("sdr", "sales development representative", "business development representative")
                else "account executive" if part == "ae"
                else part
            )
            continue
        matched = None
        for dept, words in ROLE_FAMILIES.items():
            if part in words or any(re.search(r"(^|[^a-z])" + re.escape(w) + r"([^a-z]|$)", part) for w in words if len(w) > 2):
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


def _country_breakdown_plan(params: dict):
    """For a free count over several country tokens, return (key, tokens) so the
    Worker can report a per-country breakdown; None when not applicable."""
    if not _is_truthy(params.get("count", False)):
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
            r = await _call_api(endpoint, sub, api_key)
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


def _prepare_tool_args(tool_args, tool_name: str = "") -> tuple:
    """Pre-process tools/call arguments before forwarding to the API.

    - pops the Worker-only `verbose` flag (the API returns 400 on unknown params)
    - joins list-valued arguments with "," (the API takes comma-separated strings)
    - resolves intent-level args (role, headcount_min/max, country_scope)
    Returns (params_for_api, verbose).
    """
    args = dict(tool_args or {})
    verbose = _is_truthy(args.pop("verbose", False))
    group_by_company = _is_truthy(args.pop("group_by_company", False))
    by_country = _is_truthy(args.pop("by_country", True))
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
    if isinstance(value, str) and "&" in value and ";" in value:
        # Titles arrive HTML-escaped from some sources ("Sales &amp; Marketing").
        decoded = html.unescape(value)
        if decoded != value:
            if changed is not None:
                changed[:] = [True]
            return decoded
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


def _trim_response(data, group_by_company: bool = False):
    """Default (non-verbose) response shaping: shorter text, no logos.
    Links (jobUrl, sources, LinkedIn URLs, companyWebsite) and validThrough are kept.
    `_meta.trimmed` is only added when something was actually cut, so free
    count=true responses and empty results stay clean."""
    changed = [False]
    trimmed = _trim_value(data, changed)
    if isinstance(trimmed, dict):
        rows = trimmed.get("data")
        endpoint = (trimmed.get("meta") or {}).get("endpoint")
        if group_by_company and endpoint == "signals.hiring" and isinstance(rows, list) and rows:
            # Opt-in grouped view. `data` is kept so existing consumers that read
            # rows keep working; the grouped view is an addition, not a swap.
            trimmed["companies"] = _group_hiring_by_company(rows)
            trimmed["companiesTotal"] = len(trimmed["companies"])
            trimmed["note"] = (
                "Grouped per company from this page's rows; a company with postings "
                "on several pages appears on each. pagination counts postings, not companies."
            )
            changed[0] = True
        if changed[0]:
            trimmed["_meta"] = dict(TRIM_META)
    return trimmed


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


def _success_result(data, verbose: bool = False, group_by_company: bool = False) -> dict:
    """Return an MCP tool success result with JSON-serialized data.
    Non-verbose (default): trimmed payload, compact JSON. Verbose: full payload, indented."""
    import json
    if verbose:
        text = json.dumps(data, indent=2, default=str, ensure_ascii=False)
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


# ──────────────────────────────────────────────────────────────
# JSON-RPC handler
# ──────────────────────────────────────────────────────────────

async def _handle_jsonrpc(request_body: dict, api_key: str) -> dict:
    """Route a JSON-RPC 2.0 request to the appropriate handler."""
    method = request_body.get("method", "")
    req_id = request_body.get("id")
    params = request_body.get("params", {}) or {}

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
        tool_args = params.get("arguments", {}) or {}

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
            api_params, verbose, opts = _prepare_tool_args(tool_args, tool_name)
            api_response = await _call_api(endpoint, api_params, api_key)
            if opts["by_country"]:
                api_response = await _with_country_breakdown(endpoint, api_params, api_key, api_response)

            if isinstance(api_response, dict) and api_response.get("error") is True:
                result = _error_result(_format_api_error(api_response))
            else:
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
