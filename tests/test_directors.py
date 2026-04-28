"""Director scope resolver — maps Sales_Director_Book__c → director identity.

Per memory feedback_pi_views_naming.md, there are 9 MD-1 directors.
Adam Steinhouse is US-only (P&I); the others are global.
"""

from __future__ import annotations


def test_canonical_directors_returns_9():
    from scripts._directors import canonical_directors

    dirs = canonical_directors()
    assert len(dirs) == 9, f"expected 9 MD-1 directors, got {len(dirs)}"
    names = [d["name"] for d in dirs]
    assert "Adam Steinhouse" in names


def test_resolve_director_for_known_book():
    from scripts._directors import resolve_director_for_book

    d = resolve_director_for_book("P&I")
    assert d is not None
    assert d["name"] == "Adam Steinhouse"


def test_resolve_director_unknown_book_returns_none():
    from scripts._directors import resolve_director_for_book

    d = resolve_director_for_book("NONEXISTENT-BOOK-CODE")
    assert d is None
