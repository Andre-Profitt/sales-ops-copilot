"""Phase 4 — native SF reports for the KPI layer.

Sibling to scripts/sf_audit/reports.py (which built audit/dirty-data
reports). This module builds the *KPI-value* reports — Pipeline ARR by
Stage, Forecast & Closed Won, Renewal Pipeline ACV, etc. — so the live
numbers each KPI is supposed to surface are queryable in-app, with the
canonical conventions baked in:

  - Type IN ('Land','Expand') for ARR (Opportunity.APTS_Opportunity_ARR__c.CONVERT)
  - Type = 'Renewal' for ACV (Opportunity.APTS_Renewal_ACV__c.CONVERT) — separate report
  - Test-pollution exclusion via report filters mirroring _filters.py

Reuses sf_session() / create_report() / find_or_warn_folder() from reports.py.

Usage:
  python3 -m scripts.sf_audit.kpi_reports
  python3 -m scripts.sf_audit.kpi_reports --only kpi-pipeline-by-stage
  python3 -m scripts.sf_audit.kpi_reports --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Import the auth + create_report helpers from sibling module
from scripts.sf_audit.reports import (
    _filter,
    create_report,
    find_or_warn_folder,
    sf_session,
)

logger = logging.getLogger("sf_audit.kpi_reports")


# ─── Test-pollution filters (mirror _filters.py SOQL semantics into
#     SF report-filter format) ───────────────────────────────────────────
#
# SF report filter operators we use:
#   - notEqual (exact non-match)
#   - notContain (substring non-match)
# We approximate `NOT LIKE 'X%'` SOQL with `notContain X` — slightly more
# aggressive but acceptable for KPI reports where false-exclusions of
# legitimate opps with "Test" or "QtC" in their names are rare.

POLLUTION_FILTERS: list[dict[str, Any]] = [
    # Owner-based exclusion (catches the $16.7M Maria Sabiniewicz test book wholesale)
    _filter("FULL_NAME", "notEqual", "Maria Sabiniewicz"),
    # Account-name patterns (column code TBD; ACCOUNT.NAME hit FLS — try ACCOUNT_NAME)
    _filter("ACCOUNT_NAME", "notContain", "QtC"),
    # Opp-name patterns — pulled from _filters.py EXCLUDED_OPP_NAME_PATTERNS
    _filter("OPPORTUNITY_NAME", "notContain", "TEST"),
    _filter("OPPORTUNITY_NAME", "notContain", "ASH Dummy"),
    _filter("OPPORTUNITY_NAME", "notContain", "SBL Opp"),
    _filter("OPPORTUNITY_NAME", "notContain", "Back Office"),
    _filter("OPPORTUNITY_NAME", "notContain", "QTC_Test"),
    _filter("OPPORTUNITY_NAME", "notContain", "Generic q"),
    _filter("OPPORTUNITY_NAME", "notContain", "To Be Deleted"),
]


def _summary_grouping(name: str, sort_aggregate: str | None = None) -> dict[str, Any]:
    g: dict[str, Any] = {"name": name, "sortOrder": "Desc", "dateGranularity": "None"}
    if sort_aggregate:
        g["sortAggregate"] = sort_aggregate
    return g


def _this_quarter(column: str = "CLOSE_DATE") -> dict[str, Any]:
    return {"column": column, "durationValue": "THIS_FISCAL_QUARTER"}


def kpi_reports(folder_id: str | None) -> list[dict[str, Any]]:
    """Native SF reports for the executable KPIs in the RW/AP framework."""
    base_meta: dict[str, Any] = {}
    if folder_id:
        base_meta["folderId"] = folder_id

    return [
        # ── 1. Open Pipeline ARR by Stage (this-quarter L+E) ──────────
        {
            "key": "kpi-pipeline-by-stage",
            "label": "KPI · Pipeline ARR by Stage (this-Q L+E, pollution-filtered)",
            "metadata": {
                **base_meta,
                "name": "KPI · Pipeline ARR by Stage (this-Q L+E)",
                "description": "Open Land+Expand opps in current quarter, ARR sum by Stage. Pollution filter applied. Should match $27.7M baseline.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", "Opportunity.APTS_Opportunity_ARR__c.CONVERT"],
                "groupingsDown": [_summary_grouping("STAGE_NAME")],
                "aggregates": ["s!Opportunity.APTS_Opportunity_ARR__c.CONVERT", "RowCount"],
                "standardDateFilter": _this_quarter(),
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        # ── 2. Open Pipeline ARR by Owner ─────────────────────────────
        {
            "key": "kpi-pipeline-by-owner",
            "label": "KPI · Pipeline ARR by Owner (this-Q L+E)",
            "metadata": {
                **base_meta,
                "name": "KPI · Pipeline ARR by Owner (this-Q L+E)",
                "description": "Same scope as Pipeline by Stage but grouped by Owner. Surfaces concentration risk.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", "Opportunity.APTS_Opportunity_ARR__c.CONVERT"],
                "groupingsDown": [
                    _summary_grouping("FULL_NAME", sort_aggregate="s!Opportunity.APTS_Opportunity_ARR__c.CONVERT")
                ],
                "aggregates": ["s!Opportunity.APTS_Opportunity_ARR__c.CONVERT", "RowCount"],
                "standardDateFilter": _this_quarter(),
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        # ── 3. Closed Won ARR This Quarter ────────────────────────────
        {
            "key": "kpi-closed-won-quarter",
            "label": "KPI · Closed Won ARR This Quarter (L+E)",
            "metadata": {
                **base_meta,
                "name": "KPI · Closed Won ARR This Quarter (L+E)",
                "description": "Won Land+Expand bookings in current quarter, ARR sum by month and owner.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", "Opportunity.APTS_Opportunity_ARR__c.CONVERT"],
                "groupingsDown": [
                    _summary_grouping("FULL_NAME", sort_aggregate="s!Opportunity.APTS_Opportunity_ARR__c.CONVERT")
                ],
                "aggregates": ["s!Opportunity.APTS_Opportunity_ARR__c.CONVERT", "RowCount"],
                "standardDateFilter": _this_quarter(),
                "reportFilters": [
                    _filter("WON", "equals", "1"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        # ── 4. Lost ARR This Quarter ──────────────────────────────────
        {
            "key": "kpi-lost-arr-quarter",
            "label": "KPI · Lost ARR This Quarter (L+E)",
            "metadata": {
                **base_meta,
                "name": "KPI · Lost ARR This Quarter (L+E)",
                "description": "Closed-Lost Land+Expand opps in current quarter — ARR sum + count by stage where lost.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", "Opportunity.APTS_Opportunity_ARR__c.CONVERT"],
                "groupingsDown": [_summary_grouping("STAGE_NAME")],
                "aggregates": ["s!Opportunity.APTS_Opportunity_ARR__c.CONVERT", "RowCount"],
                "standardDateFilter": _this_quarter(),
                "reportFilters": [
                    _filter("CLOSED", "equals", "1"),
                    _filter("WON", "equals", "0"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        # ── 5. Renewal Pipeline ACV (this quarter) ────────────────────
        {
            "key": "kpi-renewal-pipeline-acv",
            "label": "KPI · Renewal Pipeline ACV (this-Q)",
            "metadata": {
                **base_meta,
                "name": "KPI · Renewal Pipeline ACV (this-Q)",
                "description": "Open Renewal opps in current quarter, ACV sum (uses APTS_Renewal_ACV__c, NOT ARR).",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", "Opportunity.APTS_Renewal_ACV__c.CONVERT"],
                "groupingsDown": [_summary_grouping("STAGE_NAME")],
                "aggregates": ["s!Opportunity.APTS_Renewal_ACV__c.CONVERT", "RowCount"],
                "standardDateFilter": _this_quarter(),
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Renewal"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        # ── 6. New Opportunities Created Last Month ───────────────────
        {
            "key": "kpi-new-opps-last-month",
            "label": "KPI · New Opps Created Last Month",
            "metadata": {
                **base_meta,
                "name": "KPI · New Opps Created Last Month",
                "description": "Opportunities created in last month, grouped by Type. Pollution-filtered. Tracks pipeline-build velocity.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", "Opportunity.APTS_Opportunity_ARR__c.CONVERT"],
                "groupingsDown": [_summary_grouping("TYPE")],
                "aggregates": ["RowCount"],
                "standardDateFilter": {"column": "CREATED_DATE", "durationValue": "LAST_MONTH"},
                "reportFilters": list(POLLUTION_FILTERS),
            },
        },
        # ── 7. Win Rate proxy (closed deals only this Q) ──────────────
        # SF reports can't compute win rate as a single percentage cleanly,
        # but we can ship a SUMMARY by IsWon so the user sees Won-vs-Lost
        # counts and can read off the rate.
        {
            "key": "kpi-win-loss-this-q",
            "label": "KPI · Won vs Lost This Quarter (L+E) — for win-rate read",
            "metadata": {
                **base_meta,
                "name": "KPI · Won vs Lost This Quarter (L+E)",
                "description": "Closed L+E opps in current quarter, grouped by IsWon (true/false). Read win rate as Won / (Won + Lost).",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", "Opportunity.APTS_Opportunity_ARR__c.CONVERT"],
                "groupingsDown": [_summary_grouping("WON")],
                "aggregates": ["s!Opportunity.APTS_Opportunity_ARR__c.CONVERT", "RowCount"],
                "standardDateFilter": _this_quarter(),
                "reportFilters": [
                    _filter("CLOSED", "equals", "1"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        # ── 8. Stage 3 Approvals This Month (governance) ──────────────
        {
            "key": "kpi-stage3-approvals-this-month",
            "label": "KPI · Stage 3+ Opps Created This Month",
            "metadata": {
                **base_meta,
                "name": "KPI · Stage 3+ Opps Created This Month",
                "description": "Opportunities entering Stage 3 or higher in last month — governance volume KPI.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", "Opportunity.APTS_Opportunity_ARR__c.CONVERT"],
                "groupingsDown": [_summary_grouping("STAGE_NAME")],
                "aggregates": ["s!Opportunity.APTS_Opportunity_ARR__c.CONVERT", "RowCount"],
                "standardDateFilter": {"column": "CREATED_DATE", "durationValue": "LAST_MONTH"},
                "reportFilters": [
                    _filter("STAGE_NAME", "contains", "3"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create native SF KPI reports")
    parser.add_argument("--only", type=str, help="comma-sep list of report keys")
    parser.add_argument("--folder", type=str, default="Sales Ops Audit")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("state/sf_audit/kpi_reports_manifest.json"),
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    instance, token, _ = sf_session()
    folder_id = find_or_warn_folder(instance, token, args.folder) if not args.dry_run else None
    reports = kpi_reports(folder_id)
    if args.only:
        wanted = {k.strip() for k in args.only.split(",")}
        reports = [r for r in reports if r["key"] in wanted]
        if not reports:
            print(f"No KPI reports matched --only={args.only!r}", file=sys.stderr)
            return 2

    print(f"Creating {len(reports)} KPI report(s) in {instance}")
    if args.dry_run:
        for r in reports:
            print(f"\n=== {r['key']}: {r['label']}")
            print(json.dumps(r["metadata"], indent=2))
        return 0

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
        "instance": instance,
        "folder_id": folder_id,
        "reports": [],
    }
    ok_count = 0
    for r in reports:
        print(f"\n→ {r['key']}: {r['label']}")
        result = create_report(instance, token, r["metadata"])
        manifest["reports"].append({"key": r["key"], "label": r["label"], **result})
        if result.get("ok"):
            ok_count += 1
            print(f"  ✓ {result['id']}")
            print(f"    {result['url']}")
        else:
            print(f"  ✗ {result.get('error', 'unknown')[:300]}")

    args.manifest.write_text(json.dumps(manifest, indent=2))
    print(f"\nDone. {ok_count}/{len(reports)} created. Manifest: {args.manifest}")
    return 0 if ok_count == len(reports) else 1


if __name__ == "__main__":
    sys.exit(main())
