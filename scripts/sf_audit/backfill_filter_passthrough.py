"""Phase 14c — backfill the 4 standard dashboard filterColumns onto every
Opportunity-typed widget across the 10 dashboards that lack them.

Driven by the cross-dashboard consistency audit (state/sf_audit/dashboard_consistency_audit.json):
  - 58 widgets currently have no filterColumns at all
  - 38 are clearly Opportunity-typed (aggregates contain Opportunity.*)
  - 20 are RowCount-only or non-Opp; for those we GET the report's describe and
    only patch if reportType.type == 'Opportunity' (or its custom variants)

Idempotent: re-running on an already-patched dashboard is a no-op.

Per memory feedback_dashboard_filters_over_report_overrides — we set filter
pass-through at the WIDGET level (filterColumns), not on the underlying report.
SF's dashboard runtime cascades dashboard filters into matching filterColumns.

Usage:
  python3 -m scripts.sf_audit.backfill_filter_passthrough --dry-run
  python3 -m scripts.sf_audit.backfill_filter_passthrough
  python3 -m scripts.sf_audit.backfill_filter_passthrough --only 01ZTb00000FxYTFMA3
"""

from __future__ import annotations

import argparse
import logging
import sys

import requests

from scripts.sf_audit.rebuild_sd_dashboard import STANDARD_FILTER_COLS
from scripts.sf_audit.reports import sf_session

logger = logging.getLogger("sf_audit.backfill_filters")

# SD Monthly already has the 4 filterColumns and dashboard-level filters.
# Audit list of dashboards needing fix (the other 10).
DASHBOARDS = [
    "01ZTb00000FSP9JMAX",  # Sales Ops Quarterly KPI
    "01ZTb00000FxYTFMA3",  # Renewals
    "01ZTb00000FxYUrMAN",  # Win/Loss Analysis
    "01ZTb00000FxYY5MAN",  # Deal Desk Operations
    "01ZTb00000FxYZhMAN",  # CRO Cockpit
    "01ZTb00000FxYbJMAV",  # Marketing & Lead Funnel  (Lead-typed widgets skipped)
    "01ZTb00000FxYcvMAF",  # Forecast Accuracy & Pacing
    "01ZTb00000FxYeXMAV",  # Account Health Watch
    "01ZTb00000FxYg9MAF",  # Activity Health
    "01ZTb00000FxYhlMAF",  # Quarter Close Pacing
]

OPP_REPORT_TYPES = {
    "Opportunity",
    "OpportunityHistory",
    "OpportunityFieldHistory",
    "OpportunityProductTrending",
    "PipelineHistorical",
}

DASHBOARD_RO_FIELDS = (
    "id",
    "createdById",
    "createdDate",
    "lastModifiedDate",
    "namespace",
    "type",
    "developerName",
    "folderId",
    "folderName",
    "url",
    "labels",
    "ownerId",
)


def report_is_opp(instance: str, headers: dict, report_id: str, cache: dict) -> bool:
    """Look up report type. Cached. Returns True for Opportunity-typed reports."""
    if report_id in cache:
        return cache[report_id]
    r = requests.get(
        f"{instance}/services/data/v65.0/analytics/reports/{report_id}/describe",
        headers=headers,
        timeout=20,
    )
    if r.status_code != 200:
        cache[report_id] = False
        return False
    rt = (r.json().get("reportMetadata") or {}).get("reportType") or {}
    rtype = rt.get("type") or ""
    is_opp = rtype in OPP_REPORT_TYPES
    cache[report_id] = is_opp
    return is_opp


def process_dashboard(
    instance: str,
    token: str,
    dashboard_id: str,
    cache: dict,
    dry_run: bool,
) -> tuple[int, int, int]:
    """Returns (touched, skipped_already, skipped_non_opp)."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{instance}/services/data/v65.0/analytics/dashboards/{dashboard_id}"
    r = requests.get(url + "/describe", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"  ✗ {dashboard_id}: GET failed {r.status_code}")
        return 0, 0, 0
    md = r.json()
    components = list(md.get("components") or [])
    name = md.get("name") or "?"
    print(f"\n[{dashboard_id}] {name}  ({len(components)} components)")

    touched = skipped_already = skipped_non_opp = 0
    for c in components:
        rid = c.get("reportId")
        if not rid:
            continue
        props = c.get("properties") or {}
        cur_filters = props.get("filterColumns") or []
        cur_names = {f.get("name") for f in cur_filters}
        std_names = {f["name"] for f in STANDARD_FILTER_COLS}
        if std_names.issubset(cur_names):
            skipped_already += 1
            continue
        # Check report type
        if not report_is_opp(instance, headers, rid, cache):
            print(f"    ⚪ skip (non-Opp): {c.get('header', '?')}  reportId={rid}")
            skipped_non_opp += 1
            continue
        # Merge: keep any extras already present, ensure 4 standards present.
        merged = list(STANDARD_FILTER_COLS)
        for f in cur_filters:
            if f.get("name") not in std_names:
                merged.append(f)
        props["filterColumns"] = merged
        c["properties"] = props
        print(f"    ✚ patch:        {c.get('header', '?')}")
        touched += 1

    if not touched:
        print("  ⚪ nothing to patch")
        return 0, skipped_already, skipped_non_opp

    if dry_run:
        print(f"  [dry-run] would patch {touched} components")
        return touched, skipped_already, skipped_non_opp

    md["components"] = components
    for ro in DASHBOARD_RO_FIELDS:
        md.pop(ro, None)
    pr = requests.patch(
        url,
        headers={**headers, "Content-Type": "application/json"},
        json=md,
        timeout=60,
    )
    if pr.status_code in (200, 201):
        print(f"  ✓ patched {touched} components")
    else:
        print(f"  ✗ PATCH failed {pr.status_code}: {pr.text[:300]}")
        return 0, skipped_already, skipped_non_opp
    return touched, skipped_already, skipped_non_opp


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill standard 4 filterColumns onto Opp widgets"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", type=str, help="comma-sep dashboard IDs to limit scope")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    instance, token, _ = sf_session()
    cache: dict[str, bool] = {}
    targets = DASHBOARDS
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        targets = [d for d in DASHBOARDS if d in wanted]

    total_t = total_a = total_n = 0
    for did in targets:
        t, a, n = process_dashboard(instance, token, did, cache, args.dry_run)
        total_t += t
        total_a += a
        total_n += n

    print("\n=== Summary ===")
    print(f"  patched:           {total_t}")
    print(f"  skipped (already): {total_a}")
    print(f"  skipped (non-Opp): {total_n}")
    print(f"  report-type lookups cached: {len(cache)} ({sum(cache.values())} Opp)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
