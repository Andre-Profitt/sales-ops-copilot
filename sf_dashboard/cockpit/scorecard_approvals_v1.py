#!/usr/bin/env python3
"""
Sales Rep Scorecard widget: Approvals Stuck by Rep.

Per-rep view of the EUR 60.3M Commercial-Approval-stuck pipeline that
the cockpit displays as a single org-level Metric. Same predicate
(Submit_for_Stage_20_Review = true AND Stage_20_Approval = false AND
submitted >5 days ago), grouped by Opportunity Owner so directors can
see WHO has deals frozen at the gate.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
from typing import Any

from rebuild_viz import (  # type: ignore[import-not-found]
    API_VERSION,
    _api,
    get_credentials,
)
from upgrade_v2 import (  # type: ignore[import-not-found]
    EXCLUDE_OPP_CRITERIA,
    REPORT_FOLDER_ID,
    _find_or_create_report,
)


APPROVALS_STUCK_REPORT: dict[str, Any] = {
    "developerName": "Scorecard_Approvals_Stuck_by_Rep_v1",
    "name": "Scorecard · Approvals Stuck by Rep",
    "header": "Stage 20 Commercial Approval — stuck >5 days, by Owner",
    "reportFormat": "SUMMARY",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "Opportunity.APTS_Opportunity_ARR__c",
        "Opportunity.Submit_for_Stage_20_Review_Date__c",
    ],
    "groupingsDown": [
        {"name": "FULL_NAME", "sortOrder": "Asc"},
    ],
    "aggregates": [
        "s!Opportunity.APTS_Opportunity_ARR__c",
        "RowCount",
    ],
    "filters": [
        # SimCorp ARR/ACV split: Stage 20 Commercial Approval applies to
        # Land+Expand only. Renewals use ACV + a different governance
        # flow. Filtering to L+E prevents a blended row count vs ARR
        # sum where Renewal opps would inflate the count without
        # contributing to ARR.
        {"column": "TYPE", "operator": "equals", "value": "Land,Expand"},
        {"column": "CLOSED", "operator": "equals", "value": "False"},
        {
            "column": "Opportunity.Submit_for_Stage_20_Review__c",
            "operator": "equals",
            "value": "1",
        },
        {
            "column": "Opportunity.Stage_20_Approval__c",
            "operator": "equals",
            "value": "0",
        },
        {
            "column": "Opportunity.Submit_for_Stage_20_Review_Date__c",
            "operator": "lessThan",
            "value": "LAST_N_DAYS:5",
        },
    ],
    "exclusion": EXCLUDE_OPP_CRITERIA,
    "standardDateFilter": {
        "column": "Opportunity.Submit_for_Stage_20_Review_Date__c",
        "durationValue": "CUSTOM",
        "startDate": "2000-01-01",
        "endDate": "2099-12-31",
    },
}


def _build_body(rpt: dict[str, Any]) -> dict[str, Any]:
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
        "reportFilters": [
            *rpt.get("filters", []),
            *rpt.get("exclusion", []),
        ],
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

    print("[1/2] Build / update Approvals Stuck by Rep report")
    if args.dry_run:
        import json

        body = _build_body(APPROVALS_STUCK_REPORT)
        with open("/tmp/scorecard_approvals_body.json", "w") as f:
            json.dump(body, f, indent=2)
        print("  [dry-run] -> /tmp/scorecard_approvals_body.json")
        return 0

    rid = _find_or_create_report(APPROVALS_STUCK_REPORT, _build_body, token, instance, api_base)
    print(f"  -> {rid}")
    print(f"  view: https://simcorp.lightning.force.com/lightning/r/Report/{rid}/view")

    print("\n[2/2] Approvals stuck per rep")
    run = _api(
        "GET",
        f"{api_base}/analytics/reports/{rid}?includeDetails=false",
        token,
        instance,
    )
    fact = run.get("factMap", {})
    gd = run.get("groupingsDown", {}).get("groupings", [])
    grand_arr = fact.get("T!T", {}).get("aggregates", [{}])[0].get("value", 0)
    grand_count = fact.get("T!T", {}).get("aggregates", [{}])[1].get("value", 0)

    rows = []
    for g in gd:
        key = g.get("key")
        rep = g.get("label", "?")
        cell = fact.get(f"{key}!T", {}).get("aggregates", [])
        arr = cell[0].get("value", 0) if len(cell) > 0 else 0
        cnt = cell[1].get("value", 0) if len(cell) > 1 else 0
        rows.append((arr, cnt, rep))

    rows.sort(reverse=True)
    print(f"  {'Owner':35s} {'Opps':>5s}  {'Frozen ARR':>16s}")
    for arr, cnt, rep in rows[:15]:
        print(f"  {rep[:35]:35s} {cnt:>5d}  EUR {arr:>12,.0f}")
    print(
        f"\n  GRAND: {grand_count} opps stuck >5d, EUR {grand_arr:,.0f} ARR (across {len(gd)} reps)"
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
