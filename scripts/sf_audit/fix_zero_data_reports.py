"""Phase 14d — patch zero-data reports surfaced by the convention audit.

Two distinct bug classes found:

  1. LeadList reports (5) shipped with scope='user'. apro owns 0 of 53,148
     leads → Marketing dashboard renders empty.
     **API constraint**: LeadList only accepts scope ∈ {'user', 'team'};
     'organization' / 'everything' / listview-name all rejected with HTTP 400.
     team scope returns ~2 records — also useless. The fix requires either:
       (a) Lightning UI: open report → Filters panel → Show Me ▸ All Leads
       (b) Rebuild reports against a custom Lead-with-no-scope report type
     Documented in state/sf_audit/MARKETING_DASHBOARD_LIMITATION.md.

  2. Deal Desk · Pending Approvals had standardDateFilter CLOSE_DATE=THIS_FY_Q.
     Pending-approval is a current-state question; the 8 real records all
     have CloseDate Q3-Q4 → 0 rows shown. Fix: drop the date filter. ✓ APPLIED.

Idempotent. Re-runnable.

Usage:
  python3 -m scripts.sf_audit.fix_zero_data_reports --dry-run
  python3 -m scripts.sf_audit.fix_zero_data_reports
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

import requests

from scripts.sf_audit.reports import sf_session

logger = logging.getLogger("sf_audit.fix_zero_data")

# Skipped — LeadList rejects org-wide scope via API. See module docstring.
LEAD_REPORTS: list[tuple[str, str]] = []

# Reports whose standardDateFilter on CLOSE_DATE is wrong (governance items
# shouldn't be CLOSE_DATE bound — they're current-state).
DATE_DROP_REPORTS = [
    ("00OTb000008mvx3MAA", "DD · Stage 3+ Pending Approval"),
]

REPORT_RO = ("id", "type", "currency", "buckets", "crossFilters", "scope")


def patch_metadata(
    instance: str,
    headers: dict,
    rid: str,
    label: str,
    mutate,
    dry_run: bool,
) -> bool:
    """Generic GET-mutate-PATCH for a single report."""
    r = requests.get(
        f"{instance}/services/data/v65.0/analytics/reports/{rid}/describe",
        headers=headers,
        timeout=20,
    )
    if r.status_code != 200:
        print(f"  ✗ {label}: GET failed {r.status_code}")
        return False
    md = r.json().get("reportMetadata") or {}
    before = {k: md.get(k) for k in ("scope", "standardDateFilter")}
    mutate(md)
    after = {k: md.get(k) for k in ("scope", "standardDateFilter")}
    if before == after:
        print(f"  ⚪ {label}: already correct")
        return False
    print(f"  ⤷ {label}")
    print(f"      before: {before}")
    print(f"      after:  {after}")
    if dry_run:
        return True
    # Strip read-only fields before PATCH — keep scope (we mutated it)
    patch_md = dict(md)
    for ro in ("id", "type", "currency", "buckets", "crossFilters"):
        patch_md.pop(ro, None)
    pr = requests.patch(
        f"{instance}/services/data/v65.0/analytics/reports/{rid}",
        headers={**headers, "Content-Type": "application/json"},
        json={"reportMetadata": patch_md},
        timeout=60,
    )
    if pr.status_code in (200, 201):
        print("      ✓ patched")
        return True
    print(f"      ✗ PATCH failed {pr.status_code}: {pr.text[:300]}")
    return False


def fix_lead_scope(md: dict[str, Any]) -> None:
    md["scope"] = "organization"


def fix_drop_date(md: dict[str, Any]) -> None:
    """Replace standardDateFilter with CUSTOM-no-dates = all-time scope.

    Setting to None silently no-ops (PATCH returns 200 but value persists).
    The reliable way to disable date scoping is durationValue=CUSTOM with
    null start/end dates — verified working on 00OTb000008mvx3MAA.
    """
    cur = md.get("standardDateFilter") or {}
    md["standardDateFilter"] = {
        "column": cur.get("column", "CLOSE_DATE"),
        "durationValue": "CUSTOM",
        "startDate": None,
        "endDate": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix zero-data reports")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    instance, token, _ = sf_session()
    headers = {"Authorization": f"Bearer {token}"}

    fixed = 0
    print("=== Lead reports: scope=user → organization ===")
    for rid, label in LEAD_REPORTS:
        if patch_metadata(instance, headers, rid, label, fix_lead_scope, args.dry_run):
            fixed += 1

    print("\n=== Governance reports: drop CLOSE_DATE filter ===")
    for rid, label in DATE_DROP_REPORTS:
        if patch_metadata(instance, headers, rid, label, fix_drop_date, args.dry_run):
            fixed += 1

    print(f"\nTotal fixed: {fixed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
