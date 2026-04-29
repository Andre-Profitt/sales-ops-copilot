"""Phase 14 — Renewals Dashboard.

Separate motion from L+E. Anchored on APTS_Renewal_ACV__c (NOT ARR).

Widgets:
  KPI tiles:  Open Renewal ACV · Won this-Q · Lost this-Q · Win Rate proxy
  Trend:      Renewal Win/Loss by Fiscal Quarter
  Composition: ACV by Stage · ACV by Region · ACV by Industry
  Risk:       At-Risk Renewals (Risk_of_Potential_Termination = High/Medium)
  Pacing:     Upcoming Renewals next 30/60/90 days (existing report)

Creates reports + dashboard via Analytics API.

Usage:
  python3 -m scripts.sf_audit.build_renewals_dashboard
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

import requests

from scripts.sf_audit.improve_dashboard_layout import pack_layout, widget_size
from scripts.sf_audit.kpi_reports import POLLUTION_FILTERS
from scripts.sf_audit.rebuild_sd_dashboard import STANDARD_FILTER_COLS
from scripts.sf_audit.reports import (
    _filter,
    create_report,
    find_or_warn_folder,
    sf_session,
)

logger = logging.getLogger("sf_audit.build_renewals")


def renewal_reports(folder_id: str | None) -> list[dict[str, Any]]:
    base: dict[str, Any] = {}
    if folder_id:
        base["folderId"] = folder_id
    R = "Opportunity.APTS_Renewal_ACV__c.CONVERT"
    sR = f"s!{R}"

    return [
        {
            "key": "ren-open-by-stage",
            "metadata": {
                **base,
                "name": "REN · Open Pipeline by Stage",
                "description": "Open renewal opps by stage, ACV sum (this-Q).",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", R],
                "groupingsDown": [
                    {"name": "STAGE_NAME", "sortOrder": "Asc", "dateGranularity": "None"}
                ],
                "aggregates": [sR, "RowCount"],
                "standardDateFilter": {
                    "column": "CLOSE_DATE",
                    "durationValue": "THIS_FISCAL_QUARTER",
                },
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Renewal"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        {
            "key": "ren-open-by-region",
            "metadata": {
                **base,
                "name": "REN · Open Pipeline by Region",
                "description": "Open renewal ACV by Sales Region (this-Q).",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", R],
                "groupingsDown": [
                    {
                        "name": "Account.Region__c",
                        "sortOrder": "Desc",
                        "sortAggregate": sR,
                        "dateGranularity": "None",
                    }
                ],
                "aggregates": [sR, "RowCount"],
                "standardDateFilter": {
                    "column": "CLOSE_DATE",
                    "durationValue": "THIS_FISCAL_QUARTER",
                },
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Renewal"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        {
            "key": "ren-open-by-industry",
            "metadata": {
                **base,
                "name": "REN · Open Pipeline by Industry",
                "description": "Open renewal ACV by Industry (this-Q).",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", R],
                "groupingsDown": [
                    {
                        "name": "INDUSTRY",
                        "sortOrder": "Desc",
                        "sortAggregate": sR,
                        "dateGranularity": "None",
                    }
                ],
                "aggregates": [sR, "RowCount"],
                "standardDateFilter": {
                    "column": "CLOSE_DATE",
                    "durationValue": "THIS_FISCAL_QUARTER",
                },
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Renewal"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        {
            "key": "ren-won-this-q",
            "metadata": {
                **base,
                "name": "REN · Won This Quarter",
                "description": "Won renewals this fiscal quarter, ACV by region.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", R],
                "groupingsDown": [
                    {
                        "name": "Account.Region__c",
                        "sortOrder": "Desc",
                        "sortAggregate": sR,
                        "dateGranularity": "None",
                    }
                ],
                "aggregates": [sR, "RowCount"],
                "standardDateFilter": {
                    "column": "CLOSE_DATE",
                    "durationValue": "THIS_FISCAL_QUARTER",
                },
                "reportFilters": [
                    _filter("WON", "equals", "1"),
                    _filter("TYPE", "equals", "Renewal"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        {
            "key": "ren-lost-this-q",
            "metadata": {
                **base,
                "name": "REN · Lost This Quarter",
                "description": "Lost renewals this fiscal quarter, ACV by region.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", R],
                "groupingsDown": [
                    {
                        "name": "Account.Region__c",
                        "sortOrder": "Desc",
                        "sortAggregate": sR,
                        "dateGranularity": "None",
                    }
                ],
                "aggregates": [sR, "RowCount"],
                "standardDateFilter": {
                    "column": "CLOSE_DATE",
                    "durationValue": "THIS_FISCAL_QUARTER",
                },
                "reportFilters": [
                    _filter("CLOSED", "equals", "1"),
                    _filter("WON", "equals", "0"),
                    _filter("TYPE", "equals", "Renewal"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        {
            "key": "ren-winloss-trend",
            "metadata": {
                **base,
                "name": "REN · Win/Loss by Quarter",
                "description": "Renewal Won and Lost ACV by fiscal quarter, last fiscal year.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", R],
                "groupingsDown": [
                    {"name": "CLOSE_DATE", "sortOrder": "Asc", "dateGranularity": "fiscalQuarter"},
                    {"name": "WON", "sortOrder": "Desc", "dateGranularity": "None"},
                ],
                "aggregates": [sR, "RowCount"],
                "standardDateFilter": {"column": "CLOSE_DATE", "durationValue": "LAST_FISCAL_YEAR"},
                "reportFilters": [
                    _filter("CLOSED", "equals", "1"),
                    _filter("TYPE", "equals", "Renewal"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        {
            "key": "ren-stage-age",
            "metadata": {
                **base,
                "name": "REN · Renewal Stage Age",
                "description": "Open renewals by stage, average days at current stage.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", R],
                "groupingsDown": [
                    {"name": "STAGE_NAME", "sortOrder": "Asc", "dateGranularity": "None"}
                ],
                "aggregates": ["a!STAGE_DURATION", "RowCount"],
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Renewal"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        {
            "key": "ren-at-risk",
            "metadata": {
                **base,
                "name": "REN · At-Risk Renewals",
                "description": "Open renewals where Account.Risk_of_Potential_Termination = High or Medium.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", "STAGE_NAME", R],
                "groupingsDown": [
                    {
                        "name": "Account.Risk_of_Potential_Termination__c",
                        "sortOrder": "Desc",
                        "dateGranularity": "None",
                    }
                ],
                "aggregates": [sR, "RowCount"],
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Renewal"),
                    _filter("Account.Risk_of_Potential_Termination__c", "equals", "High,Medium"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
    ]


def make_widget(
    report_id: str,
    header: str,
    title: str,
    viz: str,
    grouping: str | None = None,
    aggregate: str | None = None,
    granularity: str = "None",
) -> dict[str, Any]:
    g = []
    if grouping:
        g = [
            {
                "inheritedReportSort": None,
                "name": grouping,
                "sortAggregate": None,
                "sortOrder": "Asc",
                "dateGranularity": granularity,
            }
        ]
    return {
        "header": header,
        "footer": None,
        "title": title,
        "reportId": report_id,
        "type": "Report",
        "componentData": 0,
        "chartTheme": None,
        "properties": {
            "aggregates": [{"name": aggregate}] if aggregate else [],
            "autoSelectColumns": False,
            "drillUrl": None,
            "filterColumns": list(STANDARD_FILTER_COLS),
            "groupings": g,
            "maxRows": None,
            "reportFormat": "SUMMARY",
            "sort": None,
            "useReportChart": False,
            "visualizationProperties": {
                "decimalPrecision": -1,
                "displayUnits": "auto",
                "legendPosition": "Right",
                "showPercentages": viz == "Pie",
                "showValues": True,
            },
            "visualizationType": viz,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", default="Sales Ops Audit")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    instance, token, _ = sf_session()
    headers = {"Authorization": f"Bearer {token}"}
    # Dashboard folder lookup — find_or_warn_folder() looks at Type='Report'.
    # For dashboards we need Type='Dashboard'. Use the existing 'Andre' folder
    # discovered via SOQL: SELECT Id FROM Folder WHERE Type='Dashboard' AND Name='Andre'
    DASHBOARD_FOLDER_ID = "00lTb000006OCRBIA4"  # Andre's dashboard folder
    folder_id = find_or_warn_folder(instance, token, args.folder) if not args.dry_run else None
    dashboard_folder_id = DASHBOARD_FOLDER_ID

    # Step 1: create reports
    rids: dict[str, str] = {}
    for r in renewal_reports(folder_id):
        if args.dry_run:
            print(f"DRY: {r['key']}")
            continue
        result = create_report(instance, token, r["metadata"])
        if result.get("ok"):
            rids[r["key"]] = result["id"]
            print(f"  ✓ {r['key']:25s} → {result['id']}")
        else:
            print(f"  ✗ {r['key']}: {result.get('error', '')[:200]}")
    if args.dry_run:
        return 0

    # Step 2: build dashboard with widgets referencing those reports
    R_AGG = "s!Opportunity.APTS_Renewal_ACV__c.CONVERT"
    components = []
    if "ren-open-by-stage" in rids:
        components.append(
            make_widget(
                rids["ren-open-by-stage"],
                "Renewal ACV by Stage",
                "Open this-Q",
                "Funnel",
                grouping="STAGE_NAME",
                aggregate=R_AGG,
            )
        )
    if "ren-open-by-region" in rids:
        components.append(
            make_widget(
                rids["ren-open-by-region"],
                "Renewal ACV by Region",
                "Open this-Q",
                "Bar",
                grouping="Account.Region__c",
                aggregate=R_AGG,
            )
        )
    if "ren-open-by-industry" in rids:
        components.append(
            make_widget(
                rids["ren-open-by-industry"],
                "Renewal ACV by Industry",
                "Open this-Q",
                "Bar",
                grouping="INDUSTRY",
                aggregate=R_AGG,
            )
        )
    if "ren-winloss-trend" in rids:
        components.append(
            make_widget(
                rids["ren-winloss-trend"],
                "Win/Loss by Fiscal Quarter",
                "Last FY (ACV)",
                "Column",
                grouping="CLOSE_DATE",
                granularity="fiscalQuarter",
                aggregate=R_AGG,
            )
        )
    if "ren-won-this-q" in rids:
        components.append(
            make_widget(
                rids["ren-won-this-q"],
                "Won This Quarter",
                "ACV by region",
                "Bar",
                grouping="Account.Region__c",
                aggregate=R_AGG,
            )
        )
    if "ren-lost-this-q" in rids:
        components.append(
            make_widget(
                rids["ren-lost-this-q"],
                "Lost This Quarter",
                "ACV by region",
                "Bar",
                grouping="Account.Region__c",
                aggregate=R_AGG,
            )
        )
    if "ren-stage-age" in rids:
        components.append(
            make_widget(
                rids["ren-stage-age"],
                "Renewal Stage Age",
                "Avg days, by stage",
                "Bar",
                grouping="STAGE_NAME",
                aggregate="a!STAGE_DURATION",
            )
        )
    if "ren-at-risk" in rids:
        components.append(
            make_widget(
                rids["ren-at-risk"],
                "At-Risk Renewals",
                "High/Medium termination risk",
                "Bar",
                grouping="Account.Risk_of_Potential_Termination__c",
                aggregate=R_AGG,
            )
        )

    sizes = [
        (3, 4)
        if (c.get("properties") or {}).get("visualizationType") == "Metric"
        else widget_size(
            (c.get("properties") or {}).get("visualizationType") or "",
            (c.get("properties") or {}).get("reportFormat") or "",
        )
        for c in components
    ]
    layout = pack_layout(sizes)

    dash_md = {
        "name": "Renewals Dashboard",
        "description": "Renewal pipeline (ACV motion). Built 2026-04-28.",
        "components": components,
        "layout": {"components": layout, "gridLayout": None},
        "filters": [],
        "dashboardType": "SpecifiedUser",
        "runningUser": None,
        "colorPalette": "wildflowers",
    }
    dash_md["folderId"] = dashboard_folder_id

    pr = requests.post(
        f"{instance}/services/data/v65.0/analytics/dashboards",
        headers={**headers, "Content-Type": "application/json"},
        json=dash_md,
        timeout=60,
    )
    if pr.status_code in (200, 201):
        did = pr.json().get("id") or pr.json().get("dashboardMetadata", {}).get("id")
        print(f"\n✓ Renewals Dashboard created: {did}")
        print(f"  {instance}/lightning/r/Dashboard/{did}/view")
        return 0
    print(f"\n✗ Dashboard creation failed: {pr.status_code}")
    print(pr.text[:600])
    return 1


if __name__ == "__main__":
    sys.exit(main())
