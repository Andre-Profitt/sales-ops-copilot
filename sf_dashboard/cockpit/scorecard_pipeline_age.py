#!/usr/bin/env python3
"""
Pipeline Age Distribution — antidote to win-rate gaming.

Open Land+Expand pipeline bucketed by deal age (`AGE` column = days
since CreatedDate). Distribution shows the smoking gun for indefinite-
push behavior: deals >2yr old are essentially zombies that should
have closed (won or lost). Counting deals >12mo as still-pipeline
without scrutiny is how reps hide losses → win rate looks better
than reality.

Live numbers verified 2026-04-29: EUR 466.6M total open L+E, of
which EUR 154M (33%) is >2 years old and EUR 283M (61%) is >1 year.

Width 12 widget — full-row bar chart at the bottom of the Sales Rep
Scorecard dashboard. Region/Product Family filters bind via the
existing dashboard-level top filters.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
from typing import Any

from rebuild_viz import API_VERSION, _api, get_credentials  # type: ignore[import-not-found]
from upgrade_v2 import (  # type: ignore[import-not-found]
    EXCLUDE_OPP_CRITERIA,
    REPORT_FOLDER_ID,
    _find_or_create_report,
)


REPORT: dict[str, Any] = {
    "developerName": "Scorecard_Pipeline_Age_Dist_v1",
    "name": "Scorecard · Pipeline Age Distribution",
    "header": "Open Land+Expand pipeline by deal age — zombie-detection",
    "reportFormat": "SUMMARY",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "STAGE_NAME",
        "Opportunity.APTS_Opportunity_ARR__c",
        "AGE",
    ],
    "groupingsDown": [
        # Group by the bucket field defined below; renders as a bar
        # chart of ARR per age bucket.
        {"name": "BucketField_AgeBand", "sortOrder": "Asc"},
    ],
    "aggregates": [
        "s!Opportunity.APTS_Opportunity_ARR__c",
        "RowCount",
    ],
    "filters": [
        # SimCorp ARR/ACV split — Land+Expand only; APTS_Opportunity_ARR__c
        # is the sum field. Renewals use ACV with a separate report.
        {"column": "TYPE", "operator": "equals", "value": "Land,Expand"},
        {"column": "CLOSED", "operator": "equals", "value": "False"},
    ],
    "exclusion": EXCLUDE_OPP_CRITERIA,
    "standardDateFilter": {
        # Wide CLOSE_DATE window — we filter by IsClosed=false above; the
        # standardDateFilter is a no-op via 2000-2099 range.
        "column": "CLOSE_DATE",
        "durationValue": "CUSTOM",
        "startDate": "2000-01-01",
        "endDate": "2099-12-31",
    },
    # Numeric bucket on AGE (days since creation). Per verified bucket
    # gotchas (memory feedback_sf_activity_reports_clone_pattern + fixes
    # in upgrade_v3): do NOT include `useOther` or `otherBucketLabel`,
    # and the last bucket's `rangeUpperBound` MUST be None.
    "buckets": [
        {
            "developerName": "BucketField_AgeBand",
            "label": "Age Band",
            "sourceColumnName": "AGE",
            "bucketType": "number",
            "nullTreatedAsZero": True,
            "values": [
                {"rangeUpperBound": 90, "sourceDimensionValues": None, "label": "0-90d"},
                {"rangeUpperBound": 180, "sourceDimensionValues": None, "label": "91-180d"},
                {"rangeUpperBound": 365, "sourceDimensionValues": None, "label": "181-365d"},
                {"rangeUpperBound": 730, "sourceDimensionValues": None, "label": "1-2yr"},
                {"rangeUpperBound": None, "sourceDimensionValues": None, "label": "2yr+"},
            ],
        }
    ],
}


def _build(rpt: dict[str, Any]) -> dict[str, Any]:
    rm: dict[str, Any] = {
        "name": rpt["name"],
        "description": "",
        "reportFormat": rpt["reportFormat"],
        "reportType": rpt["reportType"],
        "detailColumns": list(rpt["detailColumns"]),
        "aggregates": list(rpt["aggregates"]),
        "groupingsDown": [
            {"name": g["name"], "sortOrder": g.get("sortOrder", "Asc")}
            for g in rpt.get("groupingsDown", [])
        ],
        "reportFilters": [*rpt.get("filters", []), *rpt.get("exclusion", [])],
        "standardDateFilter": rpt["standardDateFilter"],
        "buckets": rpt.get("buckets", []),
        "folderId": REPORT_FOLDER_ID,
        "developerName": rpt["developerName"],
    }
    return {"reportMetadata": rm}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    creds = get_credentials()
    token, instance = creds["access_token"], creds["instance_url"]
    api_base = f"/services/data/v{API_VERSION}"

    print("[1/2] Build / update Pipeline Age Distribution report")
    if args.dry_run:
        import json

        with open("/tmp/pipeline_age_body.json", "w") as f:
            json.dump(_build(REPORT), f, indent=2)
        print("  [dry-run] -> /tmp/pipeline_age_body.json")
        return 0

    rid = _find_or_create_report(REPORT, _build, token, instance, api_base)
    print(f"  -> {rid}")
    print(f"  view: https://simcorp.lightning.force.com/lightning/r/Report/{rid}/view")

    print("\n[2/2] ARR by age band")
    run = _api("GET", f"{api_base}/analytics/reports/{rid}?includeDetails=false", token, instance)
    fact = run.get("factMap", {})
    gd = run.get("groupingsDown", {}).get("groupings", [])
    grand_arr = fact.get("T!T", {}).get("aggregates", [{}])[0].get("value", 0)
    grand_cnt = fact.get("T!T", {}).get("aggregates", [{}, {}])[1].get("value", 0)

    print(f"  {'Age band':12s} {'Opps':>5s}  {'ARR':>16s}  {'% of total':>10s}")
    for g in gd:
        key = g.get("key")
        band = g.get("label", "?")
        cell = fact.get(f"{key}!T", {}).get("aggregates", [])
        arr = cell[0].get("value", 0) if len(cell) > 0 else 0
        cnt = cell[1].get("value", 0) if len(cell) > 1 else 0
        pct = arr / grand_arr * 100 if grand_arr else 0
        print(f"  {band:12s} {cnt:>5d}  EUR {arr:>12,.0f}  {pct:>8.1f}%")
    print(f"\n  GRAND: {grand_cnt} open L+E opps, EUR {grand_arr:,.0f}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as e:
        print(
            f"FATAL HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:1500]}",
            file=sys.stderr,
        )
        sys.exit(3)
