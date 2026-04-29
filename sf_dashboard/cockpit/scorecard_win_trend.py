#!/usr/bin/env python3
"""
Win Rate Trend Last 8 Fiscal Quarters — CRO Tier-1 metric.

Matrix Opportunity report grouped by FISCAL_QUARTER × WON. Each fiscal
quarter shows won + lost counts; visually it's a stacked bar of win
trend over time. Equivalent to the v2-doc `Win Rate Trend (rolling 8Q)`.
True Forecast Accuracy (start-of-Q ForecastCategory vs end-of-Q IsWon)
requires `OpportunityFieldHistory` snapshot infra — flagged as v2.
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


# Last 8 fiscal quarters — explicit CUSTOM range. SimCorp fiscal year =
# calendar year (verified from cockpit FY26 reports), so 8 quarters back
# from now (2026-Q2) is 2024-Q3 → 2024-07-01.
REPORT: dict[str, Any] = {
    "developerName": "Scorecard_Win_Rate_Trend_8Q_v1",
    "name": "Scorecard · Win Rate Trend · 8Q",
    "header": "Win Rate Trend — last 8 fiscal quarters",
    "reportFormat": "MATRIX",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "Opportunity.APTS_Opportunity_ARR__c",
        "CLOSE_DATE",
    ],
    "groupingsDown": [
        {"name": "FISCAL_QUARTER", "sortOrder": "Asc"},
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

    print("[1/2] Build / update Win Rate Trend (8Q) report")
    if args.dry_run:
        import json

        with open("/tmp/win_trend_body.json", "w") as f:
            json.dump(_build(REPORT), f, indent=2)
        print("  [dry-run] -> /tmp/win_trend_body.json")
        return 0

    rid = _find_or_create_report(REPORT, _build, token, instance, api_base)
    print(f"  -> {rid}")
    print(f"  view: https://simcorp.lightning.force.com/lightning/r/Report/{rid}/view")

    print("\n[2/2] Win rate per fiscal quarter")
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
    print(f"  groupings across (WON values): {type_labels}")
    print(f"\n  {'Fiscal Q':12s} | {'Lost':>6s} | {'Won':>6s} | {'Win rate':>9s}")
    for g in gd:
        key = g.get("key")
        fq = g.get("label", "?")
        cells = []
        for ag in ga:
            ak = ag.get("key")
            cell = fact.get(f"{key}!{ak}", {}).get("aggregates", [])
            cnt = cell[1].get("value", 0) if len(cell) > 1 else 0
            cells.append((ag.get("label"), cnt))
        won = sum(c for lbl, c in cells if (lbl or "").lower() in ("true", "1", "yes", "won"))
        lost = sum(c for lbl, c in cells if (lbl or "").lower() in ("false", "0", "no", "lost"))
        total = won + lost
        rate = won / total * 100 if total else 0
        print(f"  {fq:12s} | {lost:>6d} | {won:>6d} | {rate:>7.1f}%")
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
