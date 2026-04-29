#!/usr/bin/env python3
"""
Won/Loss Reasons L4Q — Matrix Opportunity report grouped by
`Reason_Won_Lost__c` × WON.

Drives playbook investment: which reasons cluster on the LOST side
(invest in countering them) vs the WON side (double down on them).

Per AGENTS.md SimCorp rules: Type IN ('Land','Expand'), FX-correct
via SF report aggregation.
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
    "developerName": "Scorecard_Won_Loss_Reasons_L4Q_v1",
    "name": "Scorecard · Won-Loss Reasons L4Q",
    "header": "Closed Land+Expand outcomes by Reason · last 365 days",
    "reportFormat": "MATRIX",
    "reportType": {"type": "Opportunity"},
    # Reason_Won_Lost__c deliberately omitted from detailColumns —
    # it's the grouping; SF rejects "groupings in the selected columns
    # list" when the same column appears in both.
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "Opportunity.APTS_Opportunity_ARR__c",
        "Opportunity.Lost_to_Competitor__c",
        "CLOSE_DATE",
    ],
    "groupingsDown": [
        {"name": "Opportunity.Reason_Won_Lost__c", "sortOrder": "Asc"},
    ],
    "groupingsAcross": [
        {"name": "WON", "sortOrder": "Asc"},
    ],
    "aggregates": [
        "s!Opportunity.APTS_Opportunity_ARR__c",
        "RowCount",
    ],
    "filters": [
        {"column": "TYPE", "operator": "equals", "value": "Land,Expand"},
        {"column": "CLOSED", "operator": "equals", "value": "True"},
    ],
    "exclusion": EXCLUDE_OPP_CRITERIA,
    "standardDateFilter": {
        # L4Q ≈ 24 months window matching the cycle-length + win-rate
        # widgets so all three time-series align.
        "column": "CLOSE_DATE",
        "durationValue": "CUSTOM",
        "startDate": "2025-04-29",
        "endDate": "2026-04-29",
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
        "groupingsAcross": [
            {"name": g["name"], "sortOrder": g.get("sortOrder", "Asc")}
            for g in rpt.get("groupingsAcross", [])
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

    print("[1/2] Build / update Won-Loss Reasons L4Q report")
    if args.dry_run:
        import json

        with open("/tmp/won_loss_body.json", "w") as f:
            json.dump(_build(REPORT), f, indent=2)
        print("  [dry-run] -> /tmp/won_loss_body.json")
        return 0

    rid = _find_or_create_report(REPORT, _build, token, instance, api_base)
    print(f"  -> {rid}")
    print(f"  view: https://simcorp.lightning.force.com/lightning/r/Report/{rid}/view")

    print("\n[2/2] Top reasons L4Q (won vs lost split)")
    run = _api(
        "GET",
        f"{api_base}/analytics/reports/{rid}?includeDetails=false",
        token,
        instance,
    )
    fact = run.get("factMap", {})
    gd = run.get("groupingsDown", {}).get("groupings", [])
    ga = run.get("groupingsAcross", {}).get("groupings", [])
    type_labels = [g.get("label") for g in ga]

    rows = []
    for g in gd:
        key = g.get("key")
        reason = g.get("label", "?")
        tot_arr = fact.get(f"{key}!T", {}).get("aggregates", [{}])[0].get("value", 0)
        cells = []
        for ag in ga:
            ak = ag.get("key")
            cell = fact.get(f"{key}!{ak}", {}).get("aggregates", [])
            arr = cell[0].get("value", 0) if len(cell) > 0 else 0
            cnt = cell[1].get("value", 0) if len(cell) > 1 else 0
            cells.append((arr, cnt, ag.get("label")))
        rows.append((tot_arr, reason, cells))
    rows.sort(reverse=True)

    print(
        f"  {'Reason':35s} | "
        + " | ".join(f"{(t or '?'):>10s}" for t in type_labels)
        + " | TOTAL ARR"
    )
    for tot, reason, cells in rows[:12]:
        cell_str = " | ".join(
            f"{cnt}@{arr / 1e6:>5.1f}M" if cnt else "         ·" for arr, cnt, _ in cells
        )
        print(f"  {(reason or '(null)')[:35]:35s} | {cell_str} | EUR {tot / 1e6:.1f}M")
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
