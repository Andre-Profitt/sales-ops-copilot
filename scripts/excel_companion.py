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
    "Action_Items",
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


def build_director_excel(
    envelope: dict,
    out_path: Path,
    *,
    snapshot: dict | None = None,
    backtest: dict | None = None,
) -> None:
    """Build a 16-sheet xlsx for the director described in envelope.

    Args:
        envelope: trends.json envelope (locked, schema_version=2)
        out_path: where to write the xlsx
        snapshot: optional raw director snapshot from pull_director_snapshot
                  — used to populate Top_Deals_Land / Top_Deals_Expand /
                  Wins_Losses_QTD sheets that aren't part of the envelope
        backtest: optional dict from state/forecast_backtest_q4.json
                  — populates Forecast_Backtest sheet
    """
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

    # Action_Items — populated from envelope.action_items (schema_version=2).
    # This is the canonical location for the director's monthly action queue
    # in Excel form. Pre-positioned for think-cell datalinks: a deck template
    # can link a chart/table directly to the named range "Action_Items" or to
    # specific cells (B2:F<N>) in this sheet.
    ws = wb["Action_Items"]
    headers = ["#", "Priority", "Rule", "Claim", "Suggested action", "Due date", "Owner"]
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = Font(bold=True)
    actions = envelope.get("action_items") or []
    if actions:
        for i, a in enumerate(actions, start=1):
            ws.cell(row=i + 1, column=1, value=i)
            ws.cell(row=i + 1, column=2, value=(a.get("priority") or "").upper())
            ws.cell(row=i + 1, column=3, value=a.get("rule_id"))
            ws.cell(row=i + 1, column=4, value=a.get("claim"))
            ws.cell(row=i + 1, column=5, value=a.get("suggested_action"))
            ws.cell(row=i + 1, column=6, value=a.get("due_date"))
            ws.cell(row=i + 1, column=7, value=a.get("owner"))
        # Reasonable column widths for readability when the deck reviewer
        # pops the xlsx open
        ws.column_dimensions["A"].width = 4
        ws.column_dimensions["B"].width = 10
        ws.column_dimensions["C"].width = 22
        ws.column_dimensions["D"].width = 80
        ws.column_dimensions["E"].width = 80
        ws.column_dimensions["F"].width = 12
        ws.column_dimensions["G"].width = 22
    else:
        ws.cell(row=2, column=1, value="(no actions tripped this period)").font = Font(
            italic=True, color="999999"
        )

    # ── Top_Deals_Land + Top_Deals_Expand ──
    # Two-column ranked list: stage + ARR. From the per-director SOQL
    # snapshot (FX-correct via convertCurrency).
    for sheet_name, source_key in [
        ("Top_Deals_Land", "top_deals_land"),
        ("Top_Deals_Expand", "top_deals_expand"),
    ]:
        ws = wb[sheet_name]
        ws["A1"] = "#"
        ws["B1"] = "Stage"
        ws["C1"] = "ARR (EUR)"
        for col in ("A1", "B1", "C1"):
            ws[col].font = Font(bold=True)
        deals = (snapshot or {}).get(source_key) or []
        if deals:
            for i, d_row in enumerate(deals, start=1):
                ws.cell(row=i + 1, column=1, value=i)
                ws.cell(row=i + 1, column=2, value=d_row.get("stage") or "")
                ws.cell(row=i + 1, column=3, value=_fmt_meur(d_row.get("arr_eur") or 0))
            ws.column_dimensions["A"].width = 4
            ws.column_dimensions["B"].width = 24
            ws.column_dimensions["C"].width = 14
        else:
            ws.cell(row=2, column=1, value="(no deals in scope this period)").font = Font(
                italic=True, color="999999"
            )

    # ── Wins_Losses_QTD ──
    ws = wb["Wins_Losses_QTD"]
    ws["A1"] = "Outcome"
    ws["B1"] = "Count"
    ws["C1"] = "ARR (Land+Expand)"
    ws["D1"] = "ACV (Renewal)"
    for col in ("A1", "B1", "C1", "D1"):
        ws[col].font = Font(bold=True)
    wl = (snapshot or {}).get("wins_losses_qtd") or {}
    if wl:
        ws["A2"] = "Won"
        ws["B2"] = wl.get("won_count", 0)
        ws["C2"] = _fmt_meur(wl.get("won_arr_eur") or 0)
        ws["D2"] = _fmt_meur(wl.get("won_acv_eur") or 0)
        ws["A3"] = "Lost"
        ws["B3"] = wl.get("lost_count", 0)
        ws["C3"] = _fmt_meur(wl.get("lost_arr_eur") or 0)
        ws["D3"] = _fmt_meur(wl.get("lost_acv_eur") or 0)
        ws.column_dimensions["A"].width = 10
        ws.column_dimensions["B"].width = 8
        ws.column_dimensions["C"].width = 18
        ws.column_dimensions["D"].width = 18
    else:
        ws.cell(row=2, column=1, value="(no closed deals this quarter)").font = Font(
            italic=True, color="999999"
        )

    # ── Forecast_Backtest ──
    # Forward-rate per stage, derived from 4 quarters of OpportunityFieldHistory
    # by scripts/forecast_backtest.py. Backtest data is org-wide (not director-
    # scoped) — these are population-level conversion rates.
    ws = wb["Forecast_Backtest"]
    ws["A1"] = "Stage transition"
    ws["B1"] = "Forward rate"
    ws["C1"] = "Note"
    for col in ("A1", "B1", "C1"):
        ws[col].font = Font(bold=True)
    rates = (backtest or {}).get("forward_rates") or {}
    if rates:
        for i, (key, val) in enumerate(sorted(rates.items()), start=2):
            stage_num = key.replace("stage_", "").replace("_forward_rate", "")
            ws.cell(row=i, column=1, value=f"Stage {stage_num} -> next")
            ws.cell(row=i, column=2, value=f"{val * 100:.1f}%")
            ws.cell(row=i, column=3, value="org-wide rate, last 4 fiscal quarters")
        ws.column_dimensions["A"].width = 22
        ws.column_dimensions["B"].width = 14
        ws.column_dimensions["C"].width = 40
    else:
        ws.cell(row=2, column=1, value="run scripts/forecast_backtest.py first").font = Font(
            italic=True, color="999999"
        )

    # Sheets still scaffolded — populated once historical-snapshot infra exists
    placeholder_sheets = {
        "ARR_Roll": "New + Expand + Churn ARR - populate from Pipeline_Snapshot__c (deferred until snapshot infra deployed)",
        "Retention": "NRR + GRR - populate from cohort math against historical snapshots (deferred)",
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
