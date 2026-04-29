"""Phase 14b — Win/Loss Analysis Dashboard.

Surfaces Reason_Won_Lost__c (real data: 5,431 Won, 1,302 buying-stopped, etc.)
and Lost_to_Competitor__c (Account-lookup, ~28K NULL but 1,107 top competitor).

Reports + Dashboard creation in one shot. Dashboard lands in Andre folder.
"""

from __future__ import annotations

import logging
import sys

import requests

from scripts.sf_audit.improve_dashboard_layout import pack_layout, widget_size
from scripts.sf_audit.kpi_reports import POLLUTION_FILTERS
from scripts.sf_audit.rebuild_sd_dashboard import STANDARD_FILTER_COLS
from scripts.sf_audit.reports import _filter, create_report, sf_session

DASHBOARD_FOLDER_ID = "00lTb000006OCRBIA4"
ARR = "Opportunity.APTS_Opportunity_ARR__c.CONVERT"
sARR = f"s!{ARR}"


def reports_spec(folder_id: str | None) -> list[dict]:
    base = {"folderId": folder_id} if folder_id else {}
    return [
        {
            "key": "wl-wins-by-reason",
            "metadata": {
                **base,
                "name": "WL · Wins by Reason (TTM L+E)",
                "description": "Closed-Won L+E in last 12 months grouped by Reason_Won_Lost__c.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", ARR],
                "groupingsDown": [
                    {
                        "name": "Opportunity.Reason_Won_Lost__c",
                        "sortOrder": "Desc",
                        "sortAggregate": sARR,
                        "dateGranularity": "None",
                    }
                ],
                "aggregates": [sARR, "RowCount"],
                "standardDateFilter": {"column": "CLOSE_DATE", "durationValue": "LAST_FISCAL_YEAR"},
                "reportFilters": [
                    _filter("WON", "equals", "1"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        {
            "key": "wl-losses-by-reason",
            "metadata": {
                **base,
                "name": "WL · Losses by Reason (TTM L+E)",
                "description": "Closed-Lost L+E in last 12 months grouped by Reason_Won_Lost__c.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", ARR],
                "groupingsDown": [
                    {
                        "name": "Opportunity.Reason_Won_Lost__c",
                        "sortOrder": "Desc",
                        "sortAggregate": sARR,
                        "dateGranularity": "None",
                    }
                ],
                "aggregates": [sARR, "RowCount"],
                "standardDateFilter": {"column": "CLOSE_DATE", "durationValue": "LAST_FISCAL_YEAR"},
                "reportFilters": [
                    _filter("CLOSED", "equals", "1"),
                    _filter("WON", "equals", "0"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        {
            "key": "wl-losses-by-competitor",
            "metadata": {
                **base,
                "name": "WL · Losses by Competitor",
                "description": "Closed-Lost grouped by competitor account (Lost_to_Competitor__c).",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", ARR],
                "groupingsDown": [
                    {
                        "name": "Opportunity.Lost_to_Competitor__c",
                        "sortOrder": "Desc",
                        "sortAggregate": sARR,
                        "dateGranularity": "None",
                    }
                ],
                "aggregates": [sARR, "RowCount"],
                "standardDateFilter": {"column": "CLOSE_DATE", "durationValue": "LAST_FISCAL_YEAR"},
                "reportFilters": [
                    _filter("CLOSED", "equals", "1"),
                    _filter("WON", "equals", "0"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        {
            "key": "wl-loss-stage",
            "metadata": {
                **base,
                "name": "WL · Stage at Loss (TTM)",
                "description": "Where deals are lost — Closed-Lost grouped by StageName at close.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", ARR],
                "groupingsDown": [
                    {"name": "STAGE_NAME", "sortOrder": "Asc", "dateGranularity": "None"}
                ],
                "aggregates": [sARR, "RowCount"],
                "standardDateFilter": {"column": "CLOSE_DATE", "durationValue": "LAST_FISCAL_YEAR"},
                "reportFilters": [
                    _filter("CLOSED", "equals", "1"),
                    _filter("WON", "equals", "0"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        {
            "key": "wl-deal-size",
            "metadata": {
                **base,
                "name": "WL · Avg Deal Size W vs L (TTM)",
                "description": "Average L+E deal size in last fiscal year, grouped by IsWon.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", ARR],
                "groupingsDown": [{"name": "WON", "sortOrder": "Desc", "dateGranularity": "None"}],
                "aggregates": [sARR, f"a!{ARR}", "RowCount"],
                "standardDateFilter": {"column": "CLOSE_DATE", "durationValue": "LAST_FISCAL_YEAR"},
                "reportFilters": [
                    _filter("CLOSED", "equals", "1"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
        {
            "key": "wl-trend",
            "metadata": {
                **base,
                "name": "WL · Win Rate Trend by FQ (TTM)",
                "description": "Closed L+E grouped by fiscal quarter, IsWon split. Win-rate trend.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", ARR],
                "groupingsDown": [
                    {"name": "CLOSE_DATE", "sortOrder": "Asc", "dateGranularity": "fiscalQuarter"},
                    {"name": "WON", "sortOrder": "Desc", "dateGranularity": "None"},
                ],
                "aggregates": [sARR, "RowCount"],
                "standardDateFilter": {"column": "CLOSE_DATE", "durationValue": "LAST_FISCAL_YEAR"},
                "reportFilters": [
                    _filter("CLOSED", "equals", "1"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    *POLLUTION_FILTERS,
                ],
            },
        },
    ]


def widget(rid, header, title, viz, grouping, agg, granularity="None"):
    return {
        "header": header,
        "footer": None,
        "title": title,
        "reportId": rid,
        "type": "Report",
        "componentData": 0,
        "chartTheme": None,
        "properties": {
            "aggregates": [{"name": agg}],
            "autoSelectColumns": False,
            "drillUrl": None,
            "filterColumns": list(STANDARD_FILTER_COLS),
            "groupings": [
                {
                    "inheritedReportSort": None,
                    "name": grouping,
                    "sortAggregate": None,
                    "sortOrder": "Desc",
                    "dateGranularity": granularity,
                }
            ],
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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    instance, token, _ = sf_session()
    headers = {"Authorization": f"Bearer {token}"}

    rids = {}
    for r in reports_spec(None):  # personal folder
        result = create_report(instance, token, r["metadata"])
        if result.get("ok"):
            rids[r["key"]] = result["id"]
            print(f"  ✓ {r['key']:25s} → {result['id']}")
        else:
            print(f"  ✗ {r['key']}: {result.get('error', '')[:200]}")

    components = []
    if "wl-wins-by-reason" in rids:
        components.append(
            widget(
                rids["wl-wins-by-reason"],
                "Wins by Reason",
                "Last FY (L+E)",
                "Bar",
                "Opportunity.Reason_Won_Lost__c",
                sARR,
            )
        )
    if "wl-losses-by-reason" in rids:
        components.append(
            widget(
                rids["wl-losses-by-reason"],
                "Losses by Reason",
                "Last FY (L+E)",
                "Bar",
                "Opportunity.Reason_Won_Lost__c",
                sARR,
            )
        )
    if "wl-losses-by-competitor" in rids:
        components.append(
            widget(
                rids["wl-losses-by-competitor"],
                "Losses by Competitor",
                "Last FY (L+E)",
                "Bar",
                "Opportunity.Lost_to_Competitor__c",
                sARR,
            )
        )
    if "wl-loss-stage" in rids:
        components.append(
            widget(
                rids["wl-loss-stage"],
                "Stage at Loss",
                "Last FY (L+E)",
                "Funnel",
                "STAGE_NAME",
                sARR,
            )
        )
    if "wl-deal-size" in rids:
        components.append(
            widget(rids["wl-deal-size"], "Won vs Lost ARR Avg", "Last FY (L+E)", "Bar", "WON", sARR)
        )
    if "wl-trend" in rids:
        components.append(
            widget(
                rids["wl-trend"],
                "Win Rate Trend by FQ",
                "Last FY (L+E)",
                "Column",
                "CLOSE_DATE",
                sARR,
                "fiscalQuarter",
            )
        )

    sizes = [
        widget_size(
            (c.get("properties") or {}).get("visualizationType") or "",
            (c.get("properties") or {}).get("reportFormat") or "",
        )
        for c in components
    ]
    layout = pack_layout(sizes)

    dash_md = {
        "name": "Win/Loss Analysis",
        "description": "L+E win and loss patterns by reason, competitor, stage. Built 2026-04-28.",
        "components": components,
        "layout": {"components": layout, "gridLayout": None},
        "filters": [],
        "dashboardType": "SpecifiedUser",
        "runningUser": None,
        "colorPalette": "wildflowers",
        "folderId": DASHBOARD_FOLDER_ID,
    }
    pr = requests.post(
        f"{instance}/services/data/v65.0/analytics/dashboards",
        headers={**headers, "Content-Type": "application/json"},
        json=dash_md,
        timeout=60,
    )
    if pr.status_code in (200, 201):
        did = pr.json().get("id") or pr.json().get("dashboardMetadata", {}).get("id")
        print(f"\n✓ Win/Loss Dashboard: {did}")
        print(f"  {instance}/lightning/r/Dashboard/{did}/view")
        return 0
    print(f"\n✗ {pr.status_code}: {pr.text[:600]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
