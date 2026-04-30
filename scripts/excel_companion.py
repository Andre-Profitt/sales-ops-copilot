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
    "Top_Accounts",
    "By_Owner",
    "Pipeline_Aging",
    "Weighted_Forecast",
    "Wins_Losses_QTD",
    "ARR_Roll",
    "Retention",
    "Forecast_Backtest",
    "At_Risk_Renewals",
    "Competitive_Pressure",
    "Territory_Performance",
    "SimCorp_One",
    "Discount_Analysis",
    "Regional_Benchmarks",
    "Region_Trend_8Q",
    "Trend_MoM",
    "Trend_QoQ",
    "Process_Standards",
    "Methodology",
    "Notes",
]


# Notes — methodology appendix for derived/proxy metrics. Every non-obvious
# computed metric in this workbook is documented here with WHAT it captures,
# WHAT it does not, and HOW to read it. Goal: prevent stakeholder confusion
# when a director cites e.g. "GRR proxy 28%" without realizing it isn't
# the org's true GRR.
NOTES_BLOCKS = [
    (
        "GRR proxy",
        "Retention sheet",
        "won ACV / (won + lost ACV) of CLOSED Renewal opps, last 12 months",
        "The 'at-risk renewal save rate' — when a renewal becomes a tracked opp, what fraction is won.",
        "Auto-renewals that never get a Renewal opp record (likely the majority of true renewal volume); "
        "expansion uplift on existing accounts (which would push toward NRR).",
        "Directional indicator of how well at-risk renewals are saved, NOT the org's overall retention rate. "
        "Typical enterprise SaaS GRR is 90%+; this proxy appears lower because the denominator is biased.",
    ),
    (
        "NRR",
        "Retention sheet (currently '—')",
        "not computed today",
        "Nothing — placeholder for future cohort-based retention math.",
        "Requires cohort math against historical snapshots: pick a customer cohort at T-12mo, compare their "
        "total ACV at T-12mo to today (incl. expansion + churn).",
        "Will be derivable once Pipeline_Snapshot__c (Reporting Snapshot) accumulates 12+ months of history. "
        "Currently admin-pending deploy.",
    ),
    (
        "Forecast backtest forward rates",
        "Forecast_Backtest sheet",
        "P(advanced) per stage, computed by scripts/forecast_backtest.py from OpportunityFieldHistory over the last 4 fiscal quarters",
        "Population-level conversion rates — org-wide, not your territory.",
        "Director-specific rates (would need much more OFH data to be statistically meaningful per territory).",
        "Sanity check on your own territory's stage progression vs the population. If you're materially below, "
        "investigate; if materially above, don't extrapolate without sample-size context.",
    ),
    (
        "Late-stage concentration",
        "Action items + brief.md risks",
        "% of total open Land+Expand pipeline ARR sitting in Stage 5 (Preferred) + Stage 6 (Contracting)",
        "How much of your open pipe is in 'closeable' stages this quarter.",
        "Quality of those late-stage opps — a deal stuck in Stage 5 for 3 months has the same weight as one freshly arrived.",
        "< 30% trips a MEDIUM action. Threshold is empirical — below this it's hard to close enough this Q from existing pipe.",
    ),
    (
        "Coverage Gap",
        "Action items rule (coverage_gap)",
        "Tier-1 accounts (Account.Tier_Calculation__c='Tier 1') in your scope with no open Land/Expand opp created in last 90d",
        "Accounts where new-business pipeline-creation activity has stalled.",
        "Renewals in flight do NOT count as coverage — the rule specifically looks for new-business motion. An account "
        "renewing fine but with no Land/Expand pipe still shows as a gap.",
        ">= 5 starved Tier-1 accounts trips MEDIUM. UKI typically has 100+ — that's a real territory pattern, not a quirk.",
    ),
    (
        "Approval Gap",
        "Action items rule (approval_gap)",
        "Stage 3+ Land/Expand opps >= EUR 500k where Stage_20_Approval__c is false or null",
        "Policy violations under the SimCorp Commercial Approval gate (Commercial Handbook 2026-04, slide 7).",
        "Whether the deal is actually fine to proceed (the missing flag may be data-entry lag, not a real violation).",
        "Per the handbook: Commercial Approval is mandatory for ALL Land deals + AER >€500k Expand. Any matching opp "
        "without the flag should be reviewed; submit for approval before EOM if real.",
    ),
    (
        "Zombie ARR",
        "Action items rule (zombie_arr)",
        "Open Land+Expand opps created >730 days ago AND no Task/Event activity in last 60 days",
        "Stale pipeline that's neither closing nor being worked.",
        "Whether the opp is genuinely dead vs. paused intentionally (e.g., customer in M&A integration). Some legitimately old.",
        "ARR is FX-converted via per-record convertCurrency to EUR. > EUR 1M trips MEDIUM, > EUR 5M trips HIGH. "
        "Top owner is named in the action's suggested_action so the director knows where to start.",
    ),
    (
        "SimCorp One attach rate",
        "Action items rule (simcorp_one_attach_low)",
        "% of open Land/Expand opps with a 'Standard Platform' line item (the SimCorp One core product)",
        "How often the platform anchor is in the deal vs. modules-only opps.",
        "Whether the modules-only opps are intentional (e.g., a Standard Platform customer adding modules) "
        "vs. a missed opportunity to lead with the platform.",
        "< 30% AND total >= 5 opps trips MEDIUM. Strategic signal — most of EMEA + NA AM trips this rule today.",
    ),
    (
        "Activity Drought",
        "Action items rule (activity_drought)",
        "Count of this-quarter-closing open Land+Expand opps with no Task or Event in last 30 days",
        "Forecast-credibility signal — an opp without 30 days of activity rarely closes on time.",
        "Renewal opps (the field zeros for Renewals; would need a separate Renewal-side rule).",
        ">= 5 opps trips MEDIUM. The 30-day window is shorter than the Zombie 60-day to surface near-term forecast risk.",
    ),
    (
        "Trend MoM / QoQ",
        "Trend_MoM, Trend_QoQ sheets",
        "Closed-Won Land+Expand by CloseDate calendar month / calendar quarter, last 6 months / 4 quarters",
        "Director-scoped booked ARR rhythm.",
        "Forecast for forward periods. Small monthly samples are noisy — one large deal closing in a low month "
        "produces +1000% MoM swings that aren't predictive.",
        "Read with the # Won column as denominator context. QoQ uses CALENDAR quarters, not SimCorp fiscal "
        "quarters — adjust mentally if the org's fiscal calendar matters.",
    ),
    (
        "ARR Roll",
        "ARR_Roll sheet",
        "Same source as Trend_MoM (closed-Won L+E by CloseDate, last 6 months)",
        "Six-month booked-ARR rhythm.",
        "True 'roll' (new + expand + churn snapshot deltas) which requires snapshot history.",
        "Approximation until Pipeline_Snapshot__c accumulates 12+ months of data.",
    ),
    (
        "Top Deals Land / Expand",
        "Top_Deals_Land, Top_Deals_Expand sheets",
        "Top 10 open opps in director scope by FX-converted ARR",
        "Where most of your open pipe value sits.",
        "Account names — anonymized to (stage, ARR) per AI Code of Conduct §8 to keep client-level data out "
        "of any LLM-mediated pipeline. Owner.Name (employees) is fine.",
        "Use to prioritize 1:1 reviews with the owners of the top 5 deals; don't share externally.",
    ),
    (
        "Territory Performance",
        "Territory_Performance sheet",
        "Open Land+Expand pipeline broken out by Account.BillingCountry within your scope",
        "Sub-regional concentration within your overall scope.",
        "Region-level rollup beyond your scope (use the regional memo for that — see "
        "state/<period>/__regional__/<region>.md).",
        "Single-country directors (Megan / Adam) show one row; multi-country (Sarah / Christian / Mourad) "
        "show the dominant countries.",
    ),
    (
        "Competitive Pressure",
        "Competitive_Pressure sheet",
        "Closed-LOST Land+Expand opps in current fiscal quarter, by Lost_to_Competitor__r.Name",
        "Where you're losing deals — actionable competitive feedback.",
        "Closed-WON deals against competitors (different SF field, not currently tracked here).",
        "Lost_to_Competitor__c is sparsely populated org-wide. If most rows show '(no competitor recorded)', "
        "treat as a DATA-QUALITY finding (push reps to log it), not a commercial finding.",
    ),
    (
        "Action item priorities",
        "Action_Items sheet, brief.md, regional memo",
        "Set by rule (high/medium/low), not by relative importance to the director",
        "Within-rule severity (e.g., HIGH zombie = > EUR 5M; MEDIUM = > EUR 1M).",
        "Cross-rule comparability — two HIGH actions from different rules aren't directly comparable.",
        "HIGH = governance violation or material exposure (approval_gap; large zombie pile). "
        "MEDIUM = operational concern (coverage gap; late-stage; SC1 attach; activity). LOW = data hygiene.",
    ),
    (
        "FX conversion",
        "All EUR figures",
        "Per-record SOQL convertCurrency() returning the value in apro@simcorp.com's display currency (EUR)",
        "Each opp's ARR/ACV converted from its CurrencyIsoCode to EUR at SF's stored exchange rate.",
        "SOQL SUM(convertCurrency(field)) silently does NOT apply at aggregate level — we sum per-record values "
        "in Python. SF Reports REST `s!field.CONVERT` aggregates also FX-correct (used by the daily brief).",
        "All EUR amounts in this workbook are FX-converted. Raw multi-currency sums via SOQL are forbidden by "
        "the SimCorp cardinal rule (feedback_sf_multi_currency_aggregation memory).",
    ),
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

    # ── Top_Accounts ── account-level rollup of open Land+Expand ARR
    ws = wb["Top_Accounts"]
    ws["A1"] = "#"
    ws["B1"] = "Account"
    ws["C1"] = "# Open opps"
    ws["D1"] = "Open ARR"
    for col in ("A1", "B1", "C1", "D1"):
        ws[col].font = Font(bold=True)
    accts = (snapshot or {}).get("top_accounts") or []
    if accts:
        for i, a in enumerate(accts, start=1):
            ws.cell(row=i + 1, column=1, value=i)
            ws.cell(row=i + 1, column=2, value=a.get("account") or "(unknown)")
            ws.cell(row=i + 1, column=3, value=a.get("num_opps") or 0)
            ws.cell(row=i + 1, column=4, value=_fmt_meur(a.get("arr_eur") or 0))
        ws.column_dimensions["A"].width = 4
        ws.column_dimensions["B"].width = 40
        ws.column_dimensions["C"].width = 12
        ws.column_dimensions["D"].width = 14
    else:
        ws.cell(row=2, column=1, value="(no open Land/Expand opps in scope)").font = Font(
            italic=True, color="999999"
        )

    # ── By_Owner ── pipeline by rep within director scope
    ws = wb["By_Owner"]
    ws["A1"] = "Owner"
    ws["B1"] = "# Open opps"
    ws["C1"] = "Open ARR"
    for col in ("A1", "B1", "C1"):
        ws[col].font = Font(bold=True)
    bo = (snapshot or {}).get("by_owner") or []
    if bo:
        for i, o in enumerate(bo, start=1):
            ws.cell(row=i + 1, column=1, value=o.get("owner") or "(unknown)")
            ws.cell(row=i + 1, column=2, value=o.get("num_opps") or 0)
            ws.cell(row=i + 1, column=3, value=_fmt_meur(o.get("arr_eur") or 0))
        ws.column_dimensions["A"].width = 32
        ws.column_dimensions["B"].width = 12
        ws.column_dimensions["C"].width = 14
    else:
        ws.cell(row=2, column=1, value="(no opps to attribute)").font = Font(
            italic=True, color="999999"
        )

    # ── Pipeline_Aging ── 5 age buckets by CreatedDate
    ws = wb["Pipeline_Aging"]
    ws["A1"] = "Age bucket"
    ws["B1"] = "# Opps"
    ws["C1"] = "Open ARR"
    for col in ("A1", "B1", "C1"):
        ws[col].font = Font(bold=True)
    aging = (snapshot or {}).get("pipeline_aging") or []
    if aging:
        for i, b in enumerate(aging, start=1):
            ws.cell(row=i + 1, column=1, value=b.get("bucket") or "")
            ws.cell(row=i + 1, column=2, value=b.get("num_opps") or 0)
            ws.cell(row=i + 1, column=3, value=_fmt_meur(b.get("arr_eur") or 0))
        ws.column_dimensions["A"].width = 18
        ws.column_dimensions["B"].width = 10
        ws.column_dimensions["C"].width = 14
    else:
        ws.cell(row=2, column=1, value="(no Land/Expand opps to age-bucket)").font = Font(
            italic=True, color="999999"
        )

    # ── Weighted_Forecast ── apply backtest forward rates to current stage ARR
    ws = wb["Weighted_Forecast"]
    ws["A1"] = "Stage"
    ws["B1"] = "Open ARR"
    ws["C1"] = "Forward rate"
    ws["D1"] = "Weighted ARR"
    ws["E1"] = "Note"
    for col in ("A1", "B1", "C1", "D1", "E1"):
        ws[col].font = Font(bold=True)
    rates = (backtest or {}).get("forward_rates") or {}
    pipeline_kpis = [k for k in envelope["kpis"] if k["name"].startswith("pipeline_arr_stage_")]
    if pipeline_kpis and rates:
        total_weighted = 0.0
        for i, k in enumerate(pipeline_kpis, start=1):
            stage_num = k["name"].replace("pipeline_arr_stage_", "")
            rate_key = f"stage_{stage_num}_forward_rate"
            rate = rates.get(rate_key, 0.0)
            arr = float(k.get("value") or 0)
            weighted = arr * rate
            total_weighted += weighted
            ws.cell(row=i + 1, column=1, value=k.get("stage_label") or k["name"])
            ws.cell(row=i + 1, column=2, value=_fmt_meur(arr))
            ws.cell(row=i + 1, column=3, value=f"{rate * 100:.1f}%")
            ws.cell(row=i + 1, column=4, value=_fmt_meur(weighted))
            ws.cell(row=i + 1, column=5, value="org-wide rate × this director's open ARR")
        last_row = len(pipeline_kpis) + 2
        ws.cell(row=last_row, column=1, value="TOTAL weighted").font = Font(bold=True)
        ws.cell(row=last_row, column=4, value=_fmt_meur(total_weighted)).font = Font(bold=True)
        ws.column_dimensions["A"].width = 22
        ws.column_dimensions["B"].width = 14
        ws.column_dimensions["C"].width = 14
        ws.column_dimensions["D"].width = 14
        ws.column_dimensions["E"].width = 50
    else:
        ws.cell(
            row=2, column=1, value="(insufficient stage data for weighted forecast)"
        ).font = Font(italic=True, color="999999")

    # ── SimCorp_One ── SP attach rate + SP share by stage
    ws = wb["SimCorp_One"]
    ws["A1"] = "SimCorp One (Standard Platform) penetration"
    ws["A1"].font = Font(bold=True, size=12)
    sp_data = (snapshot or {}).get("simcorp_one") or {}
    if sp_data:
        ws["A3"] = "Total open Land+Expand opps in scope"
        ws["B3"] = sp_data.get("total_count", 0)
        ws["A4"] = "With Standard Platform line item"
        ws["B4"] = sp_data.get("sp_count", 0)
        ws["A5"] = "Attach rate"
        ws["B5"] = f"{sp_data.get('share_pct', 0):.1f}%"
        ws["A5"].font = Font(bold=True)
        ws["B5"].font = Font(bold=True)
        ws["A7"] = (
            "Threshold: < 30% AND total >= 5 trips a MEDIUM action item. "
            "See Notes sheet for the policy + selling-motion implications."
        )
        ws["A7"].font = Font(italic=True, color="666666")
        ws.column_dimensions["A"].width = 42
        ws.column_dimensions["B"].width = 14
    else:
        ws.cell(
            row=2, column=1, value="(SP data not available — check action_data wiring)"
        ).font = Font(italic=True, color="999999")

    # ── Discount_Analysis ── pulled from DD · Discount Depth Pending report (org-wide)
    ws = wb["Discount_Analysis"]
    ws["A1"] = "Discount Depth Pending — org-wide (not director-scoped)"
    ws["A1"].font = Font(bold=True, size=12)
    ws["A2"] = (
        "Source: DD · Discount Depth Pending (00OTb000008njSPMAY). Field "
        "ZIMIT_Discount__c is sparsely populated; treat the figures as "
        "indicative, not comprehensive. See Notes sheet."
    )
    ws["A2"].font = Font(italic=True, color="666666")
    ws["A4"] = "Discount band"
    ws["B4"] = "# Opps"
    ws["C4"] = "ARR"
    for col in ("A4", "B4", "C4"):
        ws[col].font = Font(bold=True)
    disc = ((snapshot or {}).get("benchmarks") or {}).get("discount_pending") or {}
    rows_disc = disc.get("rows") or []
    if rows_disc:
        for i, r in enumerate(rows_disc, start=5):
            ws.cell(row=i, column=1, value=r.get("discount_band") or "?")
            ws.cell(row=i, column=2, value=r.get("num_opps") or 0)
            ws.cell(row=i, column=3, value=_fmt_meur(r.get("arr_eur") or 0))
        last = 4 + len(rows_disc) + 1
        ws.cell(row=last, column=1, value="TOTAL").font = Font(bold=True)
        ws.cell(row=last, column=2, value=disc.get("grand_num_opps") or 0).font = Font(bold=True)
        ws.cell(row=last, column=3, value=_fmt_meur(disc.get("grand_arr_eur") or 0)).font = Font(
            bold=True
        )
        ws.column_dimensions["A"].width = 16
        ws.column_dimensions["B"].width = 10
        ws.column_dimensions["C"].width = 14
    else:
        ws.cell(
            row=5,
            column=1,
            value="(report unreachable or returned no rows)",
        ).font = Font(italic=True, color="999999")

    # ── Regional_Benchmarks ── pulled from CRO · Open Pipeline by Region (org-wide)
    ws = wb["Regional_Benchmarks"]
    ws["A1"] = "Open pipeline ARR by region — org-wide context"
    ws["A1"].font = Font(bold=True, size=12)
    ws["A2"] = (
        "Source: CRO · Open Pipeline by Region (00OTb000008mvyfMAA). "
        "FX-correct via SF Report `s!field.CONVERT` aggregates. The "
        "row matching this director's region is highlighted in bold."
    )
    ws["A2"].font = Font(italic=True, color="666666")
    ws["A4"] = "Region"
    ws["B4"] = "Open ARR"
    ws["C4"] = "% of org"
    ws["D4"] = "# Opps"
    for col in ("A4", "B4", "C4", "D4"):
        ws[col].font = Font(bold=True)
    pbr = ((snapshot or {}).get("benchmarks") or {}).get("open_pipe_by_region") or {}
    pbr_rows = pbr.get("rows") or []
    grand = pbr.get("grand_arr_eur") or 0
    director_scope = (envelope.get("director") or {}).get("scope_label", "") or ""
    if pbr_rows:
        for i, r in enumerate(pbr_rows, start=5):
            region = r.get("region") or ""
            arr = r.get("arr_eur") or 0
            pct = (arr / grand * 100) if grand else 0
            cell_a = ws.cell(row=i, column=1, value=region)
            cell_b = ws.cell(row=i, column=2, value=_fmt_meur(arr))
            cell_c = ws.cell(row=i, column=3, value=f"{pct:.1f}%")
            cell_d = ws.cell(row=i, column=4, value=r.get("opp_count") or 0)
            # Bold the row that matches the director's scope (loose substring match)
            if region and (
                region.lower() in director_scope.lower()
                or director_scope.lower() in region.lower()
                or any(
                    word in region.lower()
                    for word in director_scope.lower().split()
                    if len(word) > 3
                )
            ):
                for c in (cell_a, cell_b, cell_c, cell_d):
                    c.font = Font(bold=True)
        last = 4 + len(pbr_rows) + 1
        ws.cell(row=last, column=1, value="ORG TOTAL").font = Font(bold=True)
        ws.cell(row=last, column=2, value=_fmt_meur(grand)).font = Font(bold=True)
        ws.cell(row=last, column=3, value="100.0%").font = Font(bold=True)
        ws.column_dimensions["A"].width = 28
        ws.column_dimensions["B"].width = 14
        ws.column_dimensions["C"].width = 10
        ws.column_dimensions["D"].width = 10
    else:
        ws.cell(
            row=5,
            column=1,
            value="(benchmark report unreachable)",
        ).font = Font(italic=True, color="999999")

    # ── Region_Trend_8Q ── pulled from CRO · Win Rate Trend 8Q (org-wide)
    ws = wb["Region_Trend_8Q"]
    ws["A1"] = "Win Rate trend by Fiscal Quarter — org-wide (last 8 FQ)"
    ws["A1"].font = Font(bold=True, size=12)
    ws["A2"] = (
        "Source: CRO · Win Rate Trend 8Q (00OTb000008neanMAA). Org-wide "
        "win rate (Closed-Won / Closed-Total) by fiscal quarter. Use as "
        "context for your territory's QoQ trend in Trend_QoQ."
    )
    ws["A2"].font = Font(italic=True, color="666666")
    ws["A4"] = "Fiscal Quarter"
    ws["B4"] = "Win rate"
    ws["C4"] = "# Closed opps"
    for col in ("A4", "B4", "C4"):
        ws[col].font = Font(bold=True)
    wrt = ((snapshot or {}).get("benchmarks") or {}).get("win_rate_trend_8q") or []
    if wrt:
        for i, r in enumerate(wrt, start=5):
            ws.cell(row=i, column=1, value=r.get("quarter") or "?")
            ws.cell(row=i, column=2, value=f"{r.get('win_rate_pct', 0):.1f}%")
            ws.cell(row=i, column=3, value=r.get("num_opps") or 0)
        ws.column_dimensions["A"].width = 14
        ws.column_dimensions["B"].width = 12
        ws.column_dimensions["C"].width = 14
    else:
        ws.cell(
            row=5,
            column=1,
            value="(benchmark report unreachable)",
        ).font = Font(italic=True, color="999999")

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
        ws["C4"] = (
            "Won ACV / (Won + Lost ACV) — Renewals only, last 12 months. "
            "*** PROXY — see Notes sheet for full caveats. NOT the org's true GRR. ***"
        )
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

    # ── Notes ── methodology appendix for derived/proxy metrics
    ws = wb["Notes"]
    ws["A1"] = "Notes & Methodology — derived and proxy metrics"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = (
        "How each non-obvious computed metric in this workbook is built, "
        "what it does NOT capture, and how to read it. Read this BEFORE "
        "citing any of the percentages or proxy figures externally."
    )
    ws["A2"].font = Font(italic=True, color="666666")
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 80

    row = 4
    for metric, where_used, formula, captures, does_not_capture, how_to_read in NOTES_BLOCKS:
        ws.cell(row=row, column=1, value=metric).font = Font(bold=True, size=12)
        row += 1
        for label, val in (
            ("Where used", where_used),
            ("Formula", formula),
            ("What it captures", captures),
            ("What it does NOT capture", does_not_capture),
            ("How to read it", how_to_read),
        ):
            ws.cell(row=row, column=1, value=label).font = Font(bold=True)
            cell_b = ws.cell(row=row, column=2, value=val)
            cell_b.alignment = cell_b.alignment.copy(wrap_text=True)
            ws.row_dimensions[row].height = max(15, 15 * (1 + len(val) // 80))
            row += 1
        row += 1  # blank spacer between metrics

    # Footer
    ws.cell(
        row=row + 1,
        column=1,
        value=(
            "All figures FX-converted to EUR via SF convertCurrency() at the per-opp level. "
            "Raw multi-currency SOQL SUM is forbidden per the SimCorp cardinal rule. "
            "If you spot a number that doesn't tie to a SF report, file a bug — the report "
            "(via s!field.CONVERT aggregate) is the FX-correct source of truth."
        ),
    ).font = Font(italic=True, color="666666")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
