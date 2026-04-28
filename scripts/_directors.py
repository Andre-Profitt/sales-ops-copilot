"""Director scope resolver.

The 9 MD-1 directors per memory project_sales_director_md1_presets.md
(2026-04-09, confirmed by Andre). Source-of-truth for which Salesforce
filter scope (Region + Country + Industry) maps to each director.

This module is the single place to resolve director identity. Every
LAND-cadence script that filters by director must go through here.

Filter mechanism: each director has a SOQL `where_clause` over
Account.* fields (Region__c, BillingCountry, Industry). The pipeline
inspection territory views actually use Salesforce role-hierarchy +
USING SCOPE mine, but we have no MD-1 user IDs on file, so we use
the Account-field-based scope map as the canonical filter contract.
"""

from __future__ import annotations

from typing import Optional


# Canonical 9 MD-1 directors with Account-scoped filter clauses.
# `book_codes` is preserved for backward-compat with earlier code paths
# but is no longer used to filter — `where_clause` is the live filter.
_DIRECTORS = [
    {
        "name": "Megan Miceli",
        "scope_label": "Canada",
        "book_codes": ["Canada"],
        "where_clause": "Account.BillingCountry = 'Canada'",
        "scope": "global",
        "user_id": None,
    },
    {
        "name": "Patrick Gaughan",
        "scope_label": "NA Asset Management",
        "book_codes": ["NA AM"],
        "where_clause": (
            "Account.Region__c = 'North America' "
            "AND Account.BillingCountry != 'Canada' "
            "AND Account.Industry = 'Asset Management'"
        ),
        "scope": "us_only",
        "user_id": None,
    },
    {
        "name": "Jesper Tyrer",
        "scope_label": "APAC",
        "book_codes": ["APAC"],
        "where_clause": "Account.Region__c = 'APAC'",
        "scope": "global",
        "user_id": None,
    },
    {
        "name": "Sarah Pittroff",
        "scope_label": "Central Europe",
        "book_codes": ["CE"],
        "where_clause": "Account.Region__c = 'Central Europe'",
        "scope": "global",
        "user_id": None,
    },
    {
        "name": "Francois Thaury",
        "scope_label": "Southern Europe",
        "book_codes": ["SWE"],
        "where_clause": "Account.Region__c = 'Southwestern Europe'",
        "scope": "global",
        "user_id": None,
    },
    {
        "name": "Dan Peppett",
        "scope_label": "UK & Ireland",
        "book_codes": ["UKI"],
        "where_clause": "Account.Region__c = 'United Kingdom & Ireland'",
        "scope": "global",
        "user_id": None,
    },
    {
        "name": "Christian Ebbesen",
        "scope_label": "NL & Nordics",
        "book_codes": ["NE"],
        "where_clause": "Account.Region__c = 'Northern Europe'",
        "scope": "global",
        "user_id": None,
    },
    {
        "name": "Mourad",
        "scope_label": "Middle East & Africa",
        "book_codes": ["MEA"],
        "where_clause": "Account.Region__c = 'Middle East & Africa'",
        "scope": "global",
        "user_id": None,
    },
    {
        "name": "Adam Steinhouse",
        "scope_label": "US Pension & Insurance",
        "book_codes": ["P&I"],
        "where_clause": (
            "Account.Region__c = 'North America' "
            "AND Account.BillingCountry != 'Canada' "
            "AND Account.Industry IN ('Pension','Insurance')"
        ),
        "scope": "us_only",
        "user_id": None,
    },
]


def canonical_directors() -> list[dict]:
    """Return the canonical list of 9 MD-1 directors."""
    return [d.copy() for d in _DIRECTORS]


def resolve_director_for_book(book_code: str) -> Optional[dict]:
    """Find the director who owns the given book code (legacy interface)."""
    for d in _DIRECTORS:
        if book_code in d["book_codes"]:
            return d.copy()
    return None
