"""
Shared SOQL exclusion filters for account-drilldown scripts.

Excluded entities are sales-ops test artifacts (QtC SOL test fixtures, dummy
opps, BI test cases) that pollute pipeline reporting. Centralized here so
drill, triage, and forecast stay in sync.

Verified 2026-04-28 against `apro@simcorp.com` preprod org. Filter strategy:
    1. Exclude entire test-bot owners (Maria Sabiniewicz — 43 opps, $16.7M ARR
       of QtC SOL test fixtures)
    2. Exclude obvious test Account names (CLM_SimCorp QtC*, QtC * — these are
       the SimCorp-internal QtC test orgs)
    3. Exclude obvious test Opportunity names (Test, TEST BI ISSUE, ASH Dummy,
       SBL Opp%, etc.)

Real opportunities are preserved — e.g. "SEB - AM and OM test quote"
($4M, Johanna Bergkvist) is a real account with "test" in the name; the
filter doesn't catch it because the owner and account are legitimate.
"""

from __future__ import annotations

# Owners whose entire opp book is system-test artifacts.
EXCLUDED_OWNERS: tuple[str, ...] = ("Maria Sabiniewicz",)

# Account name LIKE patterns that indicate internal test orgs.
EXCLUDED_ACCOUNT_PATTERNS: tuple[str, ...] = (
    "CLM_SimCorp QtC%",  # CLM_SimCorp QtC SOL Cologne, etc.
    "QtC %",  # QtC VCI Münster, etc.
)

# Opp name LIKE patterns that indicate test opportunities.
# Use specific patterns — `LIKE '%test%'` would catch real opps.
EXCLUDED_OPP_NAME_PATTERNS: tuple[str, ...] = (
    "Test",  # exact match for "Test"
    "TEST %",  # "TEST BI ISSUE", etc.
    "test_%",  # "test_26_04", etc.
    "TEST_%",  # "TEST_*"
    "QTC_Test%",
    "ASH Dummy%",
    "SBL Opp%",  # "SBL Opp £1", "SBL Opp £3 Trial..."
    "Back Office",  # the 760-day-stale $1.9M test
)


def _like_clause(field: str, patterns: tuple[str, ...], negate: bool = True) -> str:
    """
    Build a SOQL fragment for matching/excluding patterns.

    SOQL syntax notes:
    - `AND NOT field LIKE 'X'` is rejected ("unexpected token: NOT").
    - `(NOT field LIKE 'X')` works — NOT must be wrapped in its own parens
      when chained after another expression.
    - We emit `((NOT a) AND (NOT b) AND (NOT c))` for negation.
    """
    if not patterns:
        return ""
    atoms = []
    for p in patterns:
        # Exact match if no wildcard
        if "%" in p or "_" in p:
            atom = f"{field} LIKE '{p}'"
        else:
            atom = f"{field} = '{p}'"
        if negate:
            atoms.append(f"(NOT {atom})")
        else:
            atoms.append(atom)
    joiner = " AND " if negate else " OR "
    return f"({joiner.join(atoms)})"


def exclude_test_artifacts_clause(prefix: str = "AND") -> str:
    """
    Return a single SOQL fragment that excludes ALL test artifacts:
    test-bot owners, test account names, and test opp names.

    Pass `prefix="AND"` to append to an existing WHERE; `prefix=""` to start fresh.
    """
    parts: list[str] = []
    if EXCLUDED_OWNERS:
        owner_parts = [f"NOT Owner.Name LIKE '{n}%'" for n in EXCLUDED_OWNERS]
        parts.append(f"({' AND '.join(owner_parts)})")
    acct = _like_clause("Account.Name", EXCLUDED_ACCOUNT_PATTERNS, negate=True)
    if acct:
        parts.append(acct)
    opp = _like_clause("Name", EXCLUDED_OPP_NAME_PATTERNS, negate=True)
    if opp:
        parts.append(opp)
    if not parts:
        return ""
    body = " AND ".join(parts)
    return f"{prefix + ' ' if prefix else ''}{body}"


# Backward-compatible (Owners only) — kept so any caller that needs the
# narrower filter (e.g., aggregation queries that don't join Account) can
# still use it.
def exclude_test_owners_clause(prefix: str = "AND") -> str:
    if not EXCLUDED_OWNERS:
        return ""
    parts = [f"NOT Owner.Name LIKE '{name}%'" for name in EXCLUDED_OWNERS]
    return f"{prefix + ' ' if prefix else ''}({' AND '.join(parts)})"


# Convenience constants
EXCLUDE_TEST_ARTIFACTS = exclude_test_artifacts_clause("AND")
EXCLUDE_TEST_OWNERS = exclude_test_owners_clause("AND")
