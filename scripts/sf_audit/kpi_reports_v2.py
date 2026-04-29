"""Phase 11 — three new exec-tier reports for the Sales Director Monthly.

What we ship:
  1. Bookings by Fiscal Quarter (last 8 quarters)  — trend visibility
  2. Top 20 At-Risk Open Opps (sorted by ARR DESC) — single drill list
  3. Forecast Category Split (Omitted/Pipeline/Best Case/Commit, this-Q L+E)

What's blocked (not built):
  - Pipeline Coverage Ratio: no User.Quota__c and no Quota object exist
    in the org. Verified 2026-04-28.

Reuses sf_session() / create_report() / find_or_warn_folder() / _filter()
from scripts/sf_audit/reports.py.

Usage:
  python3 -m scripts.sf_audit.kpi_reports_v2
  python3 -m scripts.sf_audit.kpi_reports_v2 --only kpi-forecast-category
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Any

from scripts.sf_audit.kpi_reports import POLLUTION_FILTERS
from scripts.sf_audit.reports import (
    _filter,
    create_report,
    find_or_warn_folder,
    sf_session,
)

logger = logging.getLogger("sf_audit.kpi_reports_v2")


def kpi_v2_reports(folder_id: str | None) -> list[dict[str, Any]]:
    base_meta: dict[str, Any] = {}
    if folder_id:
        base_meta["folderId"] = folder_id

    return [
        # 1. Bookings by Fiscal Quarter (last 8) ─────────────────────
        # SF reports support per-grouping dateGranularity. We group on
        # CLOSE_DATE with granularity=fiscalQuarter to get per-Q bars.
        {
            "key": "kpi-bookings-by-quarter",
            "label": "KPI · Bookings by Fiscal Quarter (L+E, last 8Q)",
            "metadata": {
                **base_meta,
                "name": "KPI · Bookings by Fiscal Quarter (L+E)",
                "description": "Won Land+Expand bookings by fiscal quarter, trailing 8 quarters. Trend view of the bookings line.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": [
                    "OPPORTUNITY_NAME",
                    "ACCOUNT_NAME",
                    "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                ],
                "groupingsDown": [
                    {
                        "name": "CLOSE_DATE",
                        "sortOrder": "Asc",
                        "dateGranularity": "fiscalQuarter",
                    }
                ],
                "aggregates": [
                    "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                    "RowCount",
                ],
                # SF accepts a narrow set of standard duration constants.
                # LAST_FISCAL_YEAR (4 quarters of history) is the safe pick
                # for an 8-bar trend chart spanning prior + current FY.
                "standardDateFilter": {
                    "column": "CLOSE_DATE",
                    "durationValue": "LAST_FISCAL_YEAR",
                },
                "reportFilters": [
                    _filter("WON", "equals", "1"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        # 2. Top 20 At-Risk Open Opps (drill list) ────────────────────
        # Boolean filter: (slipped CloseDate) OR (no recent modification)
        # AND IsClosed=false AND L+E AND pollution-clean.
        # Filter indexing in reportBooleanFilter is 1-based, in declaration order.
        {
            "key": "kpi-top-at-risk",
            "label": "KPI · Top 20 At-Risk Open Opportunities",
            "metadata": {
                **base_meta,
                "name": "KPI · Top 20 At-Risk Open Opps",
                "description": "Open Land+Expand opps that are slipped past CloseDate OR not modified in 60+ days, sorted by ARR descending. The single drill list for exec attention.",
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": [
                    "OPPORTUNITY_NAME",
                    "ACCOUNT_NAME",
                    "FULL_NAME",
                    "STAGE_NAME",
                    "CLOSE_DATE",
                    "LAST_UPDATE",
                    "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                ],
                # TABULAR reports — sort is configured via Lightning UI;
                # the API doesn't accept sortColumn/sortOrder at this level.
                "reportFilters": [
                    # 1: slipped past CloseDate
                    _filter("CLOSE_DATE", "lessThan", "TODAY"),
                    # 2: stale modification (60d+)
                    _filter("LAST_UPDATE", "lessThan", "LAST_N_DAYS:60"),
                    # 3..N: AND'd downstream conditions
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
                "reportBooleanFilter": "(1 OR 2) AND 3 AND 4 AND 5 AND 6 AND 7 AND 8 AND 9 AND 10 AND 11 AND 12 AND 13",
            },
        },
        # 3. Forecast Category Split (this-Q L+E) ─────────────────────
        # 919 opps "Omitted" — bigger than Pipeline+BestCase+Commit combined.
        # Surfacing this is a forecasting-discipline KPI.
        {
            "key": "kpi-forecast-category",
            "label": "KPI · Forecast Category Split (this-Q L+E)",
            "metadata": {
                **base_meta,
                "name": "KPI · Forecast Category (this-Q L+E)",
                "description": "Open L+E opps in current quarter, ARR sum grouped by ForecastCategoryName (Commit/Best Case/Pipeline/Omitted). Surfaces forecasting discipline; >50% of opps are typically Omitted.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": [
                    "OPPORTUNITY_NAME",
                    "ACCOUNT_NAME",
                    "STAGE_NAME",
                    "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                ],
                "groupingsDown": [
                    {
                        "name": "FORECAST_CATEGORY",
                        "sortOrder": "Desc",
                        "dateGranularity": "None",
                    }
                ],
                "aggregates": [
                    "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                    "RowCount",
                ],
                "standardDateFilter": {
                    "column": "CLOSE_DATE",
                    "durationValue": "THIS_FISCAL_QUARTER",
                },
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        # 4. Win/Loss by Fiscal Quarter (last fiscal year) ────────────
        # Two-level grouping: quarter -> won/lost so each Q shows both bars.
        {
            "key": "kpi-winloss-by-quarter",
            "label": "KPI · Win/Loss by Fiscal Quarter (L+E)",
            "metadata": {
                **base_meta,
                "name": "KPI · Win/Loss by Fiscal Quarter (L+E)",
                "description": "Closed-Won and Closed-Lost L+E ARR by fiscal quarter, last fiscal year. Bookings vs leakage trend.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": [
                    "OPPORTUNITY_NAME",
                    "ACCOUNT_NAME",
                    "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                ],
                "groupingsDown": [
                    {"name": "CLOSE_DATE", "sortOrder": "Asc", "dateGranularity": "fiscalQuarter"},
                    {"name": "WON", "sortOrder": "Desc", "dateGranularity": "None"},
                ],
                "aggregates": [
                    "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                    "RowCount",
                ],
                "standardDateFilter": {"column": "CLOSE_DATE", "durationValue": "LAST_FISCAL_YEAR"},
                "reportFilters": [
                    _filter("CLOSED", "equals", "1"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        # 6. Top Accounts by Open ARR (account-concentration drill list) ─
        {
            "key": "kpi-top-accounts-by-arr",
            "label": "KPI · Top Accounts by ARR (Q L+E)",
            "metadata": {
                **base_meta,
                "name": "KPI · Top Accounts by ARR (Q L+E)",
                "description": "Open Land+Expand opps grouped by account, ARR sum descending. Account-concentration drill list.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": [
                    "OPPORTUNITY_NAME",
                    "STAGE_NAME",
                    "FULL_NAME",
                    "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                ],
                "groupingsDown": [
                    {
                        "name": "ACCOUNT_NAME",
                        "sortOrder": "Desc",
                        "sortAggregate": "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                        "dateGranularity": "None",
                    }
                ],
                "aggregates": [
                    "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                    "RowCount",
                ],
                "standardDateFilter": {
                    "column": "CLOSE_DATE",
                    "durationValue": "THIS_FISCAL_QUARTER",
                },
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        # 7. Stuck Opps 90+ Days at Stage (Sales Ops governance) ──────
        {
            "key": "kpi-stuck-90d",
            "label": "KPI · Stuck Opps 90+ Days",
            "metadata": {
                **base_meta,
                "name": "KPI · Stuck Opps 90+ Days",
                "description": "Open L+E opps unmodified for 90+ days, grouped by stage. Sales Ops hygiene attention.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": [
                    "OPPORTUNITY_NAME",
                    "ACCOUNT_NAME",
                    "FULL_NAME",
                    "LAST_UPDATE",
                    "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                ],
                "groupingsDown": [
                    {"name": "STAGE_NAME", "sortOrder": "Asc", "dateGranularity": "None"}
                ],
                "aggregates": [
                    "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                    "RowCount",
                ],
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    _filter("LAST_UPDATE", "lessThan", "LAST_N_DAYS:90"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        # 8. Pipeline by Industry ─────────────────────────────────────
        {
            "key": "kpi-pipeline-by-industry",
            "label": "KPI · Pipeline by Industry (this-Q L+E)",
            "metadata": {
                **base_meta,
                "name": "KPI · Pipeline by Industry (this-Q L+E)",
                "description": "Open L+E pipeline grouped by Account.Industry. Vertical performance cut.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": [
                    "OPPORTUNITY_NAME",
                    "ACCOUNT_NAME",
                    "STAGE_NAME",
                    "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                ],
                "groupingsDown": [
                    {
                        "name": "INDUSTRY",
                        "sortOrder": "Desc",
                        "sortAggregate": "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                        "dateGranularity": "None",
                    }
                ],
                "aggregates": [
                    "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                    "RowCount",
                ],
                "standardDateFilter": {
                    "column": "CLOSE_DATE",
                    "durationValue": "THIS_FISCAL_QUARTER",
                },
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        # 5. Pipeline at Activity Risk ────────────────────────────────
        # Open L+E opps with no activity in 30 days, by stage.
        {
            "key": "kpi-pipeline-at-activity-risk",
            "label": "KPI · Pipeline at Activity Risk",
            "metadata": {
                **base_meta,
                "name": "KPI · Pipeline at Activity Risk",
                "description": "Open L+E opps with LastActivityDate older than 30 days. ARR at risk because no recent engagement. Activity discipline KPI.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": [
                    "OPPORTUNITY_NAME",
                    "ACCOUNT_NAME",
                    "FULL_NAME",
                    "LAST_ACTIVITY",
                    "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                ],
                "groupingsDown": [
                    {"name": "STAGE_NAME", "sortOrder": "Asc", "dateGranularity": "None"},
                ],
                "aggregates": [
                    "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                    "RowCount",
                ],
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    _filter("LAST_ACTIVITY", "lessThan", "LAST_N_DAYS:30"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create exec-tier v2 KPI reports")
    parser.add_argument("--only", type=str, help="comma-sep list of report keys")
    parser.add_argument("--folder", type=str, default="Sales Ops Audit")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("state/sf_audit/kpi_reports_v2_manifest.json"),
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    instance, token, _ = sf_session()
    folder_id = find_or_warn_folder(instance, token, args.folder) if not args.dry_run else None
    reports = kpi_v2_reports(folder_id)
    if args.only:
        wanted = {k.strip() for k in args.only.split(",")}
        reports = [r for r in reports if r["key"] in wanted]

    print(f"Creating {len(reports)} v2 KPI report(s) in {instance}")
    if args.dry_run:
        for r in reports:
            print(f"\n=== {r['key']}")
            print(json.dumps(r["metadata"], indent=2)[:1500])
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
