"""Director scope resolver.

The 9 MD-1 directors per memory feedback_pi_views_naming.md (2026-04-10).
Source-of-truth for which Salesforce User IDs correspond to which director,
and which Sales_Director_Book__c codes belong to each director's territory.

This module is the single place to resolve director identity. Every
LAND-cadence script that filters by director must go through here.
"""

from __future__ import annotations

from typing import Optional


# Canonical list. Names + book codes verified against PI views memory.
# Director SF user IDs are TBD — Andre to fill in once retrieved.
_DIRECTORS = [
    {"name": "Adam Steinhouse", "book_codes": ["P&I"], "scope": "us_only", "user_id": None},
    {"name": "Director CE", "book_codes": ["CE"], "scope": "global", "user_id": None},
    {"name": "Director SWE", "book_codes": ["SWE"], "scope": "global", "user_id": None},
    {"name": "Director UKI", "book_codes": ["UKI"], "scope": "global", "user_id": None},
    {"name": "Director NE", "book_codes": ["NE"], "scope": "global", "user_id": None},
    {"name": "Director Canada", "book_codes": ["Canada"], "scope": "global", "user_id": None},
    {"name": "Director NA AM", "book_codes": ["NA AM"], "scope": "global", "user_id": None},
    {
        "name": "Director EMEA Other",
        "book_codes": ["EMEA Other"],
        "scope": "global",
        "user_id": None,
    },
    {"name": "Director APAC", "book_codes": ["APAC"], "scope": "global", "user_id": None},
]


def canonical_directors() -> list[dict]:
    """Return the canonical list of 9 MD-1 directors."""
    return [d.copy() for d in _DIRECTORS]


def resolve_director_for_book(book_code: str) -> Optional[dict]:
    """Find the director who owns the given Sales_Director_Book__c code."""
    for d in _DIRECTORS:
        if book_code in d["book_codes"]:
            return d.copy()
    return None
