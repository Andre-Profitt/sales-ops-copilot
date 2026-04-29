#!/usr/bin/env python3
"""
Past Close Date — open Land+Expand opps where CloseDate is already in
the past. Different gaming pattern from indefinite-push (those keep
CloseDate moving forward); this catches forecast-hygiene failures
where the rep stopped maintaining the date entirely.

Live numbers verified 2026-04-29: 86 opps, EUR 17.5M raw (one rep
holds 34 of them).

Per AGENTS.md SimCorp rules: Land+Expand only, FX-correct via SF
report aggregation.
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
    "developerName": "Scorecard_Past_Close_Date_v1",
    "name": "Scorecard · Past Close Date by Rep",
    "header": "Open Land+Expand opps with CloseDate in the past — by Owner",
    "reportFormat": "SUMMARY",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "STAGE_NAME",
        "Opportunity.APTS_Opportunity_ARR__c",
        "CLOSE_DATE",
    ],
    "groupingsDown": [
        {"name": "FULL_NAME", "sortOrder": "Asc"},
    ],
    "aggregates": [
        "s!Opportunity.APTS_Opportunity_ARR__c",
        "RowCount",
    ],
    "filters": [
        {"column": "TYPE", "operator": "equals", "value": "Land,Expand"},
        {"column": "CLOSED", "operator": "equals", "value": "False"},
        # CloseDate strictly in the past (lessThan TODAY).
        {"column": "CLOSE_DATE", "operator": "lessThan", "value": "TODAY"},
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

    print("[1/2] Build / update Past Close Date by Rep report")
    if args.dry_run:
        import json

        with open("/tmp/past_close_body.json", "w") as f:
            json.dump(_build(REPORT), f, indent=2)
        print("  [dry-run] -> /tmp/past_close_body.json")
        return 0

    rid = _find_or_create_report(REPORT, _build, token, instance, api_base)
    print(f"  -> {rid}")
    print(f"  view: https://simcorp.lightning.force.com/lightning/r/Report/{rid}/view")

    print("\n[2/2] Past-close opps per rep")
    run = _api(
        "GET",
        f"{api_base}/analytics/reports/{rid}?includeDetails=false",
        token,
        instance,
    )
    fact = run.get("factMap", {})
    gd = run.get("groupingsDown", {}).get("groupings", [])
    grand_arr = fact.get("T!T", {}).get("aggregates", [{}])[0].get("value", 0)
    grand_cnt = fact.get("T!T", {}).get("aggregates", [{}, {}])[1].get("value", 0)

    rows = []
    for g in gd:
        key = g.get("key")
        rep = g.get("label", "?")
        cell = fact.get(f"{key}!T", {}).get("aggregates", [])
        arr = cell[0].get("value", 0) if len(cell) > 0 else 0
        cnt = cell[1].get("value", 0) if len(cell) > 1 else 0
        rows.append((arr, cnt, rep))
    rows.sort(reverse=True)
    print(f"  {'Owner':35s} {'Opps':>5s}  {'Past-Close ARR':>16s}")
    for arr, cnt, rep in rows[:10]:
        print(f"  {rep[:35]:35s} {cnt:>5d}  EUR {arr:>12,.0f}")
    print(
        f"\n  GRAND: {grand_cnt} past-close opps, EUR {grand_arr:,.0f} ARR (across {len(gd)} reps)"
    )
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
