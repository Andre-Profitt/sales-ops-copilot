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
    "Process_Standards",
    "Methodology",
]


# 8-stage SimCorp sales process — verbatim from the Commercial Handbook
# (~/.claude/intel/simcorp-sales-process-2026-04.md). Frozen here so each
# director's xlsx ships with policy context attached, and so the agent
# narrative in the deck can reference these by stage number consistently.
STAGES_8 = [
    ("1", "Prospecting", "Passive stage; BDRs work highest-engagement leads"),
    (
        "2",
        "Discovery",
        "Prospect active; BDR/Sales meetings; price guidance given while scoping",
    ),
    (
        "3",
        "Engagement",
        "Sales Manager driving; due-diligence continues; PAIC assessment, decision-makers identified, competitive position established",
    ),
    (
        "4",
        "Shortlisted",
        "Close plan validated with prospect; scope finalized for commercial negotiation; still in competition",
    ),
    (
        "5",
        "Preferred",
        "Named preferred; no longer in competition; exit when full set of red-lining received",
    ),
    ("6", "Contracting", "Finalize legal review + price; agree terms + implementation"),
    ("7", "Opt-out", "Won but with opt-out clause active; held in stage until clause expires"),
    ("8", "Won", "Contract signed; INSfile generated; handover; transition to delivery"),
]

# Governance gates from slide 7 of the Commercial Handbook
GOVERNANCE_GATES = [
    (
        "Commercial Approval",
        "LAND = ALL deals; AER >€500k for others",
        "Stage 3-4",
        "Go/No-Go on whether SimCorp engages; cost/resource assessment",
    ),
    (
        "Margin Review",
        "Each iteration of scope, discount, payment schedule",
        "Stage 4-6",
        "Before any price proposal to customer",
    ),
    (
        "Deal Services Design",
        "Early stage",
        "Stage 3-4",
        "Implementation costs, risks, timelines",
    ),
    ("Deal Review", "Final", "Stage 5-6", "Final review before final contracting"),
    ("Due Diligence", "All services + contractual", "Throughout", "Continuous"),
]

# Motion differences (Land vs Expand vs Renewal) — for the Process_Standards sheet
MOTIONS = [
    (
        "LAND",
        "New business",
        "Full 8-stage process applies; Commercial Approval mandatory",
        "APTS_Opportunity_ARR__c",
    ),
    (
        "EXPAND",
        "Existing customer growth",
        'Same 8 stages but steps "may vary"; Commercial Approval triggers at AER >€500k',
        "APTS_Opportunity_ARR__c",
    ),
    (
        "RENEWAL",
        "Re-up of existing contract",
        "Different motion entirely; simpler workflow; field reported as ACV not ARR",
        "APTS_Renewal_ACV__c",
    ),
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

    # ── Territory_Performance ── open Land+Expand pipeline by sub-region
    ws = wb["Territory_Performance"]
    ws["A1"] = "Country / sub-region"
    ws["B1"] = "Open ARR"
    ws["C1"] = "# Opps"
    for col in ("A1", "B1", "C1"):
        ws[col].font = Font(bold=True)
    territory = (snapshot or {}).get("territory_performance") or []
    if territory:
        for i, t in enumerate(territory, start=1):
            ws.cell(row=i + 1, column=1, value=t.get("country") or "(unset)")
            ws.cell(row=i + 1, column=2, value=_fmt_meur(t.get("arr_eur") or 0))
            ws.cell(row=i + 1, column=3, value=t.get("num_opps") or 0)
        ws.column_dimensions["A"].width = 32
        ws.column_dimensions["B"].width = 14
        ws.column_dimensions["C"].width = 8
    else:
        ws.cell(row=2, column=1, value="(no territory breakdown for this director)").font = Font(
            italic=True, color="999999"
        )

    # ── At_Risk_Renewals ── open Renewal opps where Account carries High/Very High termination risk
    ws = wb["At_Risk_Renewals"]
    ws["A1"] = "#"
    ws["B1"] = "Account"
    ws["C1"] = "Stage"
    ws["D1"] = "ACV"
    ws["E1"] = "Risk"
    for col in ("A1", "B1", "C1", "D1", "E1"):
        ws[col].font = Font(bold=True)
    at_risk = (snapshot or {}).get("at_risk_renewals") or []
    if at_risk:
        for i, r in enumerate(at_risk, start=1):
            ws.cell(row=i + 1, column=1, value=i)
            ws.cell(row=i + 1, column=2, value=r.get("account") or "")
            ws.cell(row=i + 1, column=3, value=r.get("stage") or "")
            ws.cell(row=i + 1, column=4, value=_fmt_meur(r.get("acv_eur") or 0))
            ws.cell(row=i + 1, column=5, value=r.get("risk_level") or "")
        ws.column_dimensions["A"].width = 4
        ws.column_dimensions["B"].width = 36
        ws.column_dimensions["C"].width = 18
        ws.column_dimensions["D"].width = 12
        ws.column_dimensions["E"].width = 14
    else:
        ws.cell(
            row=2,
            column=1,
            value="(no Renewal opps with High/Very-High termination risk in scope)",
        ).font = Font(italic=True, color="999999")

    # ── Competitive_Pressure ── closed-lost Land+Expand opps this quarter, by competitor
    ws = wb["Competitive_Pressure"]
    ws["A1"] = "Competitor"
    ws["B1"] = "# Lost (CFQ)"
    ws["C1"] = "ARR Lost"
    for col in ("A1", "B1", "C1"):
        ws[col].font = Font(bold=True)
    comp = (snapshot or {}).get("competitive_pressure") or []
    if comp:
        for i, c in enumerate(comp, start=1):
            ws.cell(row=i + 1, column=1, value=c.get("competitor") or "(unknown)")
            ws.cell(row=i + 1, column=2, value=c.get("num_opps") or 0)
            ws.cell(row=i + 1, column=3, value=_fmt_meur(c.get("arr_eur") or 0))
        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 14
        ws.column_dimensions["C"].width = 14
    else:
        ws.cell(
            row=2,
            column=1,
            value="(no closed-lost Land/Expand opps with competitor recorded this quarter)",
        ).font = Font(italic=True, color="999999")

    # ── ARR_Roll ── closed-won booked ARR by month, last 6 months
    ws = wb["ARR_Roll"]
    ws["A1"] = "Month"
    ws["B1"] = "# Won"
    ws["C1"] = "Booked ARR"
    for col in ("A1", "B1", "C1"):
        ws[col].font = Font(bold=True)
    roll = (snapshot or {}).get("arr_roll") or []
    if roll:
        for i, r in enumerate(roll, start=1):
            ws.cell(row=i + 1, column=1, value=r.get("month") or "")
            ws.cell(row=i + 1, column=2, value=r.get("num_opps") or 0)
            ws.cell(row=i + 1, column=3, value=_fmt_meur(r.get("arr_eur") or 0))
        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = 8
        ws.column_dimensions["C"].width = 14
    else:
        ws.cell(
            row=2, column=1, value="(no Land/Expand wins in last 6 months for this director)"
        ).font = Font(italic=True, color="999999")

    # ── Retention ── GRR proxy from closed Renewal opps last 12 months
    ws = wb["Retention"]
    ws["A1"] = "Metric"
    ws["B1"] = "Value"
    ws["C1"] = "Note"
    for col in ("A1", "B1", "C1"):
        ws[col].font = Font(bold=True)
    ret = (snapshot or {}).get("retention") or {}
    if ret:
        ws["A2"] = "Won Renewal ACV (L12M)"
        ws["B2"] = _fmt_meur(ret.get("won_renewal_acv_eur_l12m") or 0)
        ws["C2"] = f"{ret.get('won_count', 0)} renewals won"
        ws["A3"] = "Lost Renewal ACV (L12M)"
        ws["B3"] = _fmt_meur(ret.get("lost_renewal_acv_eur_l12m") or 0)
        ws["C3"] = f"{ret.get('lost_count', 0)} renewals lost"
        ws["A4"] = "GRR proxy"
        ws["B4"] = f"{ret.get('grr_proxy_pct', 0):.1f}%"
        ws["C4"] = "Won ACV / (Won + Lost ACV) — Renewals only, last 12 months"
        ws["A6"] = "NRR"
        ws["B6"] = "—"
        ws["C6"] = (
            "True NRR (incl. expansion uplift on existing accounts) requires "
            "cohort math against historical snapshots — deferred until "
            "Pipeline_Snapshot__c accumulates 12+ months of history."
        )
        ws["A6"].font = Font(italic=True, color="666666")
        ws["B6"].font = Font(italic=True, color="666666")
        ws["C6"].font = Font(italic=True, color="666666")
        ws.column_dimensions["A"].width = 28
        ws.column_dimensions["B"].width = 16
        ws.column_dimensions["C"].width = 70
    else:
        ws.cell(
            row=2, column=1, value="(no Renewal opps closed in last 12 months for this director)"
        ).font = Font(italic=True, color="999999")

    # ── Trend_MoM ── month-over-month booked ARR from arr_roll (last 6 months)
    ws = wb["Trend_MoM"]
    ws["A1"] = "Month"
    ws["B1"] = "# Won"
    ws["C1"] = "Booked ARR"
    ws["D1"] = "Δ MoM"
    for col in ("A1", "B1", "C1", "D1"):
        ws[col].font = Font(bold=True)
    roll = (snapshot or {}).get("arr_roll") or []
    if roll:
        prev_arr: float | None = None
        for i, r in enumerate(roll, start=1):
            cur = float(r.get("arr_eur") or 0)
            ws.cell(row=i + 1, column=1, value=r.get("month") or "")
            ws.cell(row=i + 1, column=2, value=r.get("num_opps") or 0)
            ws.cell(row=i + 1, column=3, value=_fmt_meur(cur))
            if prev_arr is not None and prev_arr > 0:
                pct = (cur - prev_arr) / prev_arr * 100
                ws.cell(row=i + 1, column=4, value=f"{pct:+.0f}%")
            else:
                ws.cell(row=i + 1, column=4, value="—")
            prev_arr = cur
        ws.column_dimensions["A"].width = 10
        ws.column_dimensions["B"].width = 8
        ws.column_dimensions["C"].width = 14
        ws.column_dimensions["D"].width = 10
    else:
        ws.cell(
            row=2, column=1, value="(no Land/Expand wins in last 6 months for this director)"
        ).font = Font(italic=True, color="999999")

    # ── Trend_QoQ ── roll arr_roll up to fiscal quarters (calendar Q for now)
    ws = wb["Trend_QoQ"]
    ws["A1"] = "Quarter"
    ws["B1"] = "# Won"
    ws["C1"] = "Booked ARR"
    ws["D1"] = "Δ QoQ"
    for col in ("A1", "B1", "C1", "D1"):
        ws[col].font = Font(bold=True)
    if roll:
        # Bucket months into calendar quarters (YYYY-Q1..Q4)
        from collections import OrderedDict

        q_acc: OrderedDict[str, dict[str, float]] = OrderedDict()
        for r in roll:
            ym = r.get("month") or ""
            if len(ym) < 7:
                continue
            year, month_str = ym.split("-")
            try:
                month = int(month_str)
            except ValueError:
                continue
            q_idx = (month - 1) // 3 + 1
            qkey = f"{year}-Q{q_idx}"
            bucket = q_acc.setdefault(qkey, {"num_opps": 0, "arr_eur": 0.0})
            bucket["num_opps"] += int(r.get("num_opps") or 0)
            bucket["arr_eur"] += float(r.get("arr_eur") or 0)
        prev_arr = None
        for i, (qk, v) in enumerate(q_acc.items(), start=1):
            cur = v["arr_eur"]
            ws.cell(row=i + 1, column=1, value=qk)
            ws.cell(row=i + 1, column=2, value=int(v["num_opps"]))
            ws.cell(row=i + 1, column=3, value=_fmt_meur(cur))
            if prev_arr is not None and prev_arr > 0:
                pct = (cur - prev_arr) / prev_arr * 100
                ws.cell(row=i + 1, column=4, value=f"{pct:+.0f}%")
            else:
                ws.cell(row=i + 1, column=4, value="—")
            prev_arr = cur
        ws.column_dimensions["A"].width = 10
        ws.column_dimensions["B"].width = 8
        ws.column_dimensions["C"].width = 14
        ws.column_dimensions["D"].width = 10
    else:
        ws.cell(
            row=2, column=1, value="(no quarterly trend data — fewer than 6 months of wins)"
        ).font = Font(italic=True, color="999999")

    # ── Process_Standards ──
    # Verbatim references from the SimCorp Commercial Handbook so the
    # director's xlsx ships with the policy context attached. Pulled
    # 2026-04-28 from `Commercial-Handbook-for-Simlink---Copy.pptx` per
    # `~/.claude/intel/simcorp-sales-process-2026-04.md`.
    ws = wb["Process_Standards"]
    ws["A1"] = "SimCorp 8-Stage Sales Process — verbatim from the Commercial Handbook"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "(Source: Commercial-Handbook-for-Simlink — pulled 2026-04-28)"
    ws["A2"].font = Font(italic=True, color="666666")

    ws["A4"] = "## The 8 stages"
    ws["A4"].font = Font(bold=True, size=12)
    ws["A5"] = "#"
    ws["B5"] = "Stage"
    ws["C5"] = "What happens"
    for col in ("A5", "B5", "C5"):
        ws[col].font = Font(bold=True)
    for i, (num, name, desc) in enumerate(STAGES_8, start=6):
        ws.cell(row=i, column=1, value=num)
        ws.cell(row=i, column=2, value=name)
        ws.cell(row=i, column=3, value=desc)
    next_row = 6 + len(STAGES_8) + 2

    ws.cell(row=next_row, column=1, value="## Governance gates (deal reviews)").font = Font(
        bold=True, size=12
    )
    next_row += 1
    headers_g = ("Gate", "Trigger", "When", "Purpose")
    for j, h in enumerate(headers_g, start=1):
        cell = ws.cell(row=next_row, column=j, value=h)
        cell.font = Font(bold=True)
    next_row += 1
    for gate, trigger, when, purpose in GOVERNANCE_GATES:
        ws.cell(row=next_row, column=1, value=gate)
        ws.cell(row=next_row, column=2, value=trigger)
        ws.cell(row=next_row, column=3, value=when)
        ws.cell(row=next_row, column=4, value=purpose)
        next_row += 1
    next_row += 1

    ws.cell(row=next_row, column=1, value="## Deal motions").font = Font(bold=True, size=12)
    next_row += 1
    headers_m = ("Motion", "What it is", "Process notes", "Reported field")
    for j, h in enumerate(headers_m, start=1):
        cell = ws.cell(row=next_row, column=j, value=h)
        cell.font = Font(bold=True)
    next_row += 1
    for motion, what, notes, field in MOTIONS:
        ws.cell(row=next_row, column=1, value=motion)
        ws.cell(row=next_row, column=2, value=what)
        ws.cell(row=next_row, column=3, value=notes)
        ws.cell(row=next_row, column=4, value=field)
        next_row += 1
    next_row += 1

    ws.cell(
        row=next_row,
        column=1,
        value=(
            "Stalled deal flag: a deal in Stage 5 (Preferred) for >2 weeks with no "
            "movement may have stalled red-lining."
        ),
    ).font = Font(italic=True)

    # Column widths for readability
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 80
    ws.column_dimensions["D"].width = 45

    # ── Methodology ──
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
