"""Formula-driven LAND-monthly workbook (per-director model).

Companion to `excel_companion.py` which produces a flat report (every cell
is a precomputed value written by Python). This module produces a
**model**: a workbook where the analytical sheets reference a single
canonical Data sheet through Excel formulas (SUMIFS, COUNTIFS, INDEX/MATCH,
SORT, etc.). Stakeholders can click any headline cell and trace the
computation to its inputs; thresholds live in a Parameters sheet (single
edit changes downstream propagation), and stage labels live in a Stages
reference sheet (sourced from the canonical sales-process knowledge graph).

Phase 1 (this module):
    Cover, Parameters, Stages, Data, Pipeline_Total, Pipeline_By_Stage,
    Pipeline_Aging, By_Owner, Methodology

    Everything above is formula-driven against Data + Parameters + Stages.

Phase 2 (still in excel_companion.py for now):
    Top_Deals_Land/Expand, Weighted_Forecast, Trend_MoM/QoQ, Retention,
    SimCorp_One, Discount_Analysis, Regional_Benchmarks, Region_Trend_8Q,
    Action_Items, At_Risk_Renewals, Competitive_Pressure, ARR_Roll,
    Forecast_Backtest, Territory_Performance, Process_Standards, Notes.

    These keep precomputed values for now; migrate as auditability needs
    surface.

Output: state/<period>/<director>/land.model.xlsx (sibling of land.xlsx).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.page import PageMargins

from sales_process_graph import GRAPH

# Brand colors — same source-of-truth as excel_companion (don't drift).
BRAND_PRIMARY = "083EA7"  # SimCorp blue
BRAND_SECONDARY = "1A1D31"
BRAND_GRAY = "666666"
BRAND_LIGHT_GRAY = "F2F2F2"

# FAST/ICAEW-style color coding for cell roles. Matches the convention
# used by Anthropic's official xlsx Agent Skill so stakeholders moving
# between Claude-generated workbooks and ours see one auditability scheme:
#   INPUT  (hardcoded value)     → blue
#   LOCAL  (formula, same sheet) → black (default)
#   XREF   (formula, other sheet) → green
#   EXT    (formula, other workbook) → red  [never used here]
INPUT_COLOR = "0070C0"  # blue — inputs / parameters / source data
LOCAL_COLOR = "000000"  # black — formula referencing only own sheet
XREF_COLOR = "00703C"  # dark green — formula crossing sheets
EXT_COLOR = "C00000"  # dark red — formula crossing workbooks

DATA_COLUMNS = [
    ("Id", "string"),
    ("Type", "string"),
    ("StageName", "string"),
    ("CreatedDate", "date"),
    ("CloseDate", "date"),
    ("OwnerName", "string"),
    ("AccountName", "string"),
    ("BillingCountry", "string"),
    ("RiskTermination", "string"),
    ("ARR_EUR", "number"),
    ("ACV_EUR", "number"),
]


def _period_bounds(period: str) -> tuple[date, date]:
    """'2026-Q2' -> (2026-04-01, 2026-07-01)."""
    year, q = period.split("-Q")
    qn = int(q)
    start_month = (qn - 1) * 3 + 1
    end_year = int(year) + (1 if qn == 4 else 0)
    end_month = (start_month + 3) if qn != 4 else 1
    return date(int(year), start_month, 1), date(end_year, end_month, 1)


def _add_named_range(wb: Workbook, name: str, ref: str) -> None:
    """Workbook-scoped named range pointing at e.g. 'Parameters!$B$2'."""
    wb.defined_names[name] = DefinedName(name=name, attr_text=ref)


def _set_header(ws, row: int, headers: list[str]) -> None:
    fill = PatternFill(start_color=BRAND_PRIMARY, end_color=BRAND_PRIMARY, fill_type="solid")
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col_idx, value=h)
        cell.font = Font(bold=True, color="FFFFFF", name="Arial")
        cell.fill = fill
        cell.alignment = Alignment(horizontal="left", vertical="center")


def build_director_model(
    envelope: dict,
    out_path: Path,
    *,
    snapshot: dict | None = None,
) -> None:
    """Build the formula-driven model workbook.

    Args:
        envelope: trends.json envelope (locked, schema_version=2)
        out_path: where to write the xlsx
        snapshot: per-director snapshot from pull_director_snapshot. The
            'raw_opps' key is the seed for the Data sheet. If absent, the
            Data sheet is empty and downstream formulas resolve to zero.
    """
    wb = Workbook()
    default = wb.active
    if default is not None:
        wb.remove(default)

    period = envelope.get("period") or ""
    period_start, period_end = (
        _period_bounds(period) if "-Q" in period else (date.today(), date.today())
    )
    director = envelope.get("director") or {}

    _build_cover(wb, director, period, envelope.get("period_end") or "")
    _build_parameters(wb, period_start, period_end)
    _build_stages(wb)
    _build_data(wb, (snapshot or {}).get("raw_opps") or [])
    _build_pipeline_total(wb, period)
    _build_pipeline_by_stage(wb, period)
    _build_pipeline_aging(wb)
    _build_by_owner(wb, snapshot)
    _build_methodology(wb)

    _apply_print_setup(wb, director, period)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)


# ──────────────────────────────────────────────────────────────────────────
# Sheet builders
# ──────────────────────────────────────────────────────────────────────────


def _build_cover(wb: Workbook, director: dict, period: str, period_end: str) -> None:
    ws = wb.create_sheet("Cover")
    ws["A1"] = director.get("name") or "(unknown director)"
    ws["A1"].font = Font(name="Arial", size=24, bold=True, color=BRAND_PRIMARY)
    ws["A2"] = director.get("scope_label") or ""
    ws["A2"].font = Font(name="Arial", size=14, italic=True, color=BRAND_SECONDARY)
    ws["A4"] = f"{period} LAND review (formula-driven model)"
    ws["A4"].font = Font(name="Arial", size=18, bold=True, color=BRAND_SECONDARY)
    ws["A5"] = f"Period end: {period_end}"
    ws["A5"].font = Font(name="Arial", size=11, color=BRAND_SECONDARY)
    ws["A6"] = f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    ws["A6"].font = Font(name="Arial", size=11, color=BRAND_SECONDARY)
    ws["A8"] = (
        "All KPIs on this workbook reference the Data sheet via Excel formulas. "
        "Click any cell to inspect its computation. Period boundaries and rule "
        "thresholds live in Parameters; stage labels live in Stages. "
        "Aggregate-only per SimCorp AI Code of Conduct §8."
    )
    ws["A8"].font = Font(name="Arial", size=10, italic=True, color=BRAND_GRAY)
    ws["A8"].alignment = Alignment(wrap_text=True)
    ws.column_dimensions["A"].width = 100
    ws.row_dimensions[1].height = 36
    ws.row_dimensions[4].height = 28
    ws.row_dimensions[8].height = 50


def _build_parameters(wb: Workbook, period_start: date, period_end: date) -> None:
    """Single source of truth for thresholds + period boundaries.

    Each row gets a workbook-scoped named range so downstream formulas read
    e.g. =SUMIFS(..., Data[CloseDate], ">="&period_start) and changing the
    period in this sheet propagates everywhere.
    """
    ws = wb.create_sheet("Parameters")
    _set_header(ws, 1, ["Parameter", "Value", "Description"])

    # (param_name, value, description) — name MUST be a valid Excel name.
    params = [
        ("period_start", period_start, "First day of the review period (inclusive)"),
        ("period_end", period_end, "First day AFTER the review period (exclusive bound)"),
        ("today", date.today(), "Snapshot date — used by aging buckets"),
        ("zombie_age_days", 730, "Open opps older than this are 'zombie' candidates"),
        ("activity_drought_days", 30, "No-activity threshold for current-Q closing opps"),
        ("late_stage_floor_pct", 0.30, "Minimum % of pipe in Stage 5+6 (else risk flag)"),
        ("simcorp_one_floor_pct", 0.30, "Minimum SP attach rate (else risk flag)"),
        ("commercial_approval_eur", 500_000, "Commercial Approval gate threshold (Expand)"),
        ("eur_to_meur", 1_000_000, "Display divisor for mEUR rendering"),
    ]
    for i, (name, value, desc) in enumerate(params, start=2):
        ws.cell(row=i, column=1, value=name).font = Font(bold=True)
        c = ws.cell(row=i, column=2, value=value)
        # Inputs colored blue per FAST/ICAEW convention — every value cell
        # in Parameters is a hardcoded input that drives the model.
        c.font = Font(color=INPUT_COLOR, bold=True)
        if isinstance(value, date):
            c.number_format = "yyyy-mm-dd"
        elif isinstance(value, float):
            c.number_format = "0.00%"
        else:
            c.number_format = "#,##0"
        ws.cell(row=i, column=3, value=desc)
        # Workbook-scoped named range (lets formulas use plain `period_start`).
        _add_named_range(wb, name, f"Parameters!$B${i}")

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 60


def _build_stages(wb: Workbook) -> None:
    """Stage reference table — sourced from the canonical knowledge graph
    so excel_companion.STAGES_8 and this sheet can never drift."""
    ws = wb.create_sheet("Stages")
    _set_header(ws, 1, ["#", "StageName", "Description", "TypicalRole"])
    # Stage reference is input-style (hardcoded values from the knowledge
    # graph) — color blue so it's visually distinct from formula sheets.
    input_font = Font(color=INPUT_COLOR)
    for i, s in enumerate(GRAPH.stages, start=2):
        ws.cell(row=i, column=1, value=s.number).font = input_font
        ws.cell(row=i, column=2, value=f"{s.number} - {s.name}").font = input_font
        ws.cell(row=i, column=3, value=s.description).font = input_font
        ws.cell(row=i, column=4, value=s.typical_role or "").font = input_font
    ws.column_dimensions["A"].width = 4
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 80
    ws.column_dimensions["D"].width = 28


def _build_data(wb: Workbook, raw_opps: list[dict]) -> None:
    """The single source of truth: one row per FX-converted open opp in
    director scope. Every analytical sheet's formulas reference this sheet.
    """
    ws = wb.create_sheet("Data")
    headers = [c[0] for c in DATA_COLUMNS]
    _set_header(ws, 1, headers)

    # Every Data cell is an INPUT (hardcoded source value) — blue per
    # FAST/ICAEW convention. Stakeholders looking at any analytical sheet
    # know that following a formula back here lands on hardcoded values.
    input_font = Font(color=INPUT_COLOR)
    for row_idx, opp in enumerate(raw_opps, start=2):
        for col_idx, (col_name, col_type) in enumerate(DATA_COLUMNS, start=1):
            val = opp.get(col_name)
            cell = ws.cell(row=row_idx, column=col_idx, value=val if val != "" else None)
            cell.font = input_font
            if col_type == "date" and isinstance(val, str) and len(val) >= 10:
                # Excel-friendly date — let openpyxl coerce ISO strings.
                try:
                    cell.value = date.fromisoformat(val[:10])
                    cell.number_format = "yyyy-mm-dd"
                except ValueError:
                    pass
            elif col_type == "number" and val is not None:
                cell.number_format = "#,##0.00"

    n_rows = len(raw_opps)
    last_row = n_rows + 1 if n_rows > 0 else 2
    last_col = get_column_letter(len(DATA_COLUMNS))

    # Workbook-scoped named ranges per column (e.g., Data_ARR_EUR ->
    # 'Data!$J$2:$J$<last>'). Downstream formulas use these instead of
    # raw cell ranges so adding rows is a one-edit change.
    for col_idx, (col_name, _) in enumerate(DATA_COLUMNS, start=1):
        col_letter = get_column_letter(col_idx)
        ref = f"Data!${col_letter}$2:${col_letter}${last_row}"
        _add_named_range(wb, f"Data_{col_name}", ref)

    # Total range covering all data rows for COUNTA-style queries.
    _add_named_range(wb, "Data_All", f"Data!$A$2:${last_col}${last_row}")

    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 22
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 12
    ws.column_dimensions["F"].width = 24
    ws.column_dimensions["G"].width = 36
    ws.column_dimensions["H"].width = 18
    ws.column_dimensions["I"].width = 14
    ws.column_dimensions["J"].width = 14
    ws.column_dimensions["K"].width = 14
    ws.freeze_panes = "A2"


def _build_pipeline_total(wb: Workbook, period: str) -> None:
    """Headline 3-row block: closeable / beyond / renewal. Every value is
    a SUMIFS against Data + period_start/end. Click any cell to trace."""
    ws = wb.create_sheet("Pipeline_Total")
    _set_header(ws, 1, ["KPI", "Value (EUR)", "Value (mEUR)", "Source formula"])

    # All B/C cells are XREF formulas — they reference Data_* and
    # Parameters named ranges (cross-sheet). Color green per convention.
    xref_font = Font(color=XREF_COLOR, bold=True)
    xref_font_normal = Font(color=XREF_COLOR)
    note_font = Font(italic=True, color=BRAND_GRAY)

    # Row 2: CFQ closeable Land+Expand
    ws.cell(row=2, column=1, value=f"{period} closeable Land+Expand ARR").font = Font(bold=True)
    c = ws.cell(
        row=2,
        column=2,
        value=(
            '=SUMIFS(Data_ARR_EUR, Data_Type, "Land", '
            'Data_CloseDate, ">="&period_start, '
            'Data_CloseDate, "<"&period_end) '
            '+ SUMIFS(Data_ARR_EUR, Data_Type, "Expand", '
            'Data_CloseDate, ">="&period_start, '
            'Data_CloseDate, "<"&period_end)'
        ),
    )
    c.number_format = "#,##0"
    c.font = xref_font
    c2 = ws.cell(row=2, column=3, value="=B2/eur_to_meur")
    c2.number_format = "#,##0.0"
    c2.font = xref_font
    ws.cell(
        row=2,
        column=4,
        value="SUMIFS over Data: Type IN (Land,Expand) AND period_start ≤ CloseDate < period_end",
    ).font = note_font

    # Row 3: Beyond CFQ
    ws.cell(row=3, column=1, value=f"Open Land+Expand beyond {period}")
    c = ws.cell(
        row=3,
        column=2,
        value=(
            '=SUMIFS(Data_ARR_EUR, Data_Type, "Land", Data_CloseDate, ">="&period_end) '
            '+ SUMIFS(Data_ARR_EUR, Data_Type, "Expand", Data_CloseDate, ">="&period_end)'
        ),
    )
    c.number_format = "#,##0"
    c.font = xref_font_normal
    c2 = ws.cell(row=3, column=3, value="=B3/eur_to_meur")
    c2.number_format = "#,##0.0"
    c2.font = xref_font_normal
    ws.cell(
        row=3,
        column=4,
        value="Out-of-quarter pipe; context only, not in CFQ forecast",
    ).font = note_font

    # Row 4: Renewal ACV
    ws.cell(row=4, column=1, value=f"{period} renewal ACV").font = Font(bold=True)
    c = ws.cell(
        row=4,
        column=2,
        value=(
            '=SUMIFS(Data_ACV_EUR, Data_Type, "Renewal", '
            'Data_CloseDate, ">="&period_start, '
            'Data_CloseDate, "<"&period_end)'
        ),
    )
    c.number_format = "#,##0"
    c.font = xref_font
    c2 = ws.cell(row=4, column=3, value="=B4/eur_to_meur")
    c2.number_format = "#,##0.0"
    c2.font = xref_font
    ws.cell(
        row=4,
        column=4,
        value="SUMIFS over Data: Type=Renewal AND period_start ≤ CloseDate < period_end",
    ).font = note_font

    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 70
    ws.freeze_panes = "A2"


def _build_pipeline_by_stage(wb: Workbook, period: str) -> None:
    """8 stages × {ARR, count} via SUMIFS/COUNTIFS. Stage label comes from
    the Stages reference sheet, so changes there propagate automatically."""
    ws = wb.create_sheet("Pipeline_By_Stage")
    _set_header(ws, 1, [f"Stage ({period} closeable)", "ARR (EUR)", "ARR (mEUR)", "# Opps"])
    # All per-stage cells are XREF (reference Stages + Data + Parameters
    # named ranges). TOTAL row is a same-sheet SUM → LOCAL color.
    xref_font = Font(color=XREF_COLOR)
    local_bold = Font(color=LOCAL_COLOR, bold=True)
    for i, _s in enumerate(GRAPH.stages, start=2):
        # Stage label pulled from Stages sheet (Stages!B<i>) — cross-sheet.
        ws.cell(row=i, column=1, value=f"=Stages!B{i}").font = xref_font
        c = ws.cell(
            row=i,
            column=2,
            value=(
                f'=SUMIFS(Data_ARR_EUR, Data_Type, "Land", Data_StageName, Stages!B{i}, '
                'Data_CloseDate, ">="&period_start, Data_CloseDate, "<"&period_end) '
                f'+ SUMIFS(Data_ARR_EUR, Data_Type, "Expand", Data_StageName, Stages!B{i}, '
                'Data_CloseDate, ">="&period_start, Data_CloseDate, "<"&period_end)'
            ),
        )
        c.number_format = "#,##0"
        c.font = xref_font
        c2 = ws.cell(row=i, column=3, value=f"=B{i}/eur_to_meur")
        c2.number_format = "#,##0.0"
        c2.font = xref_font
        c3 = ws.cell(
            row=i,
            column=4,
            value=(
                f'=COUNTIFS(Data_Type, "Land", Data_StageName, Stages!B{i}, '
                'Data_CloseDate, ">="&period_start, Data_CloseDate, "<"&period_end) '
                f'+ COUNTIFS(Data_Type, "Expand", Data_StageName, Stages!B{i}, '
                'Data_CloseDate, ">="&period_start, Data_CloseDate, "<"&period_end)'
            ),
        )
        c3.font = xref_font
    # Total row — same-sheet sum → LOCAL color.
    last_stage_row = 1 + len(GRAPH.stages)
    total_row = last_stage_row + 1
    ws.cell(row=total_row, column=1, value="TOTAL").font = local_bold
    c = ws.cell(row=total_row, column=2, value=f"=SUM(B2:B{last_stage_row})")
    c.number_format = "#,##0"
    c.font = local_bold
    c = ws.cell(row=total_row, column=3, value=f"=B{total_row}/eur_to_meur")
    c.number_format = "#,##0.0"
    c.font = local_bold
    ws.cell(row=total_row, column=4, value=f"=SUM(D2:D{last_stage_row})").font = local_bold

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 10
    ws.freeze_panes = "A2"


def _build_pipeline_aging(wb: Workbook) -> None:
    """5 age buckets via SUMPRODUCT on Data + bucket bounds. Age is computed
    relative to `today` named cell so re-snapshotting just bumps Parameters."""
    ws = wb.create_sheet("Pipeline_Aging")
    _set_header(ws, 1, ["Age bucket (days since CreatedDate)", "Min", "Max", "ARR (EUR)", "# Opps"])

    buckets = [
        ("0-30 days", 0, 30),
        ("31-90 days", 31, 90),
        ("91-180 days", 91, 180),
        ("181-365 days", 181, 365),
        ("366-730 days", 366, 730),
        ("> 730 days (zombie)", 731, 99999),
    ]
    # Min/Max bucket bounds are inputs (blue); SUMPRODUCT formulas are XREF
    # (they reference Data_* + the `today` named cell on Parameters).
    input_font = Font(color=INPUT_COLOR)
    xref_font = Font(color=XREF_COLOR)
    for i, (label, lo, hi) in enumerate(buckets, start=2):
        ws.cell(row=i, column=1, value=label)
        ws.cell(row=i, column=2, value=lo).font = input_font
        ws.cell(row=i, column=3, value=hi).font = input_font
        # ARR: SUMPRODUCT of Type IN (Land,Expand) AND age in [lo, hi]
        c = ws.cell(
            row=i,
            column=4,
            value=(
                "=SUMPRODUCT("
                '((Data_Type="Land")+(Data_Type="Expand"))'
                f"*((today-Data_CreatedDate)>=B{i})"
                f"*((today-Data_CreatedDate)<=C{i})"
                "*Data_ARR_EUR)"
            ),
        )
        c.number_format = "#,##0"
        c.font = xref_font
        c2 = ws.cell(
            row=i,
            column=5,
            value=(
                "=SUMPRODUCT("
                '((Data_Type="Land")+(Data_Type="Expand"))'
                f"*((today-Data_CreatedDate)>=B{i})"
                f"*((today-Data_CreatedDate)<=C{i}))"
            ),
        )
        c2.font = xref_font

    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 8
    ws.column_dimensions["C"].width = 8
    ws.column_dimensions["D"].width = 16
    ws.column_dimensions["E"].width = 10
    ws.freeze_panes = "A2"


def _build_by_owner(wb: Workbook, snapshot: dict | None) -> None:
    """One row per Owner.Name in scope, with formula-driven aggregates.
    Owner names are written from the snapshot (deduped) but ARR / counts
    are SUMIFS/COUNTIFS so totals tie back to Data."""
    ws = wb.create_sheet("By_Owner")
    _set_header(ws, 1, ["Owner", "Open ARR (Land+Expand, all CloseDates)", "# Opps"])

    raw_opps = (snapshot or {}).get("raw_opps") or []
    owners = sorted(
        {
            (r.get("OwnerName") or "(unknown)")
            for r in raw_opps
            if r.get("Type") in ("Land", "Expand")
        }
    )

    # All formula cells reference Data_* — XREF (green).
    xref_font = Font(color=XREF_COLOR)
    for i, owner in enumerate(owners, start=2):
        ws.cell(row=i, column=1, value=owner)
        # Quote owner with " for SUMIFS literal — escape any embedded quotes.
        owner_lit = owner.replace('"', '""')
        c = ws.cell(
            row=i,
            column=2,
            value=(
                f'=SUMIFS(Data_ARR_EUR, Data_OwnerName, "{owner_lit}", Data_Type, "Land") '
                f'+ SUMIFS(Data_ARR_EUR, Data_OwnerName, "{owner_lit}", Data_Type, "Expand")'
            ),
        )
        c.number_format = "#,##0"
        c.font = xref_font
        c2 = ws.cell(
            row=i,
            column=3,
            value=(
                f'=COUNTIFS(Data_OwnerName, "{owner_lit}", Data_Type, "Land") '
                f'+ COUNTIFS(Data_OwnerName, "{owner_lit}", Data_Type, "Expand")'
            ),
        )
        c2.font = xref_font

    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 10
    ws.freeze_panes = "A2"


def _build_methodology(wb: Workbook) -> None:
    """Documents the model contract: how to read the formulas, which
    cells are the inputs, how to extend the model."""
    ws = wb.create_sheet("Methodology")
    ws["A1"] = "Methodology — formula-driven model"
    ws["A1"].font = Font(bold=True, size=14, color=BRAND_PRIMARY)

    blocks = [
        (
            "Single source of truth",
            "All analytical sheets reference Data via named ranges (Data_ARR_EUR, "
            "Data_Type, Data_StageName, Data_CloseDate, Data_OwnerName, etc.). To "
            "trace any KPI, click the cell and inspect the formula — every input "
            "is a Data_* range or a Parameters cell.",
        ),
        (
            "Period boundaries",
            "Parameters!B2 (period_start) and Parameters!B3 (period_end) drive the "
            "CFQ filter on every analytical sheet. Convention: period_end is the "
            "FIRST DAY AFTER the period (used as a strict upper bound: "
            "CloseDate < period_end). Editing these cells reflows every KPI.",
        ),
        (
            "Stage labels",
            "Stages!B2:B9 holds the canonical stage names (sourced from "
            "scripts/sales_process_graph.py). Pipeline_By_Stage references them "
            "with =Stages!B<row>, so renaming a stage in Stages updates the "
            "Pipeline_By_Stage labels too.",
        ),
        (
            "FX correctness",
            "Data_ARR_EUR and Data_ACV_EUR are FX-converted at the per-record level "
            "by Salesforce's convertCurrency() before being written to the Data "
            "sheet. SUMIFS over these columns is therefore FX-correct.",
        ),
        (
            "Phase 2 sheets (still precomputed)",
            "Top deals, weighted forecast, retention, action items, regional "
            "benchmarks, and trend sheets are still in the legacy companion xlsx "
            "(land.xlsx). They migrate to formulas as auditability needs surface.",
        ),
    ]
    row = 3
    for title, body in blocks:
        ws.cell(row=row, column=1, value=title).font = Font(bold=True, size=12)
        row += 1
        c = ws.cell(row=row, column=1, value=body)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[row].height = max(30, 15 * (1 + len(body) // 100))
        row += 2

    # Color-coding key — FAST/ICAEW convention. Same scheme as Anthropic's
    # official xlsx Agent Skill, so stakeholders moving between Claude-
    # generated workbooks and ours see one auditability scheme.
    ws.cell(row=row, column=1, value="Color-coding key").font = Font(bold=True, size=12)
    row += 1
    key_rows = [
        (
            "Blue",
            INPUT_COLOR,
            "Hardcoded input — Data sheet rows, Parameters cells, Stages reference",
        ),
        ("Black", LOCAL_COLOR, "Formula referencing only its own sheet (e.g., TOTAL row =SUM)"),
        ("Green", XREF_COLOR, "Formula crossing sheets — references Data_*, Parameters, or Stages"),
        ("Red", EXT_COLOR, "Formula referencing an external workbook — never used in this model"),
    ]
    for label, color, desc in key_rows:
        ws.cell(row=row, column=1, value=label).font = Font(bold=True, color=color)
        ws.cell(row=row, column=2, value=desc).alignment = Alignment(vertical="top")
        row += 1

    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 100


def _apply_print_setup(wb: Workbook, director: dict, period: str) -> None:
    for ws in wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.print_options.horizontalCentered = True
        ws.page_margins = PageMargins(left=0.5, right=0.5, top=0.6, bottom=0.6)
        if ws.sheet_properties.pageSetUpPr is not None:
            ws.sheet_properties.pageSetUpPr.fitToPage = True
        try:
            d_name = director.get("name") or ""
            if ws.oddHeader is not None:
                ws.oddHeader.left.text = f"{d_name} | {period} | model"
                ws.oddHeader.right.text = ws.title
            if ws.oddFooter is not None:
                ws.oddFooter.center.text = "Aggregate-only per SimCorp AI Code of Conduct §8"
        except Exception:
            pass
