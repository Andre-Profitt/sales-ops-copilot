"""Excel companion for LAND-monthly per-director brief.

15 sheets. mEUR formatting, no em-dashes per project memory.
Sheets 4-12 are scaffolded for future enrichment from forecast_backtest /
snapshot_diff (Phase 1.5.A.4 + .5).
"""

from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font


def _fmt_meur(value: float) -> str:
    if value is None:
        return "-"
    return f"{value / 1_000_000:.1f} mEUR"


SHEET_NAMES = [
    "Cover",
    "Pipeline_Total",
    "Pipeline_By_Stage",
    "Top_Deals_Land",
    "Top_Deals_Expand",
    "Wins_Losses_QTD",
    "ARR_Roll",
    "Retention",
    "Forecast_Backtest",
    "At_Risk_Renewals",
    "Competitive_Pressure",
    "Territory_Performance",
    "Trend_MoM",
    "Trend_QoQ",
    "Methodology",
]


def build_director_excel(envelope: dict, out_path: Path) -> None:
    """Build a 15-sheet xlsx for the director described in envelope."""
    wb = Workbook()
    default = wb.active
    wb.remove(default)

    for name in SHEET_NAMES:
        wb.create_sheet(name)

    d = envelope["director"]

    # Cover
    ws = wb["Cover"]
    ws["A1"] = f"{d['name']} - {envelope['period']} LAND review"
    ws["A1"].font = Font(bold=True, size=18)
    ws["A3"] = f"Period end: {envelope['period_end']}"
    ws["A4"] = f"Generated: {datetime.now(timezone.utc).isoformat()}"
    ws["A5"] = f"Currency: {envelope.get('currency_format', 'mEUR')}"
    ws["A7"] = "Aggregate-only per SimCorp AI Code of Conduct. No client-level data."

    # Pipeline_Total
    ws = wb["Pipeline_Total"]
    ws["A1"] = "KPI"
    ws["B1"] = "Value"
    ws["A1"].font = Font(bold=True)
    ws["B1"].font = Font(bold=True)
    pipeline = next((k for k in envelope["kpis"] if k["name"] == "total_pipeline_arr"), None)
    renewal = next((k for k in envelope["kpis"] if k["name"] == "total_renewal_acv"), None)
    ws["A2"] = "Total new-business ARR"
    ws["B2"] = _fmt_meur(pipeline["value"]) if pipeline else "-"
    ws["A3"] = "Total renewal ACV"
    ws["B3"] = _fmt_meur(renewal["value"]) if renewal else "-"

    # Pipeline_By_Stage
    ws = wb["Pipeline_By_Stage"]
    ws["A1"] = "Stage"
    ws["B1"] = "ARR"
    ws["C1"] = "# Opps"
    for col in ("A1", "B1", "C1"):
        ws[col].font = Font(bold=True)
    row = 2
    for k in envelope["kpis"]:
        if k["name"].startswith("pipeline_arr_stage_"):
            ws.cell(row=row, column=1, value=k.get("stage_label", k["name"]))
            ws.cell(row=row, column=2, value=_fmt_meur(k["value"]))
            ws.cell(row=row, column=3, value=k.get("num_opps", 0))
            row += 1

    # Sheets 4-12: scaffolded but populated only when forecast_backtest /
    # snapshot_diff data is wired in (Phase 1.5.A.4 + .5).
    placeholder_sheets = {
        "Top_Deals_Land": "Top 10 Land deals - populate when sample-deal join is added",
        "Top_Deals_Expand": "Top 10 Expand deals - same",
        "Wins_Losses_QTD": "QTD wins + losses - populate from CloseDate window",
        "ARR_Roll": "New + Expand + Churn ARR - populate from snapshot_diff",
        "Retention": "NRR + GRR - populate from Wave Revenue_Retention_Health (when wired)",
        "Forecast_Backtest": "4Q backtest - populate from forecast_backtest.py output",
        "At_Risk_Renewals": "At-risk renewal accounts - populate when health-score join is added",
        "Competitive_Pressure": "Lost-to-competitor breakdown - populate from Lost_to_Competitor__c",
        "Territory_Performance": "Per-territory pipeline + wins - populate from Account.Region__c roll-up",
    }
    for sheet_name, msg in placeholder_sheets.items():
        ws = wb[sheet_name]
        ws["A1"] = msg
        ws["A1"].font = Font(italic=True, color="999999")

    # Trend_MoM, Trend_QoQ - empty for now (filled by snapshot_diff wiring in Phase 1.5.A.5)
    for trend_sheet in ("Trend_MoM", "Trend_QoQ"):
        ws = wb[trend_sheet]
        ws["A1"] = "KPI"
        ws["B1"] = "Value"
        ws["C1"] = f"Delta {trend_sheet.split('_')[1]} %"
        for col in ("A1", "B1", "C1"):
            ws[col].font = Font(bold=True)
        row = 2
        for k in envelope["kpis"]:
            ws.cell(row=row, column=1, value=k["name"])
            ws.cell(
                row=row, column=2, value=_fmt_meur(k["value"]) if k["unit"] == "EUR" else k["value"]
            )
            ws.cell(row=row, column=3, value="-")
            row += 1

    # Methodology
    ws = wb["Methodology"]
    ws["A1"] = "Field reference"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A3"] = "Source"
    ws["B3"] = "Field"
    ws["C3"] = "Notes"
    for col in ("A3", "B3", "C3"):
        ws[col].font = Font(bold=True)
    method_rows = [
        (
            "Salesforce Opportunity",
            "APTS_Opportunity_ARR__c",
            "Land + Expand ARR (do not blend with Renewal ACV)",
        ),
        ("Salesforce Opportunity", "APTS_Renewal_ACV__c", "Renewal ACV"),
        ("Salesforce Opportunity", "Stage_20_Approval__c", "Commercial Approval flag"),
        (
            "Salesforce Account",
            "Region__c / BillingCountry / Industry",
            "Director scope (per project_sales_director_md1_presets memory)",
        ),
        (
            "SimCorp Commercial Handbook",
            "8-stage process",
            "Prospecting -> ... -> Won; stage names start with stage number",
        ),
        ("AI Code of Conduct", "aggregate-only", "No client-level data flows through LLM"),
    ]
    for i, row in enumerate(method_rows, start=4):
        for j, val in enumerate(row, start=1):
            ws.cell(row=i, column=j, value=val)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
