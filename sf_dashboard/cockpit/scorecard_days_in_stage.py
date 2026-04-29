#!/usr/bin/env python3
"""
Sales Rep Scorecard widget: Avg Days in Stage by Rep.

Mean of `STAGE_DURATION` (Reports API for `LastStageChangeInDays`) across
each rep's open Land+Expand book. Tells the director who's letting deals
sit at a stage too long, on average, vs. the org P75. Companion to the
Stale Deals report (which is "no activity 14d+") — this one is "no
stage progression."
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
    "developerName": "Scorecard_Days_in_Stage_by_Rep_v1",
    "name": "Scorecard · Days in Stage by Rep",
    "header": "Avg Days in Stage by Owner — open Land+Expand",
    "reportFormat": "SUMMARY",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "Opportunity.APTS_Opportunity_ARR__c",
        "STAGE_DURATION",
    ],
    "groupingsDown": [
        {"name": "FULL_NAME", "sortOrder": "Asc"},
    ],
    "aggregates": [
        "a!STAGE_DURATION",  # AVG
        "RowCount",
    ],
    "filters": [
        {"column": "TYPE", "operator": "equals", "value": "Land,Expand"},
        {"column": "CLOSED", "operator": "equals", "value": "False"},
    ],
    "exclusion": EXCLUDE_OPP_CRITERIA,
    "standardDateFilter": {
        "column": "CLOSE_DATE",
        "durationValue": "CUSTOM",
        "startDate": "2000-01-01",
        "endDate": "2099-12-31",
    },
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

    print("[1/2] Build / update Days-in-Stage report")
    if args.dry_run:
        import json

        with open("/tmp/days_in_stage_body.json", "w") as f:
            json.dump(_build(REPORT), f, indent=2)
        print("  [dry-run] -> /tmp/days_in_stage_body.json")
        return 0

    rid = _find_or_create_report(REPORT, _build, token, instance, api_base)
    print(f"  -> {rid}")
    print(f"  view: https://simcorp.lightning.force.com/lightning/r/Report/{rid}/view")

    print("\n[2/2] Top 12 reps by avg days in stage (worst offenders)")
    run = _api(
        "GET",
        f"{api_base}/analytics/reports/{rid}?includeDetails=false",
        token,
        instance,
    )
    fact = run.get("factMap", {})
    gd = run.get("groupingsDown", {}).get("groupings", [])
    rows = []
    for g in gd:
        key = g.get("key")
        rep = g.get("label", "?")
        cell = fact.get(f"{key}!T", {}).get("aggregates", [])
        avg = cell[0].get("value", 0) if len(cell) > 0 else 0
        cnt = cell[1].get("value", 0) if len(cell) > 1 else 0
        rows.append((avg, cnt, rep))
    rows.sort(reverse=True)
    print(f"  {'Owner':35s} {'Opps':>5s}  {'Avg Days in Stage':>20s}")
    for avg, cnt, rep in rows[:12]:
        print(f"  {rep[:35]:35s} {cnt:>5d}  {avg:>16,.0f} d")
    grand_avg = fact.get("T!T", {}).get("aggregates", [{}])[0].get("value", 0)
    grand_cnt = fact.get("T!T", {}).get("aggregates", [{}, {}])[1].get("value", 0)
    print(f"\n  ORG: {grand_cnt} open opps, avg {grand_avg:,.0f} days in stage")
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
