#!/usr/bin/env python3
"""
Sales Rep Scorecard — two more reports:
  - Win Rate by Rep (L4Q): Matrix Owner × WON, count + ARR per cell.
  - Open Pipeline by Rep: SUMMARY by Owner, count + ARR of open L+E.

Both Opportunity reportType, no clone needed. Same pattern as the
cockpit + stale + approvals scripts.
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


WIN_RATE_REPORT: dict[str, Any] = {
    "developerName": "Scorecard_Win_Rate_by_Rep_L4Q_v1",
    "name": "Scorecard · Win Rate by Rep · L4Q",
    "header": "Win/Loss Outcomes by Owner — last 365 days",
    "reportFormat": "MATRIX",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "Opportunity.APTS_Opportunity_ARR__c",
        "CLOSE_DATE",
    ],
    "groupingsDown": [{"name": "FULL_NAME", "sortOrder": "Asc"}],
    "groupingsAcross": [{"name": "WON", "sortOrder": "Asc"}],
    "aggregates": [
        "s!Opportunity.APTS_Opportunity_ARR__c",
        "RowCount",
    ],
    "filters": [
        {"column": "TYPE", "operator": "equals", "value": "Land,Expand"},
        {"column": "CLOSED", "operator": "equals", "value": "True"},
    ],
    "exclusion": EXCLUDE_OPP_CRITERIA,
    # `LAST_N_DAYS:365` is rejected on this org; CUSTOM with explicit
    # rolling window is the portable path (same workaround used in
    # upgrade_v3 for L4Q win rate).
    "standardDateFilter": {
        "column": "CLOSE_DATE",
        "durationValue": "CUSTOM",
        "startDate": "2025-04-29",
        "endDate": "2026-04-29",
    },
}


OPEN_PIPELINE_REPORT: dict[str, Any] = {
    "developerName": "Scorecard_Open_Pipeline_by_Rep_v1",
    "name": "Scorecard · Open Pipeline by Rep",
    "header": "Open Land+Expand Pipeline by Owner",
    "reportFormat": "SUMMARY",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "STAGE_NAME",
        "Opportunity.APTS_Opportunity_ARR__c",
        "CLOSE_DATE",
    ],
    "groupingsDown": [{"name": "FULL_NAME", "sortOrder": "Asc"}],
    "aggregates": [
        "s!Opportunity.APTS_Opportunity_ARR__c",
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


def _build_summary_body(rpt: dict[str, Any]) -> dict[str, Any]:
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


def _build_matrix_body(rpt: dict[str, Any]) -> dict[str, Any]:
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


def _summarize(
    rid: str, label: str, token: str, instance: str, api_base: str, top_n: int = 10
) -> None:
    run = _api(
        "GET",
        f"{api_base}/analytics/reports/{rid}?includeDetails=false",
        token,
        instance,
    )
    fact = run.get("factMap", {})
    gd = run.get("groupingsDown", {}).get("groupings", [])
    ga = run.get("groupingsAcross", {}).get("groupings", [])
    print(f"\n{label}: {len(gd)} reps")
    if ga:
        # Matrix — show won/lost split per rep
        type_labels = [g.get("label") for g in ga]
        rows = []
        for g in gd:
            key = g.get("key")
            rep = g.get("label", "?")
            tot_arr = fact.get(f"{key}!T", {}).get("aggregates", [{}])[0].get("value", 0)
            tot_cnt = fact.get(f"{key}!T", {}).get("aggregates", [{}, {}])[1].get("value", 0)
            cells = []
            for ag in ga:
                ak = ag.get("key")
                cell = fact.get(f"{key}!{ak}", {}).get("aggregates", [])
                arr = cell[0].get("value", 0) if len(cell) > 0 else 0
                cnt = cell[1].get("value", 0) if len(cell) > 1 else 0
                cells.append((arr, cnt))
            rows.append((tot_arr, rep, cells))
        rows.sort(reverse=True)

        # Matrix label is "WON: false" / "WON: true" usually — display as Lost/Won
        def lbl(t: str) -> str:
            tl = (t or "").lower()
            if tl in ("true", "1", "yes"):
                return "Won"
            if tl in ("false", "0", "no"):
                return "Lost"
            return t or "?"

        print(
            f"  {'Owner':30s} | "
            + " | ".join(f"{lbl(t):>14s}" for t in type_labels)
            + f" | {'Total ARR':>14s}"
        )
        for tot_arr, rep, cells in rows[:top_n]:
            cell_str = " | ".join(
                f"{cnt}@{arr / 1000:>5.0f}K" if cnt else "        ·" for arr, cnt in cells
            )
            print(f"  {rep[:30]:30s} | {cell_str} | EUR {tot_arr:>10,.0f}")
    else:
        # Simple SUMMARY — just rank by ARR
        rows = []
        for g in gd:
            key = g.get("key")
            rep = g.get("label", "?")
            cell = fact.get(f"{key}!T", {}).get("aggregates", [])
            arr = cell[0].get("value", 0) if len(cell) > 0 else 0
            cnt = cell[1].get("value", 0) if len(cell) > 1 else 0
            rows.append((arr, cnt, rep))
        rows.sort(reverse=True)
        print(f"  {'Owner':35s} {'Opps':>5s}  {'ARR':>16s}")
        for arr, cnt, rep in rows[:top_n]:
            print(f"  {rep[:35]:35s} {cnt:>5d}  EUR {arr:>12,.0f}")
    grand_arr = fact.get("T!T", {}).get("aggregates", [{}])[0].get("value", 0)
    grand_cnt = fact.get("T!T", {}).get("aggregates", [{}, {}])[1].get("value", 0)
    print(f"\n  GRAND: {grand_cnt} opps, EUR {grand_arr:,.0f} ARR")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    creds = get_credentials()
    token, instance = creds["access_token"], creds["instance_url"]
    api_base = f"/services/data/v{API_VERSION}"

    if args.dry_run:
        import json

        for label, rpt, builder in [
            ("WIN_RATE", WIN_RATE_REPORT, _build_matrix_body),
            ("OPEN_PIPELINE", OPEN_PIPELINE_REPORT, _build_summary_body),
        ]:
            body = builder(rpt)
            with open(f"/tmp/scorecard_{label.lower()}_body.json", "w") as f:
                json.dump(body, f, indent=2)
            print(f"  {label} body -> /tmp/scorecard_{label.lower()}_body.json")
        return 0

    print("[1/3] Build / update Win Rate by Rep report")
    win_rid = _find_or_create_report(WIN_RATE_REPORT, _build_matrix_body, token, instance, api_base)
    print(f"  -> {win_rid}")
    print(f"  view: https://simcorp.lightning.force.com/lightning/r/Report/{win_rid}/view")

    print("\n[2/3] Build / update Open Pipeline by Rep report")
    pipe_rid = _find_or_create_report(
        OPEN_PIPELINE_REPORT, _build_summary_body, token, instance, api_base
    )
    print(f"  -> {pipe_rid}")
    print(f"  view: https://simcorp.lightning.force.com/lightning/r/Report/{pipe_rid}/view")

    print("\n[3/3] Top 10 summary")
    _summarize(win_rid, "Win/Loss by Rep (L4Q)", token, instance, api_base)
    _summarize(pipe_rid, "Open Pipeline by Rep", token, instance, api_base)
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
