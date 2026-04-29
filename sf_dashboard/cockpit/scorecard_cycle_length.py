#!/usr/bin/env python3
"""
Sales Cycle Length Trend — won-deals avg days from creation to close,
grouped by FISCAL_QUARTER over the last 8 fiscal quarters.

If cycle length is trending up, push-gaming is increasing (deals stay
in pipeline longer). Companion to Win Rate Trend (8Q): one shows
pipeline conversion %, the other shows pipeline duration. Together
they triangulate forecast hygiene.

Live verified 2026-04-29: 797 won L+E deals last 365d, avg 288 days
from creation to close.
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
    "developerName": "Scorecard_Cycle_Length_Trend_8Q_v1",
    "name": "Scorecard · Sales Cycle Length 8Q",
    "header": "Won-deal cycle length (days, creation→close) by fiscal quarter",
    "reportFormat": "SUMMARY",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "Opportunity.APTS_Opportunity_ARR__c",
        "Opportunity.Number_of_Days_Since_Created__c",
        "CLOSE_DATE",
    ],
    "groupingsDown": [
        {"name": "FISCAL_QUARTER", "sortOrder": "Asc"},
    ],
    "aggregates": [
        # Average days from creation to close on the won cohort.
        "a!Opportunity.Number_of_Days_Since_Created__c",
        "RowCount",
    ],
    "filters": [
        # Per AGENTS.md: ARR side only; explicit Type filter; won-only cohort.
        {"column": "TYPE", "operator": "equals", "value": "Land,Expand"},
        {"column": "WON", "operator": "equals", "value": "1"},
        {"column": "CLOSED", "operator": "equals", "value": "True"},
    ],
    "exclusion": EXCLUDE_OPP_CRITERIA,
    "standardDateFilter": {
        # ~8 fiscal quarters back (matches the win-rate trend window).
        # `LAST_N_FISCAL_QUARTERS:N` is rejected on this org (verified
        # in upgrade_v3 — durationValue picklist is restrictive). Use
        # CUSTOM with explicit ~24-month window.
        "column": "CLOSE_DATE",
        "durationValue": "CUSTOM",
        "startDate": "2024-07-01",
        "endDate": "2026-06-30",
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

    print("[1/2] Build / update Sales Cycle Length 8Q report")
    if args.dry_run:
        import json

        with open("/tmp/cycle_length_body.json", "w") as f:
            json.dump(_build(REPORT), f, indent=2)
        print("  [dry-run] -> /tmp/cycle_length_body.json")
        return 0

    rid = _find_or_create_report(REPORT, _build, token, instance, api_base)
    print(f"  -> {rid}")
    print(f"  view: https://simcorp.lightning.force.com/lightning/r/Report/{rid}/view")

    print("\n[2/2] Cycle length trend")
    run = _api(
        "GET",
        f"{api_base}/analytics/reports/{rid}?includeDetails=false",
        token,
        instance,
    )
    fact = run.get("factMap", {})
    gd = run.get("groupingsDown", {}).get("groupings", [])
    print(f"  {'Fiscal Q':12s} {'Won':>5s}  {'Avg cycle (days)':>18s}")
    for g in gd:
        key = g.get("key")
        fq = g.get("label", "?")
        cell = fact.get(f"{key}!T", {}).get("aggregates", [])
        avg = cell[0].get("value", 0) if len(cell) > 0 else 0
        cnt = cell[1].get("value", 0) if len(cell) > 1 else 0
        print(f"  {fq:12s} {cnt:>5d}  {avg:>16,.0f} d")
    grand_avg = fact.get("T!T", {}).get("aggregates", [{}])[0].get("value", 0)
    grand_cnt = fact.get("T!T", {}).get("aggregates", [{}, {}])[1].get("value", 0)
    print(f"\n  GRAND: {grand_cnt} won deals, org avg {grand_avg:,.0f} days from creation→close")
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
