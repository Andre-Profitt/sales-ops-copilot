#!/usr/bin/env python3
"""
Wire 5 scorecard reports into the Sales Rep Scorecard dashboard.
Dashboard 01ZTb00000FyJSAMA3 was created via Playwright (Lightning UI).
This script PATCHes the layout + components via Analytics REST.

Layout (12-col grid):
  Row 0-9:   Task Volume Matrix          (Lightning Table, full width)
  Row 10-15: Open Pipeline Bar | Stale Deals Bar  (6 cols each)
  Row 16-21: Win Rate Matrix  | Approvals Stuck Bar (6 cols each)
"""

from __future__ import annotations

import json
import sys
import urllib.error
from typing import Any

from rebuild_viz import API_VERSION, _api, get_credentials  # type: ignore[import-not-found]

DASHBOARD_ID = "01ZTb00000FyJSAMA3"

REPORT_IDS = {
    "task_volume": "00OTb000008nZsrMAE",
    "open_pipeline": "00OTb000008nbMnMAI",
    "stale": "00OTb000008nak5MAA",
    "win_rate": "00OTb000008nbLBMAY",
    "approvals_stuck": "00OTb000008navNMAQ",
}


def _matrix_table(report_id: str, header: str, max_rows: int = 50) -> dict[str, Any]:
    return {
        "reportId": report_id,
        "header": header,
        "title": None,
        "footer": None,
        "type": "Report",
        "properties": {
            "visualizationType": "LightningTable",
            "drillUrl": f"/lightning/r/Report/{report_id}/view",
            "filterColumns": [],
            "autoSelectColumns": True,
            "useReportChart": False,
            "reportFormat": "MATRIX",
            "aggregates": [{"name": "RowCount"}],
            "maxRows": max_rows,
            "visualizationProperties": {"displayUnits": "auto", "decimalPrecision": 0},
        },
    }


def _summary_bar(
    report_id: str,
    header: str,
    grouping: str,
    aggregate: str,
    max_rows: int = 12,
    severity: str | None = None,
) -> dict[str, Any]:
    vp: dict[str, Any] = {"displayUnits": "auto", "decimalPrecision": 1}
    if severity == "critical":
        vp["metricFontColor"] = "#C25454"
    return {
        "reportId": report_id,
        "header": header,
        "title": None,
        "footer": None,
        "type": "Report",
        "properties": {
            "visualizationType": "Bar",
            "drillUrl": f"/lightning/r/Report/{report_id}/view",
            "filterColumns": [],
            "autoSelectColumns": True,
            "useReportChart": False,
            "reportFormat": "SUMMARY",
            "groupings": [
                {
                    "name": grouping,
                    "inheritedReportSort": "reportGrouping",
                    "sortAggregate": None,
                    "sortOrder": None,
                }
            ],
            "aggregates": [{"name": aggregate}],
            "maxRows": max_rows,
            "visualizationProperties": vp,
        },
    }


def main() -> int:
    creds = get_credentials()
    token, instance = creds["access_token"], creds["instance_url"]
    api_base = f"/services/data/v{API_VERSION}"

    print(f"[1/3] GET dashboard {DASHBOARD_ID}/describe")
    describe = _api(
        "GET", f"{api_base}/analytics/dashboards/{DASHBOARD_ID}/describe", token, instance
    )
    print(f"  current widgets: {len(describe.get('components') or [])}")
    print(
        f"  layout: {describe.get('layout', {}).get('numColumns')}-col × {describe.get('layout', {}).get('rowHeight')}px"
    )

    print("\n[2/3] Build 5 components + layout")
    components = [
        _matrix_table(
            REPORT_IDS["task_volume"], "Task Volume by Owner × Type · last 30d", max_rows=30
        ),
        _summary_bar(
            REPORT_IDS["open_pipeline"],
            "Open Pipeline by Rep (ARR)",
            "FULL_NAME",
            "s!Opportunity.APTS_Opportunity_ARR__c",
            max_rows=12,
        ),
        _summary_bar(
            REPORT_IDS["stale"],
            "Stale Deals by Rep (no activity 14d+)",
            "FULL_NAME",
            "s!Opportunity.APTS_Opportunity_ARR__c",
            max_rows=12,
            severity="critical",
        ),
        _matrix_table(REPORT_IDS["win_rate"], "Win/Loss by Rep · L4Q", max_rows=30),
        _summary_bar(
            REPORT_IDS["approvals_stuck"],
            "Approvals Stuck by Rep (>5d)",
            "FULL_NAME",
            "s!Opportunity.APTS_Opportunity_ARR__c",
            max_rows=10,
            severity="critical",
        ),
    ]
    layout_components = [
        {"row": 0, "column": 0, "rowspan": 10, "colspan": 12},  # task volume — full width top
        {"row": 10, "column": 0, "rowspan": 6, "colspan": 6},  # open pipeline left
        {"row": 10, "column": 6, "rowspan": 6, "colspan": 6},  # stale right
        {"row": 16, "column": 0, "rowspan": 6, "colspan": 6},  # win rate left
        {"row": 16, "column": 6, "rowspan": 6, "colspan": 6},  # approvals stuck right
    ]

    new_layout = json.loads(json.dumps(describe.get("layout", {})))
    new_layout["components"] = layout_components
    new_layout.setdefault("gridLayout", True)
    new_layout.setdefault("numColumns", 12)
    new_layout.setdefault("rowHeight", 36)

    # runningUser describe response is a {displayName, id} object but
    # PATCH expects either the ID string or the same object. Pass through
    # whichever describe gave us. Including filters=[] explicitly because
    # the empty new dashboard's PATCH validation seems strict (cockpit
    # PATCHes work with filters set, this stub has none).
    body = {
        "name": describe.get("name"),
        "description": describe.get("description"),
        "folderId": describe.get("folderId"),
        "dashboardType": describe.get("dashboardType"),
        "runningUser": describe.get("runningUser"),
        "chartTheme": describe.get("chartTheme"),
        "colorPalette": describe.get("colorPalette"),
        "components": components,
        "layout": new_layout,
        "filters": describe.get("filters") or [],
    }
    # Drop None values — they're the most common JSON_PARSER_ERROR cause.
    body = {k: v for k, v in body.items() if v is not None}

    print(f"\n[3/3] PATCH dashboard: {len(components)} widgets")
    try:
        _api("PATCH", f"{api_base}/analytics/dashboards/{DASHBOARD_ID}", token, instance, body=body)
        print("  [OK] PATCH succeeded")
    except RuntimeError as e:
        print(f"  [FAIL] {str(e)[:600]}", file=sys.stderr)
        return 2

    verify = _api(
        "GET", f"{api_base}/analytics/dashboards/{DASHBOARD_ID}/describe", token, instance
    )
    n = len(verify.get("components") or [])
    rids = {c.get("reportId") for c in verify.get("components") or []}
    expected = set(REPORT_IDS.values())
    print(f"\n[verify] components: {n}, all 5 reports present: {expected.issubset(rids)}")
    print(f"\n[done] https://simcorp.lightning.force.com/lightning/r/Dashboard/{DASHBOARD_ID}/view")
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
