#!/usr/bin/env python3
"""
Sales Ops — Commercial Health & Governance — Lightning dashboard deployer.

Mirrors the daily cockpit PDF (alerts + concentration + KPI strip) as a live
Salesforce Lightning Gen-2 dashboard.

Deploy mechanism: **Analytics REST API** (`POST /services/data/v66.0/folders`,
`POST /analytics/reports`, `POST /analytics/dashboards`) — same fall-back path
used by `~/code/apps/salesforce-api/deploy_coo_dashboard.py` when the user
lacks Modify-All-Data / Modify-Metadata. Andre's `apro@simcorp.com` user does
NOT have Metadata API permissions, so the Metadata-deploy path always 403s;
the Analytics REST API works with standard Create-Reports / Create-Dashboards
permissions.

Hard rules (from project memory):
- ARR (`APTS_Opportunity_ARR__c`) for Land+Expand. ACV (`APTS_Renewal_ACV__c`)
  for Renewals. Never blend.
- Lightning Dashboard widget cap: 20. We ship 16.
- Test-artifact exclusion (mirrors scripts/_filters.py) is applied as Report
  criteria on every report.

Usage:
    python deploy_cockpit_dashboard.py                 # create folder + reports + dashboard
    python deploy_cockpit_dashboard.py --dry-run       # don't hit the API; just validate request bodies
    python deploy_cockpit_dashboard.py --rebuild       # delete & recreate existing reports/dashboard
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

# ── Config ─────────────────────────────────────────────────────────────────

TARGET_ORG = "apro@simcorp.com"
API_VERSION = "66.0"

FOLDER_NAME = "Sales_Ops_Commercial_Health"
FOLDER_LABEL = "Sales Ops Commercial Health"
DASHBOARD_DEV_NAME = "SalesOps_Cockpit_Dashboard"
DASHBOARD_TITLE = "Sales Ops — Commercial Health & Governance"

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR / "_sfdx"
FORCE_APP = PROJECT_DIR / "force-app" / "main" / "default"
REPORTS_DIR = FORCE_APP / "reports" / FOLDER_NAME
DASHBOARDS_DIR = FORCE_APP / "dashboards" / FOLDER_NAME

XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n'
META_NS = "http://soap.sforce.com/2006/04/metadata"

LATE_STAGES = ["3 - Engagement", "4 - Shortlisted", "5 - Preferred", "6 - Contracting"]
LATE_STAGES_5_6 = ["5 - Preferred", "6 - Contracting"]


# ── Test-artifact exclusion (mirrors scripts/_filters.py) ──────────────────
# Each tuple: (column, operator, value)
# Test-artifact exclusion. FULL_NAME (Owner.Name) is intentionally OMITTED
# because FlexTable widgets fail dashboard "viewing as" validation when a
# Filter column references User.Name (field-level-security constraint in
# SimCorp's preprod). The Maria Sabiniewicz test-bot owner is also caught
# by the Account/Opportunity name patterns (her test fixtures live on
# `CLM_SimCorp QtC` accounts, which we already exclude).
EXCLUDE_CRITERIA: list[tuple[str, str, str]] = [
    ("ACCOUNT_NAME", "notContain", "CLM_SimCorp QtC"),
    ("ACCOUNT_NAME", "notStartWith", "QtC "),
    ("OPPORTUNITY_NAME", "notStartWith", "TEST "),
    ("OPPORTUNITY_NAME", "notStartWith", "test_"),
    ("OPPORTUNITY_NAME", "notStartWith", "TEST_"),
    ("OPPORTUNITY_NAME", "notStartWith", "QTC_Test"),
    ("OPPORTUNITY_NAME", "notStartWith", "ASH Dummy"),
    ("OPPORTUNITY_NAME", "notStartWith", "SBL Opp"),
    ("OPPORTUNITY_NAME", "notContain", "To Be Deleted"),
    ("OPPORTUNITY_NAME", "notStartWith", "Generic qoute"),
    ("OPPORTUNITY_NAME", "notStartWith", "Generic Quote"),
]


# ── XML helpers ────────────────────────────────────────────────────────────


def _t(name: str, value: str, indent: int = 1) -> str:
    pad = "    " * indent
    return f"{pad}<{name}>{value}</{name}>"


def _wrap(name: str, children: str, indent: int = 1) -> str:
    pad = "    " * indent
    return f"{pad}<{name}>\n{children}\n{pad}</{name}>"


def _xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _criteria_item(field: str, op: str, value: str, n: int) -> str:
    inner = _t("column", field, 3)
    inner += "\n" + _t("filterNumber", str(n), 3)
    inner += "\n" + _t("isRunPageEditable", "true", 3)
    inner += "\n" + _t("operator", op, 3)
    if value != "":
        inner += "\n" + _t("value", _xml_escape(value), 3)
    return _wrap("criteriaItems", inner, 2)


# ── Report definitions ─────────────────────────────────────────────────────


def _exclude_criteria_items(start: int) -> tuple[list[str], int]:
    items = [_criteria_item(f, op, v, start + i) for i, (f, op, v) in enumerate(EXCLUDE_CRITERIA)]
    return items, start + len(EXCLUDE_CRITERIA)


def _build_report_xml(rpt: dict[str, Any]) -> str:
    lines = [XML_HEADER, f'<Report xmlns="{META_NS}">']
    lines.append(_t("name", _xml_escape(rpt["label"])))
    lines.append(_t("description", _xml_escape(rpt["description"])))
    lines.append(_t("reportType", rpt["reportType"]))
    lines.append(_t("format", rpt["format"]))
    lines.append(_t("scope", "organization"))
    lines.append(_t("showDetails", "true" if rpt["format"] == "TABULAR" else "false"))
    lines.append(_t("currency", "USD"))

    for col in rpt.get("columns", []):
        lines.append(_wrap("columns", _t("field", col, 2), 1))

    for g in rpt.get("groupingsDown", []):
        inner = _t("field", g["field"], 2)
        inner += "\n" + _t("sortOrder", g.get("sortOrder", "Asc"), 2)
        if g.get("dateGranularity"):
            inner += "\n" + _t("dateGranularity", g["dateGranularity"], 2)
        lines.append(_wrap("groupingsDown", inner, 1))

    for g in rpt.get("groupingsAcross", []):
        inner = _t("field", g["field"], 2)
        inner += "\n" + _t("sortOrder", g.get("sortOrder", "Asc"), 2)
        if g.get("dateGranularity"):
            inner += "\n" + _t("dateGranularity", g["dateGranularity"], 2)
        lines.append(_wrap("groupingsAcross", inner, 1))

    for a in rpt.get("aggregates", []):
        inner = _t("field", a["field"], 2)
        inner += "\n" + _t("aggregate", a.get("type", "Sum"), 2)
        inner += "\n" + _t("acrossGroupingContext", "GRAND_SUMMARY", 2)
        inner += "\n" + _t("downGroupingContext", "GRAND_SUMMARY", 2)
        lines.append(_wrap("aggregates", inner, 1))

    # User filters (start at 1), then test-artifact exclusion
    user_filters = rpt.get("filters", [])
    n = 1
    for f in user_filters:
        lines.append(_criteria_item(f["field"], f["operation"], f.get("value", ""), n))
        n += 1
    excl_items, _ = _exclude_criteria_items(n)
    lines.extend(excl_items)

    tf = rpt.get("timeFrame")
    if tf:
        inner = _t("dateColumn", tf.get("dateColumn", "CLOSE_DATE"), 2)
        inner += "\n" + _t("interval", tf.get("interval", "CURRENT_FY"), 2)
        if tf.get("interval") == "CUSTOM":
            if tf.get("startDate"):
                inner += "\n" + _t("startDate", tf["startDate"], 2)
            if tf.get("endDate"):
                inner += "\n" + _t("endDate", tf["endDate"], 2)
        lines.append(_wrap("timeFrameFilter", inner, 1))

    if rpt.get("chartType"):
        chart_inner = []
        chart_inner.append(_t("chartType", rpt["chartType"], 2))
        chart_inner.append(_t("enableHoverLabels", "true", 2))
        chart_inner.append(_t("expandOthers", "false", 2))
        chart_inner.append(_t("showAxisLabels", "true", 2))
        chart_inner.append(_t("showPercentage", "false", 2))
        chart_inner.append(_t("showTotal", "true", 2))
        chart_inner.append(_t("showValues", "true", 2))
        chart_inner.append(_t("legendPosition", "Bottom", 2))
        chart_inner.append(_t("location", "CHART_BOTTOM", 2))
        chart_inner.append(_t("size", "Medium", 2))
        if rpt.get("chartGroupings"):
            chart_inner.append(_t("groupingColumn", rpt["chartGroupings"][0], 2))
        for s in rpt.get("chartSummaries", []):
            s_inner = _t("column", s["column"], 3)
            if "aggregate" in s:
                s_inner += "\n" + _t("aggregate", s["aggregate"], 3)
            chart_inner.append(_wrap("chartSummaries", s_inner, 2))
        lines.append(_wrap("chart", "\n".join(chart_inner), 1))

    lines.append("</Report>")
    return "\n".join(lines)


def get_report_definitions() -> list[dict[str, Any]]:
    """16 reports, one per dashboard widget."""

    base_cols = [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "STAGE_NAME",
        "APTS_Opportunity_ARR__c",
        "CLOSE_DATE",
    ]

    reports: list[dict[str, Any]] = []

    # 1. Total open Land+Expand pipeline ARR — FY26
    reports.append(
        {
            "devName": "SalesOps_Cockpit_Open_Pipeline_ARR_FY",
            "label": "Open Pipeline ARR (Land+Expand, FY)",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "KPI: Total open new-business ARR across the current fiscal year (Land+Expand only).",
            "columns": base_cols,
            "groupingsDown": [{"field": "STAGE_NAME"}],
            "aggregates": [
                {"field": "APTS_Opportunity_ARR__c", "type": "Sum"},
                {"field": "RowCount", "type": "RowCount"},
            ],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
                {"field": "TYPE", "operation": "equals", "value": "Land,Expand"},
            ],
            "timeFrame": {"dateColumn": "CLOSE_DATE", "interval": "CURRENT_FY"},
            "chartType": "HorizontalBar",
            "chartGroupings": ["STAGE_NAME"],
            "chartSummaries": [{"column": "APTS_Opportunity_ARR__c", "aggregate": "Sum"}],
        }
    )

    # 2. Commit forecast this quarter (Stage 5+6)
    reports.append(
        {
            "devName": "SalesOps_Cockpit_Commit_Forecast_CFQ",
            "label": "Commit Forecast — Stage 5+6 ARR (CFQ)",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "KPI: Land+Expand ARR at Stage 5 (Preferred) or 6 (Contracting), CloseDate this fiscal quarter.",
            "columns": base_cols,
            "groupingsDown": [{"field": "STAGE_NAME"}],
            "aggregates": [
                {"field": "APTS_Opportunity_ARR__c", "type": "Sum"},
                {"field": "RowCount", "type": "RowCount"},
            ],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
                {"field": "TYPE", "operation": "equals", "value": "Land,Expand"},
                {"field": "STAGE_NAME", "operation": "equals", "value": ",".join(LATE_STAGES_5_6)},
            ],
            "timeFrame": {"dateColumn": "CLOSE_DATE", "interval": "CURRENT_QUARTER"},
            "chartType": "HorizontalBar",
            "chartGroupings": ["STAGE_NAME"],
            "chartSummaries": [{"column": "APTS_Opportunity_ARR__c", "aggregate": "Sum"}],
        }
    )

    # 3. Open opps count
    reports.append(
        {
            "devName": "SalesOps_Cockpit_Open_Opps_Count",
            "label": "Open Opps Count (Land+Expand, FY)",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "KPI: Count of open Land+Expand opportunities with CloseDate in the current fiscal year.",
            "columns": base_cols,
            "groupingsDown": [{"field": "TYPE"}],
            "aggregates": [{"field": "RowCount", "type": "RowCount"}],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
                {"field": "TYPE", "operation": "equals", "value": "Land,Expand"},
            ],
            "timeFrame": {"dateColumn": "CLOSE_DATE", "interval": "CURRENT_FY"},
            "chartType": "HorizontalBar",
            "chartGroupings": ["TYPE"],
            "chartSummaries": [{"column": "RowCount"}],
        }
    )

    # 4. Renewal ACV — current quarter
    reports.append(
        {
            "devName": "SalesOps_Cockpit_Renewal_ACV_CFQ",
            "label": "Renewal ACV — Current Quarter",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "KPI: Open Renewal ACV closing this fiscal quarter. Uses APTS_Renewal_ACV__c (NOT blended with ARR).",
            "columns": [
                "ACCOUNT_NAME",
                "OPPORTUNITY_NAME",
                "STAGE_NAME",
                "APTS_Renewal_ACV__c",
                "CLOSE_DATE",
            ],
            "groupingsDown": [{"field": "STAGE_NAME"}],
            "aggregates": [
                {"field": "APTS_Renewal_ACV__c", "type": "Sum"},
                {"field": "RowCount", "type": "RowCount"},
            ],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
                {"field": "TYPE", "operation": "equals", "value": "Renewal"},
            ],
            "timeFrame": {"dateColumn": "CLOSE_DATE", "interval": "CURRENT_QUARTER"},
            "chartType": "HorizontalBar",
            "chartGroupings": ["STAGE_NAME"],
            "chartSummaries": [{"column": "APTS_Renewal_ACV__c", "aggregate": "Sum"}],
        }
    )

    # 5. Critical-alert ARR concentration — Stage 3+ ≥$500k no Commercial Approval
    reports.append(
        {
            "devName": "SalesOps_Cockpit_Critical_NoCommApproval_500k",
            "label": "Stage 3+ ≥$500k no Commercial Approval",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "Top critical alert: Land+Expand at Stage 3+ with ARR ≥$500k missing Commercial Approval (Stage_20_Approval__c=False).",
            "columns": base_cols,
            "groupingsDown": [{"field": "STAGE_NAME"}],
            "aggregates": [
                {"field": "APTS_Opportunity_ARR__c", "type": "Sum"},
                {"field": "RowCount", "type": "RowCount"},
            ],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
                {"field": "TYPE", "operation": "equals", "value": "Land,Expand"},
                {"field": "STAGE_NAME", "operation": "equals", "value": ",".join(LATE_STAGES)},
                {
                    "field": "APTS_Opportunity_ARR__c",
                    "operation": "greaterOrEqual",
                    "value": "500000",
                },
                {"field": "Stage_20_Approval__c", "operation": "equals", "value": "False"},
            ],
            "chartType": "HorizontalBar",
            "chartGroupings": ["STAGE_NAME"],
            "chartSummaries": [{"column": "APTS_Opportunity_ARR__c", "aggregate": "Sum"}],
        }
    )

    # 6. Top open Land+Expand accounts (SUMMARY+Bar — FlexTable widget is
    #    blocked in this org by a "viewing as" field-access restriction).
    reports.append(
        {
            "devName": "SalesOps_Cockpit_Top_Open_Accounts",
            "label": "Top Open Accounts by Land+Expand ARR",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "Top accounts by open Land+Expand ARR.",
            "columns": base_cols,
            "groupingsDown": [{"field": "ACCOUNT_NAME"}],
            "aggregates": [
                {"field": "APTS_Opportunity_ARR__c", "type": "Sum"},
                {"field": "RowCount", "type": "RowCount"},
            ],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
                {"field": "TYPE", "operation": "equals", "value": "Land,Expand"},
            ],
            "timeFrame": {"dateColumn": "CLOSE_DATE", "interval": "CURRENT_FY"},
            "chartType": "HorizontalBar",
            "chartGroupings": ["ACCOUNT_NAME"],
            "chartSummaries": [{"column": "APTS_Opportunity_ARR__c", "aggregate": "Sum"}],
        }
    )

    # 7. Pipeline by Stage (Bar, ARR)
    reports.append(
        {
            "devName": "SalesOps_Cockpit_Pipeline_by_Stage",
            "label": "Pipeline by Stage — Land+Expand ARR",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "Open Land+Expand ARR grouped by stage (StageName).",
            "columns": base_cols,
            "groupingsDown": [{"field": "STAGE_NAME"}],
            "aggregates": [
                {"field": "APTS_Opportunity_ARR__c", "type": "Sum"},
                {"field": "RowCount", "type": "RowCount"},
            ],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
                {"field": "TYPE", "operation": "equals", "value": "Land,Expand"},
            ],
            "timeFrame": {"dateColumn": "CLOSE_DATE", "interval": "CURRENT_FY"},
            "chartType": "HorizontalBar",
            "chartGroupings": ["STAGE_NAME"],
            "chartSummaries": [{"column": "APTS_Opportunity_ARR__c", "aggregate": "Sum"}],
        }
    )

    # 8. Renewal ACV by quarter
    reports.append(
        {
            "devName": "SalesOps_Cockpit_Renewal_ACV_by_Quarter",
            "label": "Renewal ACV by Fiscal Quarter",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "Open Renewal ACV grouped by close fiscal quarter.",
            "columns": [
                "ACCOUNT_NAME",
                "OPPORTUNITY_NAME",
                "STAGE_NAME",
                "APTS_Renewal_ACV__c",
                "CLOSE_DATE",
            ],
            "groupingsDown": [{"field": "FISCAL_QUARTER"}],
            "aggregates": [
                {"field": "APTS_Renewal_ACV__c", "type": "Sum"},
                {"field": "RowCount", "type": "RowCount"},
            ],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
                {"field": "TYPE", "operation": "equals", "value": "Renewal"},
            ],
            "timeFrame": {"dateColumn": "CLOSE_DATE", "interval": "CURRENT_FY"},
            "chartType": "HorizontalBar",
            "chartGroupings": ["FISCAL_QUARTER"],
            "chartSummaries": [{"column": "APTS_Renewal_ACV__c", "aggregate": "Sum"}],
        }
    )

    # 9. Open ARR by Type (Land vs Expand) — Renewals get a separate ACV widget
    reports.append(
        {
            "devName": "SalesOps_Cockpit_ARR_by_Type",
            "label": "Open ARR by Type — Land vs Expand",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "Open Land+Expand ARR split by deal type. Renewal ACV is shown in a separate widget per ARR/ACV split rule.",
            "columns": base_cols,
            "groupingsDown": [{"field": "TYPE"}],
            "aggregates": [
                {"field": "APTS_Opportunity_ARR__c", "type": "Sum"},
                {"field": "RowCount", "type": "RowCount"},
            ],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
                {"field": "TYPE", "operation": "equals", "value": "Land,Expand"},
            ],
            "timeFrame": {"dateColumn": "CLOSE_DATE", "interval": "CURRENT_FY"},
            "chartType": "HorizontalBar",
            "chartGroupings": ["TYPE"],
            "chartSummaries": [{"column": "APTS_Opportunity_ARR__c", "aggregate": "Sum"}],
        }
    )

    # 10. Land Stage 3+ no Commercial Approval (count + ARR)
    reports.append(
        {
            "devName": "SalesOps_Cockpit_Alert_Land_NoCommApproval",
            "label": "Land Stage 3+ no Commercial Approval",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "Critical alert: Land deals at Stage 3+ missing Commercial Approval. Per the SimCorp Commercial Handbook, ALL Land deals require Commercial Approval before Stage 3.",
            "columns": base_cols,
            "groupingsDown": [{"field": "STAGE_NAME"}],
            "aggregates": [
                {"field": "APTS_Opportunity_ARR__c", "type": "Sum"},
                {"field": "RowCount", "type": "RowCount"},
            ],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
                {"field": "TYPE", "operation": "equals", "value": "Land"},
                {"field": "STAGE_NAME", "operation": "equals", "value": ",".join(LATE_STAGES)},
                {"field": "Stage_20_Approval__c", "operation": "equals", "value": "False"},
            ],
            "chartType": "HorizontalBar",
            "chartGroupings": ["STAGE_NAME"],
            "chartSummaries": [{"column": "APTS_Opportunity_ARR__c", "aggregate": "Sum"}],
        }
    )

    # 11. Stage 5+ Land/Expand without KYC clearance
    reports.append(
        {
            "devName": "SalesOps_Cockpit_Alert_KYC_Gap",
            "label": "Alert: Stage 5+ Land/Expand without KYC",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "Critical alert: Land/Expand at Stage 5+ (Preferred or Contracting) without KYC clearance. KYC is a closing-stage gate.",
            "columns": base_cols,
            "groupingsDown": [{"field": "STAGE_NAME"}],
            "aggregates": [
                {"field": "APTS_Opportunity_ARR__c", "type": "Sum"},
                {"field": "RowCount", "type": "RowCount"},
            ],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
                {"field": "TYPE", "operation": "equals", "value": "Land,Expand"},
                {"field": "STAGE_NAME", "operation": "equals", "value": ",".join(LATE_STAGES_5_6)},
                {"field": "KYC_Approval_Message__c", "operation": "equals", "value": "False"},
            ],
            "chartType": "HorizontalBar",
            "chartGroupings": ["STAGE_NAME"],
            "chartSummaries": [{"column": "APTS_Opportunity_ARR__c", "aggregate": "Sum"}],
        }
    )

    # 12. Open opps with CloseDate in past
    reports.append(
        {
            "devName": "SalesOps_Cockpit_Alert_Past_CloseDate",
            "label": "Alert: Open Opps with Past CloseDate",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "Critical alert: Open opps with CloseDate before today — distorts every pipeline view.",
            "columns": base_cols,
            "groupingsDown": [{"field": "STAGE_NAME"}],
            "aggregates": [
                {"field": "APTS_Opportunity_ARR__c", "type": "Sum"},
                {"field": "RowCount", "type": "RowCount"},
            ],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
            ],
            "timeFrame": {
                "dateColumn": "CLOSE_DATE",
                "interval": "CUSTOM",
                "startDate": "2000-01-01",
                "endDate": "2026-04-27",
            },
            "chartType": "HorizontalBar",
            "chartGroupings": ["STAGE_NAME"],
            "chartSummaries": [{"column": "APTS_Opportunity_ARR__c", "aggregate": "Sum"}],
        }
    )

    # 13. Stage 3+ Dec 31 placeholder dates (CloseDate = current calendar 12/31)
    reports.append(
        {
            "devName": "SalesOps_Cockpit_Alert_Dec31_Placeholder",
            "label": "Alert: Stage 3+ Dec 31 Placeholder Dates",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "Important alert: Stage 3+ open opps with Dec 31 close dates (placeholders that inflate Q4 forecast).",
            "columns": base_cols,
            "groupingsDown": [{"field": "STAGE_NAME"}],
            "aggregates": [
                {"field": "APTS_Opportunity_ARR__c", "type": "Sum"},
                {"field": "RowCount", "type": "RowCount"},
            ],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
                {"field": "STAGE_NAME", "operation": "equals", "value": ",".join(LATE_STAGES)},
            ],
            "timeFrame": {
                "dateColumn": "CLOSE_DATE",
                "interval": "CUSTOM",
                "startDate": "2026-12-31",
                "endDate": "2026-12-31",
            },
            "chartType": "HorizontalBar",
            "chartGroupings": ["STAGE_NAME"],
            "chartSummaries": [{"column": "APTS_Opportunity_ARR__c", "aggregate": "Sum"}],
        }
    )

    # 14. Stage 3+ no activity 60d+
    reports.append(
        {
            "devName": "SalesOps_Cockpit_Alert_Stale_Activity_60d",
            "label": "Alert: Stage 3+ No Activity 60+ Days",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "Important alert: Stage 3+ open opps with LastActivityDate older than 60 days — stalling deals.",
            "columns": [
                "ACCOUNT_NAME",
                "OPPORTUNITY_NAME",
                "STAGE_NAME",
                "APTS_Opportunity_ARR__c",
                "LAST_ACTIVITY",
                "CLOSE_DATE",
            ],
            "groupingsDown": [{"field": "STAGE_NAME"}],
            "aggregates": [
                {"field": "APTS_Opportunity_ARR__c", "type": "Sum"},
                {"field": "RowCount", "type": "RowCount"},
            ],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
                {"field": "STAGE_NAME", "operation": "equals", "value": ",".join(LATE_STAGES)},
                {"field": "LAST_ACTIVITY", "operation": "lessThan", "value": "LAST_N_DAYS:60"},
            ],
            "chartType": "HorizontalBar",
            "chartGroupings": ["STAGE_NAME"],
            "chartSummaries": [{"column": "APTS_Opportunity_ARR__c", "aggregate": "Sum"}],
        }
    )

    # 15. Owner concentration on flagged ARR — top 10 (Tabular)
    # Approximation: rank by ARR among Stage 3+ Land+Expand missing Commercial Approval
    reports.append(
        {
            "devName": "SalesOps_Cockpit_Owner_Concentration",
            "label": "Owner Concentration — Flagged ARR",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "Top owners by flagged ARR — proxy view of who is sitting on the most governance-debt pipeline.",
            "columns": base_cols,
            "groupingsDown": [{"field": "FULL_NAME"}, {"field": "STAGE_NAME"}],
            "aggregates": [
                {"field": "APTS_Opportunity_ARR__c", "type": "Sum"},
                {"field": "RowCount", "type": "RowCount"},
            ],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
                {"field": "TYPE", "operation": "equals", "value": "Land,Expand"},
                {"field": "STAGE_NAME", "operation": "equals", "value": ",".join(LATE_STAGES)},
                {"field": "Stage_20_Approval__c", "operation": "equals", "value": "False"},
            ],
            "chartType": "HorizontalBar",
            "chartGroupings": ["FULL_NAME"],
            "chartSummaries": [{"column": "APTS_Opportunity_ARR__c", "aggregate": "Sum"}],
        }
    )

    # 16. Account concentration on flagged ARR — top 15
    reports.append(
        {
            "devName": "SalesOps_Cockpit_Account_Concentration",
            "label": "Account Concentration — Flagged ARR",
            "reportType": "Opportunity",
            "format": "SUMMARY",
            "description": "Top accounts by flagged ARR — same predicate as Owner Concentration, pivoted to account.",
            "columns": base_cols,
            "groupingsDown": [{"field": "ACCOUNT_NAME"}],
            "aggregates": [
                {"field": "APTS_Opportunity_ARR__c", "type": "Sum"},
                {"field": "RowCount", "type": "RowCount"},
            ],
            "filters": [
                {"field": "IsClosed", "operation": "equals", "value": "0"},
                {"field": "TYPE", "operation": "equals", "value": "Land,Expand"},
                {"field": "STAGE_NAME", "operation": "equals", "value": ",".join(LATE_STAGES)},
                {"field": "Stage_20_Approval__c", "operation": "equals", "value": "False"},
            ],
            "chartType": "HorizontalBar",
            "chartGroupings": ["ACCOUNT_NAME"],
            "chartSummaries": [{"column": "APTS_Opportunity_ARR__c", "aggregate": "Sum"}],
        }
    )

    return reports


# ── Dashboard XML ──────────────────────────────────────────────────────────


def _component(
    rpt: dict[str, Any],
    col: int,
    row: int,
    col_span: int = 4,
    row_span: int = 4,
    comp_type: str | None = None,
) -> str:
    inner = []
    inner.append(_t("colSpan", str(col_span), 2))
    inner.append(_t("column", str(col), 2))
    inner.append(_t("row", str(row), 2))
    inner.append(_t("rowSpan", str(row_span), 2))

    ct = comp_type or _component_type(rpt)
    comp_inner = []
    comp_inner.append(_t("autoselectColumnsFromReport", "true", 3))
    comp_inner.append(_t("chartAxisRange", "Auto", 3))
    comp_inner.append(_t("componentType", ct, 3))
    comp_inner.append(_t("displayUnits", "Auto", 3))
    comp_inner.append(_t("drillEnabled", "true", 3))
    comp_inner.append(_t("drillToDetailEnabled", "true", 3))
    comp_inner.append(_t("enableHoverLabels", "true", 3))
    comp_inner.append(_t("header", _xml_escape(rpt["label"]), 3))
    comp_inner.append(_t("indicatorBreakpoint1", "33", 3))
    comp_inner.append(_t("indicatorBreakpoint2", "67", 3))
    comp_inner.append(_t("indicatorHighColor", "#54C254", 3))
    comp_inner.append(_t("indicatorLowColor", "#C25454", 3))
    comp_inner.append(_t("indicatorMiddleColor", "#C2C254", 3))
    comp_inner.append(_t("report", f"{FOLDER_NAME}/{rpt['devName']}", 3))
    comp_inner.append(_t("showPercentage", "false", 3))
    comp_inner.append(_t("showPicturesOnCharts", "false", 3))
    comp_inner.append(_t("showPicturesOnTables", "false", 3))
    comp_inner.append(_t("showRange", "true", 3))
    comp_inner.append(_t("showTotal", "true", 3))
    comp_inner.append(_t("showValues", "true", 3))
    comp_inner.append(_t("sortBy", "RowLabelDescending", 3))
    inner.append(_wrap("dashboardComponent", "\n".join(comp_inner), 2))

    return _wrap("dashboardGridComponents", "\n".join(inner), 1)


def _component_type(rpt: dict[str, Any]) -> str:
    if rpt.get("format") == "TABULAR":
        return "Table"
    return "Bar"  # all our charts are HorizontalBar → 'Bar' in dashboard parlance


def _section_header(label: str, row: int) -> str:
    inner = []
    inner.append(_t("column", "0", 2))
    inner.append(_t("columnSpan", "12", 2))
    inner.append(_t("isRichText", "true", 2))
    inner.append(_t("row", str(row), 2))
    inner.append(_t("rowSpan", "1", 2))
    inner.append(_t("value", f"&lt;b&gt;{_xml_escape(label)}&lt;/b&gt;", 2))
    return _wrap("dashboardTextComponents", "\n".join(inner), 1)


# Layout: 16 widgets, 4 per row, 4 sections, 12-col grid, colSpan=3.
LAYOUT_SECTIONS = [
    {
        "label": "KPI Strip",
        "reports": [
            "SalesOps_Cockpit_Open_Pipeline_ARR_FY",
            "SalesOps_Cockpit_Commit_Forecast_CFQ",
            "SalesOps_Cockpit_Open_Opps_Count",
            "SalesOps_Cockpit_Renewal_ACV_CFQ",
        ],
    },
    {
        "label": "Pipeline Detail",
        "reports": [
            "SalesOps_Cockpit_Top_Open_Accounts",
            "SalesOps_Cockpit_Pipeline_by_Stage",
            "SalesOps_Cockpit_Renewal_ACV_by_Quarter",
            "SalesOps_Cockpit_ARR_by_Type",
        ],
    },
    {
        "label": "Critical Alerts",
        "reports": [
            "SalesOps_Cockpit_Critical_NoCommApproval_500k",
            "SalesOps_Cockpit_Alert_Land_NoCommApproval",
            "SalesOps_Cockpit_Alert_KYC_Gap",
            "SalesOps_Cockpit_Alert_Past_CloseDate",
        ],
    },
    {
        "label": "Hygiene & Concentration",
        "reports": [
            "SalesOps_Cockpit_Alert_Dec31_Placeholder",
            "SalesOps_Cockpit_Alert_Stale_Activity_60d",
            "SalesOps_Cockpit_Owner_Concentration",
            "SalesOps_Cockpit_Account_Concentration",
        ],
    },
]


def generate_dashboard_xml(reports: list[dict[str, Any]]) -> str:
    report_map = {r["devName"]: r for r in reports}
    lines = [XML_HEADER, f'<Dashboard xmlns="{META_NS}">']
    lines.append(_t("backgroundEndColor", "#FFFFFF"))
    lines.append(_t("backgroundFadeDirection", "Diagonal"))
    lines.append(_t("backgroundStartColor", "#FFFFFF"))
    lines.append(_t("chartTheme", "light"))
    lines.append(_t("colorPalette", "unity"))
    lines.append(_t("dashboardResultRefreshedDate", "2026-04-28T00:00:00Z"))
    lines.append(_t("dashboardResultRunningUser", TARGET_ORG))
    lines.append(_t("dashboardType", "SpecifiedUser"))
    lines.append(
        _t(
            "description",
            "Live SF cockpit mirror of the daily Sales Ops brief — KPI strip, pipeline detail, alerts, concentration. ARR and ACV reported separately.",
        )
    )
    lines.append(_t("isGridLayout", "true"))
    lines.append(_t("runningUser", TARGET_ORG))
    lines.append(_t("textColor", "#000000"))
    lines.append(_t("title", _xml_escape(DASHBOARD_TITLE)))
    lines.append(_t("titleColor", "#000000"))
    lines.append(_t("titleSize", "12"))

    # Layout
    row = 0
    for section in LAYOUT_SECTIONS:
        lines.append(_section_header(section["label"], row))
        row += 1
        for i, dev in enumerate(section["reports"]):
            rpt = report_map[dev]
            col = (i % 4) * 3
            lines.append(_component(rpt, col=col, row=row, col_span=3, row_span=4))
        row += 4

    lines.append("</Dashboard>")
    return "\n".join(lines)


# ── Folders ────────────────────────────────────────────────────────────────


def report_folder_xml() -> str:
    return f"""{XML_HEADER}<ReportFolder xmlns="{META_NS}">
    <accessType>Hidden</accessType>
    <folderShares>
        <accessLevel>Manage</accessLevel>
        <sharedTo>{TARGET_ORG}</sharedTo>
        <sharedToType>User</sharedToType>
    </folderShares>
    <name>{FOLDER_LABEL}</name>
    <publicFolderAccess>ReadWrite</publicFolderAccess>
</ReportFolder>"""


def dashboard_folder_xml() -> str:
    return f"""{XML_HEADER}<DashboardFolder xmlns="{META_NS}">
    <accessType>Hidden</accessType>
    <folderShares>
        <accessLevel>Manage</accessLevel>
        <sharedTo>{TARGET_ORG}</sharedTo>
        <sharedToType>User</sharedToType>
    </folderShares>
    <name>{FOLDER_LABEL}</name>
</DashboardFolder>"""


def sfdx_project_json() -> str:
    return json.dumps(
        {
            "packageDirectories": [{"path": "force-app", "default": True}],
            "name": "salesops-cockpit",
            "namespace": "",
            "sfdcLoginUrl": "https://login.salesforce.com",
            "sourceApiVersion": API_VERSION,
        },
        indent=2,
    )


def package_xml(reports: list[dict[str, Any]]) -> str:
    members = "\n".join(f"        <members>{FOLDER_NAME}/{r['devName']}</members>" for r in reports)
    return f"""{XML_HEADER}<Package xmlns="{META_NS}">
    <types>
        <name>Report</name>
        <members>{FOLDER_NAME}</members>
{members}
    </types>
    <types>
        <name>Dashboard</name>
        <members>{FOLDER_NAME}</members>
        <members>{FOLDER_NAME}/{DASHBOARD_DEV_NAME}</members>
    </types>
    <version>{API_VERSION}</version>
</Package>"""


# ── Project generation ─────────────────────────────────────────────────────


def generate_project(reports: list[dict[str, Any]]) -> Path:
    print(f"\n[1/3] Generating SFDX metadata in {PROJECT_DIR}")
    if PROJECT_DIR.exists():
        shutil.rmtree(PROJECT_DIR)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)

    (PROJECT_DIR / "sfdx-project.json").write_text(sfdx_project_json())
    (REPORTS_DIR / f"{FOLDER_NAME}.reportFolder-meta.xml").write_text(report_folder_xml())
    (DASHBOARDS_DIR / f"{FOLDER_NAME}.dashboardFolder-meta.xml").write_text(dashboard_folder_xml())

    for r in reports:
        (REPORTS_DIR / f"{r['devName']}.report-meta.xml").write_text(_build_report_xml(r))

    (DASHBOARDS_DIR / f"{DASHBOARD_DEV_NAME}.dashboard-meta.xml").write_text(
        generate_dashboard_xml(reports)
    )

    print(f"  [OK] {len(reports)} reports + 1 dashboard + 2 folders")
    return PROJECT_DIR


def create_zip(reports: list[dict[str, Any]]) -> Path:
    zip_path = SCRIPT_DIR / "cockpit_package.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", package_xml(reports))
        for f in REPORTS_DIR.iterdir():
            if f.suffix == ".xml":
                zf.write(f, f"reports/{FOLDER_NAME}/{f.name}")
        for f in DASHBOARDS_DIR.iterdir():
            if f.suffix == ".xml":
                zf.write(f, f"dashboards/{FOLDER_NAME}/{f.name}")
    print(f"  [OK] ZIP: {zip_path} ({zip_path.stat().st_size:,} bytes)")
    return zip_path


# ── Deploy via Analytics REST API ──────────────────────────────────────────


def get_credentials() -> dict[str, str]:
    p = subprocess.run(
        ["sf", "org", "display", "--json", "--target-org", TARGET_ORG],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        raise RuntimeError(f"sf org display failed:\n{p.stderr}")
    data = json.loads(p.stdout)["result"]
    return {"access_token": data["accessToken"], "instance_url": data["instanceUrl"].rstrip("/")}


# Maps Metadata API filter operations to Analytics REST API operators.
_FILTER_OP_MAP = {
    "equals": "equals",
    "notEqual": "notEqual",
    "lessThan": "lessThan",
    "greaterThan": "greaterThan",
    "lessOrEqual": "lessOrEqual",
    "greaterOrEqual": "greaterOrEqual",
    "contains": "contains",
    "notContain": "notContain",
    "startsWith": "startsWith",
    "notStartWith": "notContain",  # Analytics API has no notStartWith — use notContain (safe over-match for our test patterns)
}

_DATE_INTERVAL_MAP = {
    "CURRENT_FY": "THIS_FISCAL_YEAR",
    "CURRENT_QUARTER": "THIS_FISCAL_QUARTER",
    "CURRENT_FQ": "THIS_FISCAL_QUARTER",
    "CURRENT_CY": "THIS_CALENDAR_YEAR",
    "LAST_30_DAYS": "LAST_30_DAYS",
    "LAST_60_DAYS": "LAST_60_DAYS",
    "LAST_90_DAYS": "LAST_90_DAYS",
    "CUSTOM": "CUSTOM",
}

_AGG_PREFIX = {"Sum": "s", "Average": "a", "Max": "x", "Min": "m"}


def _qualify_field(field: str) -> str:
    """Map our field tokens to Analytics-API column names (Opportunity report type)."""
    if field == "IsClosed":
        return "CLOSED"
    if field == "IsWon":
        return "WON"
    if field == "TYPE":
        return "TYPE"
    if field.endswith("__c") and "." not in field:
        return f"Opportunity.{field}"
    return field


def _convert_value(field: str, _op: str, value: str) -> Any:
    """Coerce a metadata-API filter value into Analytics-API form."""
    if not value:
        return ""
    # Booleans:
    if field in {"IsClosed", "IsWon"}:
        # Metadata API uses "0"/"1"; Analytics API expects "true"/"false"
        return "false" if value in {"0", "False", "false"} else "true"
    # Custom boolean fields:
    if field.endswith("__c") and value in {"True", "False", "true", "false"}:
        return value.lower()
    # Multi-value pick-list (comma-joined values for `equals`)
    return value


def _convert_report_to_analytics_json(rpt: dict[str, Any], folder_id: str) -> dict[str, Any]:
    """Build the Analytics-API request body for POST /analytics/reports."""
    groupings_down = []
    grouping_field_names = set()
    for g in rpt.get("groupingsDown", []):
        qualified = _qualify_field(g["field"])
        grouping_field_names.add(qualified)
        gd: dict[str, Any] = {"name": qualified, "sortOrder": g.get("sortOrder", "Asc")}
        if g.get("dateGranularity"):
            gd["dateGranularity"] = g["dateGranularity"].upper()
        groupings_down.append(gd)

    detail_columns: list[str] = []
    for c in rpt["columns"]:
        q = _qualify_field(c)
        if q not in grouping_field_names:
            detail_columns.append(q)

    aggregates: list[str] = []
    for a in rpt.get("aggregates", []):
        field = a["field"]
        agg_type = a.get("type", "Sum")
        if agg_type == "RowCount" or field == "RowCount":
            aggregates.append("RowCount")
        else:
            q = _qualify_field(field)
            aggregates.append(f"{_AGG_PREFIX.get(agg_type, 's')}!{q}")
            if q not in detail_columns and q not in grouping_field_names:
                detail_columns.append(q)

    # User filters first, then test-artifact exclusion.
    report_filters: list[dict[str, Any]] = []
    for f in rpt.get("filters", []):
        op = f.get("operation", "equals")
        report_filters.append(
            {
                "column": _qualify_field(f["field"]),
                "operator": _FILTER_OP_MAP.get(op, op),
                "value": _convert_value(f["field"], op, f.get("value", "")),
            }
        )
    for field, op, value in EXCLUDE_CRITERIA:
        report_filters.append(
            {
                "column": _qualify_field(field),
                "operator": _FILTER_OP_MAP.get(op, op),
                "value": value,
            }
        )

    # Salesforce auto-injects a CFQ standardDateFilter when none is provided —
    # which silently filters governance alert counts down. Always emit one;
    # use a wide CUSTOM range when the report definition doesn't supply a
    # timeFrame so alerts cover all open pipeline.
    tf = rpt.get("timeFrame") or {
        "dateColumn": "CLOSE_DATE",
        "interval": "CUSTOM",
        "startDate": "2000-01-01",
        "endDate": "2099-12-31",
    }
    date_column = tf.get("dateColumn", "CLOSE_DATE")
    interval = tf.get("interval", "CURRENT_FY")
    duration = _DATE_INTERVAL_MAP.get(interval, "THIS_FISCAL_YEAR")
    standard_date_filter: dict[str, Any] = {"column": date_column, "durationValue": duration}
    if interval == "CUSTOM":
        standard_date_filter["startDate"] = tf.get("startDate", "2000-01-01")
        standard_date_filter["endDate"] = tf.get("endDate", "2099-12-31")

    report_metadata: dict[str, Any] = {
        "name": rpt["label"],
        "description": rpt.get("description", ""),
        "reportFormat": rpt["format"],
        "reportType": {"type": "Opportunity"},
        "detailColumns": detail_columns,
        "groupingsDown": groupings_down,
        "aggregates": aggregates,
        "reportFilters": report_filters,
        "standardDateFilter": standard_date_filter,
        "folderId": folder_id,
        "scope": "organization",
        "developerName": rpt["devName"],
    }

    return {"reportMetadata": report_metadata}


def _convert_dashboard_to_analytics_json(
    reports: list[dict[str, Any]],
    report_id_map: dict[str, str],
    folder_id: str,
) -> dict[str, Any]:
    """Build a POST /analytics/dashboards body. 16 widgets in a 12-column grid.

    Per Salesforce Analytics REST docs (verified against existing BOB
    dashboard 01ZTb00000DoGYLMA3 in this org):
      - `components[]`  → list of report/text widget definitions
      - `layout.gridLayout: true` and `layout.numColumns: 12`
      - `layout.components[]` → one positioning entry per widget, in the
        SAME ORDER as `components[]`. Indices match by position.
    """
    report_map = {r["devName"]: r for r in reports}
    components: list[dict[str, Any]] = []
    layout_components: list[dict[str, Any]] = []
    row_cursor = 0

    for section in LAYOUT_SECTIONS:
        # 4 widgets per row, colSpan=3 in the 12-col grid, rowSpan=4
        # Section label is prefixed onto the first widget's header.
        for i, dev_name in enumerate(section["reports"]):
            rid = report_id_map.get(dev_name)
            rpt = report_map.get(dev_name)
            if not rid or not rpt:
                continue
            col = (i % 4) * 3
            is_table = rpt.get("format") == "TABULAR"
            viz = "FlexTable" if is_table else "Bar"
            properties: dict[str, Any] = {
                "visualizationType": viz,
                "autoSelectColumns": True,
                "useReportChart": False,
            }
            if not is_table and rpt.get("aggregates"):
                a = next(
                    (x for x in rpt["aggregates"] if x.get("type") != "RowCount"),
                    rpt["aggregates"][0],
                )
                if a.get("type") == "RowCount" or a.get("field") == "RowCount":
                    properties["aggregates"] = [{"name": "RowCount"}]
                else:
                    properties["aggregates"] = [
                        {
                            "name": f"{_AGG_PREFIX.get(a.get('type', 'Sum'), 's')}!{_qualify_field(a['field'])}"
                        }
                    ]
                if rpt.get("groupingsDown"):
                    g = rpt["groupingsDown"][0]
                    properties["groupings"] = [
                        {
                            "name": _qualify_field(g["field"]),
                            "sortOrder": g.get("sortOrder", "Asc"),
                        }
                    ]
            header = f"[{section['label']}] {rpt['label']}" if i == 0 else rpt["label"]
            components.append(
                {
                    "type": "Report",
                    "reportId": rid,
                    "header": header,
                    "title": None,
                    "properties": properties,
                }
            )
            layout_components.append({"row": row_cursor, "column": col, "rowspan": 4, "colspan": 3})
        row_cursor += 4

    return {
        "name": DASHBOARD_TITLE,
        "description": "Live SF cockpit mirror of the daily Sales Ops brief — KPI strip, pipeline detail, alerts, concentration. ARR and ACV reported separately.",
        "folderId": folder_id,
        "components": components,
        "layout": {
            "gridLayout": True,
            "numColumns": 12,
            "rowHeight": 36,
            "components": layout_components,
        },
    }


def _api(method: str, path: str, token: str, instance: str, body: dict | None = None) -> dict:
    url = f"{instance}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            txt = resp.read().decode()
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {e.reason} {method} {path}\n{err[:1500]}") from e


def _ensure_folder(token: str, instance: str, folder_type: str) -> str:
    """Create or look up a Reports/Dashboards folder via Analytics API.

    SimCorp's preprod org rejects `developerName` (JSON_PARSER_ERROR) and
    rejects `name` for non-admin users (error 102). Pass only `label` + `type`;
    Salesforce derives `name` from the label.
    """
    api_base = f"/services/data/v{API_VERSION}"
    sf_type = "Report" if folder_type == "report" else "Dashboard"

    # Look up first (idempotent re-deploy)
    p = subprocess.run(
        [
            "sf",
            "data",
            "query",
            "--target-org",
            TARGET_ORG,
            "--query",
            f"SELECT Id FROM Folder WHERE DeveloperName='{FOLDER_NAME}' AND Type='{sf_type}' LIMIT 1",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    recs = json.loads(p.stdout).get("result", {}).get("records", []) if p.returncode == 0 else []
    if recs:
        fid = recs[0]["Id"]
        print(f"  [OK] reusing {folder_type} folder: {fid}")
        return fid

    body = {"label": FOLDER_LABEL, "type": folder_type}
    result = _api("POST", f"{api_base}/folders", token, instance, body=body)
    fid = result.get("id")
    if not fid:
        raise RuntimeError(f"Folder POST returned no id: {result}")
    print(f"  [OK] {folder_type} folder created: {fid}")
    return fid


def _existing_reports_in_folder(_folder_id: str) -> dict[str, str]:
    """Return {label: reportId} for reports already in the folder.

    Salesforce auto-derives DeveloperName from `name`, ignoring any
    `developerName` we pass — and SF appends 1/2/3 suffixes on duplicates.
    Match by `Name` (the label) for idempotent reuse.
    """
    p = subprocess.run(
        [
            "sf",
            "data",
            "query",
            "--target-org",
            TARGET_ORG,
            "--query",
            f"SELECT Id, Name, DeveloperName FROM Report WHERE FolderName='{FOLDER_LABEL}'",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        return {}
    recs = json.loads(p.stdout).get("result", {}).get("records", [])
    out: dict[str, str] = {}
    for r in recs:
        # Prefer first-seen (DeveloperName without numeric suffix means original).
        if r["Name"] not in out:
            out[r["Name"]] = r["Id"]
    return out


def _existing_dashboard_id(folder_id: str) -> str | None:
    p = subprocess.run(
        [
            "sf",
            "data",
            "query",
            "--target-org",
            TARGET_ORG,
            "--query",
            f"SELECT Id, DeveloperName FROM Dashboard WHERE FolderId='{folder_id}' AND DeveloperName='{DASHBOARD_DEV_NAME}' LIMIT 1",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        return None
    recs = json.loads(p.stdout).get("result", {}).get("records", [])
    return recs[0]["Id"] if recs else None


def deploy_via_analytics_api(
    reports: list[dict[str, Any]], rebuild: bool = False
) -> tuple[bool, str | None, dict[str, str]]:
    """Deploy folder + reports + dashboard via the Analytics REST API.

    Returns (success, dashboard_id, report_id_map)."""
    print("\n[1/4] Connecting to Salesforce")
    creds = get_credentials()
    token, instance = creds["access_token"], creds["instance_url"]
    print(f"  [OK] {instance}")

    api_base = f"/services/data/v{API_VERSION}"

    print("\n[2/4] Provisioning folders")
    report_folder_id = _ensure_folder(token, instance, "report")
    dashboard_folder_id = _ensure_folder(token, instance, "dashboard")

    if rebuild:
        print("\n[INFO] --rebuild specified; deleting existing reports + dashboard")
        existing = _existing_reports_in_folder(report_folder_id)
        for dev, rid in existing.items():
            try:
                _api("DELETE", f"{api_base}/analytics/reports/{rid}", token, instance)
                print(f"  [OK] deleted report {dev} ({rid})")
            except RuntimeError as e:
                print(f"  [WARN] could not delete report {dev}: {e}")
        existing_dash = _existing_dashboard_id(dashboard_folder_id)
        if existing_dash:
            try:
                _api("DELETE", f"{api_base}/analytics/dashboards/{existing_dash}", token, instance)
                print(f"  [OK] deleted dashboard {existing_dash}")
            except RuntimeError as e:
                print(f"  [WARN] could not delete dashboard: {e}")

    print(f"\n[3/4] Creating {len(reports)} reports")
    report_id_map: dict[str, str] = {}
    existing = _existing_reports_in_folder(report_folder_id)
    fail_count = 0
    for i, rpt in enumerate(reports, 1):
        dev = rpt["devName"]
        label = rpt["label"]
        if label in existing:
            report_id_map[dev] = existing[label]
            print(f"  [{i:>2}/{len(reports)}] {label[:55]:55s} REUSE  {existing[label]}")
            continue
        body = _convert_report_to_analytics_json(rpt, report_folder_id)
        try:
            res = _api("POST", f"{api_base}/analytics/reports", token, instance, body=body)
            rid = res.get("reportMetadata", {}).get("id") or res.get("id")
            if not rid:
                print(f"  [{i:>2}/{len(reports)}] {label[:55]:55s} FAIL   no id in response")
                fail_count += 1
                continue
            report_id_map[dev] = rid
            print(f"  [{i:>2}/{len(reports)}] {label[:55]:55s} OK     {rid}")
        except RuntimeError as e:
            print(f"  [{i:>2}/{len(reports)}] {label[:55]:55s} FAIL")
            print(f"    {str(e)[:600]}")
            fail_count += 1
    if fail_count:
        print(f"\n  [WARN] {fail_count} report(s) failed; continuing if at least one succeeded")
    if not report_id_map:
        return False, None, {}

    print("\n[4/4] Creating dashboard")
    dash_id = _existing_dashboard_id(dashboard_folder_id)
    body = _convert_dashboard_to_analytics_json(reports, report_id_map, dashboard_folder_id)
    try:
        if dash_id:
            print(f"  [INFO] dashboard exists ({dash_id}) — PATCHing")
            _api("PATCH", f"{api_base}/analytics/dashboards/{dash_id}", token, instance, body=body)
        else:
            res = _api("POST", f"{api_base}/analytics/dashboards", token, instance, body=body)
            dash_id = res.get("id")
            if not dash_id:
                # Look it up
                dash_id = _existing_dashboard_id(dashboard_folder_id)
        print(f"  [OK] dashboard id = {dash_id}")
    except RuntimeError as e:
        print(f"  [FAIL] {e}")
        return False, None, report_id_map

    return True, dash_id, report_id_map


def deploy_zip(zip_path: Path) -> bool:
    print("\n[2/3] Deploying via Metadata REST API")
    creds = get_credentials()
    token, instance = creds["access_token"], creds["instance_url"]

    boundary = "----CockpitMetadataBoundary"
    body = io.BytesIO()
    deploy_options = json.dumps(
        {
            "deployOptions": {
                "allowMissingFiles": False,
                "autoUpdatePackage": False,
                "checkOnly": False,
                "ignoreWarnings": True,
                "performRetrieve": False,
                "purgeOnDelete": False,
                "rollbackOnError": True,
                "runTests": [],
                "singlePackage": True,
                "testLevel": "NoTestRun",
            }
        }
    )
    body.write(f"--{boundary}\r\n".encode())
    body.write(b'Content-Disposition: form-data; name="json"\r\n')
    body.write(b"Content-Type: application/json\r\n\r\n")
    body.write(deploy_options.encode())
    body.write(b"\r\n")
    body.write(f"--{boundary}\r\n".encode())
    body.write(b'Content-Disposition: form-data; name="file"; filename="cockpit_package.zip"\r\n')
    body.write(b"Content-Type: application/zip\r\n\r\n")
    body.write(zip_path.read_bytes())
    body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())

    url = f"{instance}/services/data/v{API_VERSION}/metadata/deployRequest"
    req = urllib.request.Request(
        url,
        data=body.getvalue(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", errors="replace")
        print(f"  [ERROR] HTTP {e.code}: {e.reason}")
        print(f"  Response: {body_txt[:1500]}")
        return False
    deploy_id = data.get("id")
    if not deploy_id:
        print(f"  [ERROR] No deploy ID: {data}")
        return False
    print(f"  [OK] deploy id = {deploy_id}")

    print("\n[3/3] Polling for completion")
    status_url = f"{instance}/services/data/v{API_VERSION}/metadata/deployRequest/{deploy_id}?includeDetails=true"
    final = None
    for attempt in range(1, 61):
        time.sleep(5)
        sreq = urllib.request.Request(
            status_url,
            method="GET",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(sreq, timeout=30) as r:
                sdata = json.loads(r.read().decode())
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARN] poll {attempt}: {exc}")
            continue
        result = sdata.get("deployResult", sdata)
        status = result.get("status", "?")
        done = result.get("done", False)
        nt = result.get("numberComponentsTotal", 0)
        nd = result.get("numberComponentsDeployed", 0)
        ne = result.get("numberComponentErrors", 0)
        print(f"  poll {attempt:>2}: status={status}  components={nd}/{nt}  errors={ne}")
        if done:
            final = result
            break

    if not final:
        print("  [ERROR] deploy did not complete in 5 minutes")
        return False
    if final.get("success"):
        print("\n  [OK] DEPLOY SUCCEEDED")
        return True
    print(f"\n  [FAIL] status={final.get('status')}")
    failures = final.get("details", {}).get("componentFailures", [])
    if isinstance(failures, dict):
        failures = [failures]
    for f in failures[:25]:
        print(f"    - {f.get('fullName', f.get('fileName', '?'))}: {f.get('problem', 'unknown')}")
    return False


def lookup_dashboard_id() -> str | None:
    p = subprocess.run(
        [
            "sf",
            "data",
            "query",
            "--target-org",
            TARGET_ORG,
            "--query",
            f"SELECT Id, Title, DeveloperName FROM Dashboard WHERE DeveloperName='{DASHBOARD_DEV_NAME}' LIMIT 1",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        return None
    recs = json.loads(p.stdout).get("result", {}).get("records", [])
    return recs[0]["Id"] if recs else None


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy Sales Ops Commercial Health & Governance dashboard"
    )
    parser.add_argument(
        "--generate-xml",
        action="store_true",
        help="Generate SFDX metadata XML files (legacy / for fallback ZIP deploy)",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete and recreate all reports and dashboard from scratch",
    )
    parser.add_argument(
        "--metadata-zip",
        action="store_true",
        help="Use legacy Metadata-API ZIP deploy (requires ModifyAllData; usually 403s)",
    )
    args = parser.parse_args()

    reports = get_report_definitions()
    print(f"Reports: {len(reports)} | Dashboard widgets: {len(reports)}")
    assert len(reports) <= 18, f"Widget count {len(reports)} exceeds soft cap 18"

    if args.generate_xml or args.metadata_zip:
        generate_project(reports)
        if args.generate_xml:
            return 0
        zip_path = create_zip(reports)
        ok = deploy_zip(zip_path)
        return 0 if ok else 1

    ok, dash_id, report_id_map = deploy_via_analytics_api(reports, rebuild=args.rebuild)
    if not ok or not dash_id:
        return 1
    url = f"https://simcorp.lightning.force.com/lightning/r/Dashboard/{dash_id}/view"
    print("\n" + "=" * 60)
    print("DEPLOY COMPLETE")
    print("=" * 60)
    print(f"\n  Dashboard ID:  {dash_id}")
    print(f"  Dashboard URL: {url}")
    print(f"\n  Reports created/reused: {len(report_id_map)}/{len(reports)}")
    print("  Reports folder URL:")
    print("    https://simcorp.lightning.force.com/lightning/o/Report/home")
    print(f"    Look for: {FOLDER_LABEL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
