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
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.table import (  # noqa: F401  # formatter strips otherwise
    Table,
    TableStyleInfo,
)

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
    ("Industry", "string"),
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
    backtest: dict | None = None,
) -> None:
    """Build the formula-driven model workbook.

    Args:
        envelope: trends.json envelope (locked, schema_version=2)
        out_path: where to write the xlsx
        snapshot: per-director snapshot from pull_director_snapshot. The
            'raw_opps' key is the seed for the Data sheet. If absent, the
            Data sheet is empty and downstream formulas resolve to zero.
        backtest: parsed state/forecast_backtest_q4.json — used by
            Weighted_Forecast sheet to seed the org-wide stage forward
            rates as INPUT (blue) cells. Stakeholders can edit these to
            see how the weighted forecast moves.
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
    # Closed-history raw Data sheets — auditable inputs for ARR_Roll,
    # Trend_MoM/QoQ, Retention, Wins_Losses_QTD. Must sit BEFORE the
    # analytical sheets so their named ranges exist by the time we wire
    # SUMIFS criteria.
    _build_closed_cfq(wb, snapshot)
    _build_closed_won_6mo(wb, snapshot)
    _build_renewals_12mo(wb, snapshot)
    _build_pipeline_total(wb, period)
    _build_pipe_movement(wb, snapshot, period)
    _build_pipeline_by_stage(wb, period)
    _build_pipeline_aging(wb)
    _build_by_owner(wb, snapshot)
    _build_pivots(wb, snapshot)
    _build_velocity(wb)
    _build_concentration(wb, snapshot, period)
    _build_weighted_forecast(wb, backtest)
    # Formula-driven analytical sheets that consume the closed-history
    # named ranges above. Order doesn't matter among these except
    # Trend_MoM/QoQ which reference ARR_Roll!B<n> — keep ARR_Roll first.
    _build_arr_roll(wb)
    _build_trend_mom(wb)
    _build_trend_qoq(wb)
    _build_retention(wb)
    _build_wins_losses_qtd(wb)
    # Phase 3: Competitive_Pressure — needs Lost_to_Competitor__r.Name in
    # the SF queries before it can be wired here. Tracked separately.
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

    # Convert Data to a real Excel Table (`tblData`) — unlocks the
    # Insert > PivotTable workflow for stakeholders without code, and
    # gives them tblData[ARR_EUR] structured-reference syntax in any
    # ad-hoc formulas they write.
    if n_rows > 0:
        table_ref = f"A1:${last_col}${last_row}".replace("$", "")
        # Use a recognizable name; openpyxl rejects names containing spaces.
        table = Table(displayName="tblData", ref=table_ref)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        ws.add_table(table)

    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 22
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 12
    ws.column_dimensions["F"].width = 24
    ws.column_dimensions["G"].width = 36
    ws.column_dimensions["H"].width = 18
    ws.column_dimensions["I"].width = 18
    ws.column_dimensions["J"].width = 14
    ws.column_dimensions["K"].width = 14
    ws.column_dimensions["L"].width = 14
    ws.freeze_panes = "A2"


# ──────────────────────────────────────────────────────────────────────────
# Closed-history Data sheets — auditable inputs for ARR_Roll / Trend_MoM /
# Trend_QoQ / Retention / Wins_Losses_QTD. Each mirrors `_build_data`'s
# pattern: header row, INPUT (blue) cells, an Excel Table for ad-hoc pivots,
# and per-column workbook-scoped named ranges so analytical sheets can
# write SUMIFS that survive row-count changes.
# ──────────────────────────────────────────────────────────────────────────


# 10 columns shared by all three closed-history sheets — matches the dict
# shape produced by `_flat_closed` in scripts/land_brief.py.
CLOSED_HISTORY_COLUMNS = [
    ("Id", "string"),
    ("Name", "string"),
    ("Type", "string"),
    ("StageName", "string"),
    ("IsWon", "bool"),
    ("CloseDate", "date"),
    ("OwnerName", "string"),
    ("AccountName", "string"),
    ("ARR_EUR", "number"),
    ("ACV_EUR", "number"),
]


def _build_closed_history_sheet(
    wb: Workbook,
    *,
    sheet_name: str,
    table_name: str,
    name_prefix: str,
    rows: list[dict],
) -> None:
    """Shared writer for the three closed-history raw Data sheets.

    Writes header + INPUT-blue cells, registers per-column named ranges
    (e.g., ClosedCFQ_ARR_EUR -> 'Data_Closed_CFQ!$I$2:$I$<last>') and
    converts the data range to an Excel Table for ad-hoc pivot use. The
    sheet is empty-safe: when `rows` is empty we still write the header
    and register named ranges pointing at row 2 so SUMIFS in analytical
    sheets resolve to zero rather than #REF!.
    """
    ws = wb.create_sheet(sheet_name)
    headers = [c[0] for c in CLOSED_HISTORY_COLUMNS]
    _set_header(ws, 1, headers)

    input_font = Font(color=INPUT_COLOR)
    for row_idx, opp in enumerate(rows, start=2):
        for col_idx, (col_name, col_type) in enumerate(CLOSED_HISTORY_COLUMNS, start=1):
            val = opp.get(col_name)
            cell = ws.cell(row=row_idx, column=col_idx, value=val if val != "" else None)
            cell.font = input_font
            if col_type == "date" and isinstance(val, str) and len(val) >= 10:
                # Mirror _build_data: parse ISO date so Excel stores a real
                # date serial (required for SUMIFS(..., ">="&DATE(y,m,1))).
                try:
                    cell.value = date.fromisoformat(val[:10])
                    cell.number_format = "yyyy-mm-dd"
                except ValueError:
                    pass
            elif col_type == "number" and val is not None:
                cell.number_format = "#,##0.00"
            elif col_type == "bool":
                # openpyxl serializes Python bool as Excel TRUE/FALSE;
                # SUMIFS criteria of `, IsWon, TRUE` will match.
                cell.value = bool(val) if val is not None else False

    n_rows = len(rows)
    last_row = n_rows + 1 if n_rows > 0 else 2
    last_col = get_column_letter(len(CLOSED_HISTORY_COLUMNS))

    # Per-column named ranges: <name_prefix>_<col_name>. These let the
    # analytical sheets reference e.g. ClosedCFQ_ARR_EUR without binding
    # to absolute cell ranges that would drift on data refresh.
    for col_idx, (col_name, _) in enumerate(CLOSED_HISTORY_COLUMNS, start=1):
        col_letter = get_column_letter(col_idx)
        ref = f"{sheet_name}!${col_letter}$2:${col_letter}${last_row}"
        _add_named_range(wb, f"{name_prefix}_{col_name}", ref)

    # Excel Table — only valid when there's at least one data row. Mirrors
    # the guard in _build_data.
    if n_rows > 0:
        table_ref = f"A1:{last_col}{last_row}"
        table = Table(displayName=table_name, ref=table_ref)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        ws.add_table(table)

    # Column widths — match `_build_data` style for legibility.
    widths = [20, 36, 10, 22, 8, 12, 24, 36, 14, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def _build_closed_cfq(wb: Workbook, snapshot: dict | None) -> None:
    """Closed-this-Q opps (won + lost; Land/Expand/Renewal). Source for
    Wins_Losses_QTD."""
    rows = (snapshot or {}).get("closed_cfq_rows") or []
    _build_closed_history_sheet(
        wb,
        sheet_name="Data_Closed_CFQ",
        table_name="tblClosedCFQ",
        name_prefix="ClosedCFQ",
        rows=rows,
    )


def _build_closed_won_6mo(wb: Workbook, snapshot: dict | None) -> None:
    """Closed-WON Land+Expand opps last 180 days. Source for ARR_Roll +
    Trend_MoM/QoQ."""
    rows = (snapshot or {}).get("closed_won_6mo_rows") or []
    _build_closed_history_sheet(
        wb,
        sheet_name="Data_Closed_Won_6mo",
        table_name="tblClosedWon6mo",
        name_prefix="ClosedWon6mo",
        rows=rows,
    )


def _build_renewals_12mo(wb: Workbook, snapshot: dict | None) -> None:
    """Closed Renewal opps last 365 days (won + lost). Source for the
    Retention GRR proxy."""
    rows = (snapshot or {}).get("closed_renewals_12mo_rows") or []
    _build_closed_history_sheet(
        wb,
        sheet_name="Data_Renewals_12mo",
        table_name="tblRenewals12mo",
        name_prefix="Renewals12mo",
        rows=rows,
    )


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


def _build_pipe_movement(wb: Workbook, snapshot: dict | None, period: str) -> None:
    """Bridge from prior-period closeable Land+Expand pipe to current.

    Six-row waterfall:
        opening (INPUT) + (new + advanced − slipped, residual) − won − lost
            = closing.
    Closing pulls from Pipeline_Total!B2 (the headline closeable L+E ARR);
    Won/Lost pull from Wins_Losses_QTD!C2/C3 (which themselves are SUMIFS
    over closed-CFQ rows). The "+ New + Advanced (residual)" row is a
    same-sheet plug computed as closing − opening + won + lost — it lumps
    new deals + advanced-into-CFQ + slipped-out together until the
    OpportunityFieldHistory-driven decomposition lands in Phase 2.

    Opening pipe comes from the prior monthly snapshot (Phase 2 plumbing
    in land_brief.py reads state/<period>/<director>/snapshot_prev.json
    and surfaces it on snapshot.pipe_movement_opening_arr). If no prior
    snapshot exists the opening is 0 and the residual bucket carries the
    full closing — flagged in the methodology row below the bridge.
    """
    ws = wb.create_sheet("Pipe_Movement")
    _set_header(ws, 1, ["Bucket", "ARR (EUR)", "Note"])

    opening = float((snapshot or {}).get("pipe_movement_opening_arr") or 0)
    has_prior = opening > 0

    input_font = Font(color=INPUT_COLOR, bold=True)
    xref_font = Font(color=XREF_COLOR, bold=True)
    local_font = Font(color=LOCAL_COLOR, bold=True)
    note_font = Font(italic=True, color=BRAND_GRAY)

    # Row 2: Opening pipe (INPUT — pulled from prior snapshot).
    ws.cell(row=2, column=1, value=f"Opening pipe (start of {period})")
    c = ws.cell(row=2, column=2, value=round(opening, 2))
    c.font = input_font
    c.number_format = "#,##0"
    ws.cell(
        row=2,
        column=3,
        value=(
            "Prior monthly snapshot — closeable L+E ARR"
            if has_prior
            else "(no prior snapshot — first run)"
        ),
    ).font = note_font

    # Row 3: New + Advanced (residual) — same-sheet plug. LOCAL black.
    # NOTE: row labels intentionally avoid leading +/=/- characters because
    # both Excel and the `formulas` recalc lib interpret a cell starting
    # with one of those as a formula expression. Prefix the bridge symbol
    # with ASCII text instead of leaving it as the first glyph.
    ws.cell(row=3, column=1, value="(+) New + Advanced (residual)")
    c = ws.cell(row=3, column=2, value="=B6-B2+B4+B5")
    c.font = local_font
    c.number_format = "#,##0"
    ws.cell(
        row=3,
        column=3,
        value=(
            "Residual: closing minus opening plus won plus lost. Lumps new "
            "deals + advanced-into-CFQ + slipped-out until Phase 2 OFH wiring."
        ),
    ).font = note_font

    # Row 4: Won this Q (Land+Expand) — XREF green.
    ws.cell(row=4, column=1, value="(-) Won this Q (Land+Expand)")
    c = ws.cell(row=4, column=2, value="=Wins_Losses_QTD!C2")
    c.font = xref_font
    c.number_format = "#,##0"
    ws.cell(
        row=4,
        column=3,
        value="From Wins_Losses_QTD!C2 (SUMIFS over closed-CFQ Land+Expand wins)",
    ).font = note_font

    # Row 5: Lost this Q (Land+Expand) — XREF green.
    ws.cell(row=5, column=1, value="(-) Lost this Q (Land+Expand)")
    c = ws.cell(row=5, column=2, value="=Wins_Losses_QTD!C3")
    c.font = xref_font
    c.number_format = "#,##0"
    ws.cell(
        row=5,
        column=3,
        value="From Wins_Losses_QTD!C3 (SUMIFS over closed-CFQ Land+Expand losses)",
    ).font = note_font

    # Row 6: Closing pipe (CFQ closeable) — XREF green, references the
    # headline. Bold to mark it as the bridge end-state.
    ws.cell(row=6, column=1, value=f"Closing pipe ({period} CFQ)").font = Font(bold=True)
    c = ws.cell(row=6, column=2, value="=Pipeline_Total!B2")
    c.font = xref_font
    c.number_format = "#,##0"
    ws.cell(
        row=6,
        column=3,
        value="From Pipeline_Total!B2 (headline closeable Land+Expand ARR)",
    ).font = note_font

    # Methodology caveat row — same style as _build_weighted_forecast.
    ws.cell(row=8, column=1, value="How to read this sheet").font = Font(
        bold=True, color=BRAND_PRIMARY
    )
    ws.cell(
        row=9,
        column=1,
        value=(
            "Opening pipe (B2) is read from the prior monthly snapshot if "
            "available (state/<period>/<director>/snapshot_prev.json); on "
            "the first run for a director it starts at 0 and the residual "
            "bucket (B3) carries the full closing figure. The 'New + "
            "Advanced (residual)' bucket is intentionally plug-style — it "
            "currently lumps new deals + advanced-into-CFQ + slipped-out "
            "together. Phase 2 will decompose it into discrete movements "
            "via OpportunityFieldHistory snapshots."
        ),
    ).font = note_font
    ws.cell(row=9, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[9].height = 60

    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 60
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


# ──────────────────────────────────────────────────────────────────────────
# Pivot-equivalent dynamic-array sheets
# ──────────────────────────────────────────────────────────────────────────


def _unique_sorted(seq, key=None):
    """Stable de-dup + sort. Empty values collapse to '(unset)'."""
    seen = []
    for s in seq:
        v = (s or "(unset)") if not callable(key) else key(s)
        if v not in seen:
            seen.append(v)
    return sorted(seen)


def _build_pivots(wb: Workbook, snapshot: dict | None) -> None:
    """Five pre-built cross-tabs over Data via SUMIFS. Row/column axes are
    derived in Python (deduped from raw_opps and written as INPUT cells —
    blue) so the model doesn't depend on dynamic-array Excel functions
    (UNIQUE/SORT) that older Excel can't evaluate. The matrix interior
    cells are SUMIFS — XREF green — and they reference Data_* named ranges
    so re-running re-aggregates without code changes.
    """
    ws = wb.create_sheet("Pivots")
    raw = (snapshot or {}).get("raw_opps") or []

    input_font = Font(color=INPUT_COLOR)
    xref_font = Font(color=XREF_COLOR)
    title_font = Font(bold=True, size=12, color=BRAND_PRIMARY)
    note_font = Font(italic=True, color=BRAND_GRAY)

    row = 1
    ws.cell(row=row, column=1, value="Pivot views — open Land+Expand pipeline").font = Font(
        bold=True, size=14, color=BRAND_PRIMARY
    )
    row += 1
    ws.cell(
        row=row,
        column=1,
        value=(
            "Each block is a pre-built cross-tab. Row + column headers are inputs "
            "(blue); matrix cells are SUMIFS over Data (green). To slice differently "
            "than the pre-builts here, click anywhere in the Data sheet and use "
            "Insert > PivotTable — the table is named tblData."
        ),
    ).font = note_font
    ws.cell(row=row, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[row].height = 36
    row += 2

    # ── Pivot 1: Stage × Industry (ARR, Land+Expand only) ──
    stages = [f"{s.number} - {s.name}" for s in GRAPH.stages]
    industries = _unique_sorted(
        r.get("Industry") for r in raw if r.get("Type") in ("Land", "Expand")
    )
    if industries:
        ws.cell(row=row, column=1, value="Stage × Industry — ARR (EUR)").font = title_font
        row += 1
        # Header row: empty + industries
        ws.cell(row=row, column=1, value="Stage").font = Font(bold=True)
        for j, ind in enumerate(industries, start=2):
            c = ws.cell(row=row, column=j, value=ind)
            c.font = Font(bold=True, color=INPUT_COLOR)
        # Stage rows
        for i, st in enumerate(stages, start=row + 1):
            ws.cell(row=i, column=1, value=st).font = input_font
            for j, ind in enumerate(industries, start=2):
                ind_lit = ind.replace('"', '""')
                st_lit = st.replace('"', '""')
                c = ws.cell(
                    row=i,
                    column=j,
                    value=(
                        f'=SUMIFS(Data_ARR_EUR, Data_Type, "Land", Data_StageName, "{st_lit}", '
                        f'Data_Industry, "{ind_lit}") '
                        f'+ SUMIFS(Data_ARR_EUR, Data_Type, "Expand", Data_StageName, "{st_lit}", '
                        f'Data_Industry, "{ind_lit}")'
                    ),
                )
                c.font = xref_font
                c.number_format = "#,##0"
        # Heat-map conditional formatting on the Stage × Industry matrix
        # interior (excludes row/col headers). think-cell on macOS lacks a
        # native heat-map; the runbook (docs/THINKCELL_SETUP.md) binds a
        # think-cell "Table with Formatting" to this range so the cells
        # render heat-map-like via the conditional fills below. SimCorp
        # brand-blue gradient: white (empty/zero) → pale blue (median) →
        # SimCorp primary (max).
        first_row = row + 1
        last_row = row + len(stages)
        last_col = get_column_letter(1 + len(industries))
        heatmap_rule = ColorScaleRule(
            start_type="min",
            start_color="FFFFFF",
            mid_type="percentile",
            mid_value=50,
            mid_color="A9C0E5",
            end_type="max",
            end_color="083EA7",
        )
        ws.conditional_formatting.add(f"B{first_row}:{last_col}{last_row}", heatmap_rule)
        row = row + 1 + len(stages) + 2

    # ── Pivot 2: Owner × Stage (count, Land+Expand) ──
    owners = _unique_sorted(r.get("OwnerName") for r in raw if r.get("Type") in ("Land", "Expand"))
    if owners:
        ws.cell(row=row, column=1, value="Owner × Stage — # Opps").font = title_font
        row += 1
        ws.cell(row=row, column=1, value="Owner").font = Font(bold=True)
        for j, st in enumerate(stages, start=2):
            ws.cell(row=row, column=j, value=st).font = Font(bold=True, color=INPUT_COLOR)
        for i, owner in enumerate(owners, start=row + 1):
            owner_lit = owner.replace('"', '""')
            ws.cell(row=i, column=1, value=owner).font = input_font
            for j, st in enumerate(stages, start=2):
                st_lit = st.replace('"', '""')
                c = ws.cell(
                    row=i,
                    column=j,
                    value=(
                        f'=COUNTIFS(Data_OwnerName, "{owner_lit}", Data_StageName, "{st_lit}", '
                        f'Data_Type, "Land") '
                        f'+ COUNTIFS(Data_OwnerName, "{owner_lit}", Data_StageName, "{st_lit}", '
                        f'Data_Type, "Expand")'
                    ),
                )
                c.font = xref_font
        row = row + 1 + len(owners) + 2

    # ── Pivot 3: Country × Type (ARR) ──
    countries = _unique_sorted(r.get("BillingCountry") for r in raw)
    types = ["Land", "Expand", "Renewal"]
    if countries:
        ws.cell(row=row, column=1, value="Country × Type — ARR / ACV (EUR)").font = title_font
        row += 1
        ws.cell(row=row, column=1, value="Country").font = Font(bold=True)
        for j, t in enumerate(types, start=2):
            ws.cell(row=row, column=j, value=t).font = Font(bold=True, color=INPUT_COLOR)
        for i, country in enumerate(countries, start=row + 1):
            country_lit = country.replace('"', '""')
            ws.cell(row=i, column=1, value=country).font = input_font
            for j, t in enumerate(types, start=2):
                # Renewal uses ACV column; Land/Expand use ARR column.
                value_range = "Data_ACV_EUR" if t == "Renewal" else "Data_ARR_EUR"
                c = ws.cell(
                    row=i,
                    column=j,
                    value=(
                        f'=SUMIFS({value_range}, Data_BillingCountry, "{country_lit}", '
                        f'Data_Type, "{t}")'
                    ),
                )
                c.font = xref_font
                c.number_format = "#,##0"
        row = row + 1 + len(countries) + 2

    # ── Pivot 4: Top-10 Accounts × Stage (ARR, Land+Expand) ──
    # Predetermine top-10 accounts in Python by total open L+E ARR
    # (input names in blue; SUMIFS for the matrix in green).
    acct_totals: dict[str, float] = {}
    for r in raw:
        if r.get("Type") not in ("Land", "Expand"):
            continue
        n = r.get("AccountName") or "(unknown)"
        acct_totals[n] = acct_totals.get(n, 0.0) + float(r.get("ARR_EUR") or 0)
    top_accounts = sorted(acct_totals.items(), key=lambda kv: kv[1], reverse=True)[:10]
    if top_accounts:
        ws.cell(row=row, column=1, value="Top-10 Accounts × Stage — ARR (EUR)").font = title_font
        row += 1
        ws.cell(row=row, column=1, value="Account").font = Font(bold=True)
        for j, st in enumerate(stages, start=2):
            ws.cell(row=row, column=j, value=st).font = Font(bold=True, color=INPUT_COLOR)
        for i, (acct, _total) in enumerate(top_accounts, start=row + 1):
            acct_lit = acct.replace('"', '""')
            ws.cell(row=i, column=1, value=acct).font = input_font
            for j, st in enumerate(stages, start=2):
                st_lit = st.replace('"', '""')
                c = ws.cell(
                    row=i,
                    column=j,
                    value=(
                        f'=SUMIFS(Data_ARR_EUR, Data_AccountName, "{acct_lit}", '
                        f'Data_StageName, "{st_lit}", Data_Type, "Land") '
                        f'+ SUMIFS(Data_ARR_EUR, Data_AccountName, "{acct_lit}", '
                        f'Data_StageName, "{st_lit}", Data_Type, "Expand")'
                    ),
                )
                c.font = xref_font
                c.number_format = "#,##0"
        row = row + 1 + len(top_accounts) + 2

    # ── Pivot 5: Stage × Quarter (ARR, Land+Expand by CloseDate quarter) ──
    # Quarters derived from CloseDate values present in the data; capped
    # to a reasonable forward window (current year + next year quarters).
    quarters: list[str] = []
    for r in raw:
        if r.get("Type") not in ("Land", "Expand"):
            continue
        cd = r.get("CloseDate") or ""
        if len(cd) >= 7:
            try:
                y, m = int(cd[:4]), int(cd[5:7])
                qk = f"{y}-Q{(m - 1) // 3 + 1}"
                if qk not in quarters:
                    quarters.append(qk)
            except ValueError:
                pass
    quarters = sorted(quarters)[:8]  # cap at 8 forward quarters
    if quarters:
        ws.cell(
            row=row, column=1, value="Stage × Quarter (CloseDate) — ARR (EUR)"
        ).font = title_font
        row += 1
        ws.cell(row=row, column=1, value="Stage").font = Font(bold=True)
        for j, q in enumerate(quarters, start=2):
            ws.cell(row=row, column=j, value=q).font = Font(bold=True, color=INPUT_COLOR)
        for i, st in enumerate(stages, start=row + 1):
            ws.cell(row=i, column=1, value=st).font = input_font
            st_lit = st.replace('"', '""')
            for j, q in enumerate(quarters, start=2):
                qy, qn = q.split("-Q")
                qm_start = (int(qn) - 1) * 3 + 1
                qm_end = qm_start + 3
                qend_year = int(qy) + (1 if qm_end > 12 else 0)
                qend_month = qm_end if qm_end <= 12 else 1
                q_start = f"DATE({qy},{qm_start},1)"
                q_end = f"DATE({qend_year},{qend_month},1)"
                c = ws.cell(
                    row=i,
                    column=j,
                    value=(
                        f'=SUMIFS(Data_ARR_EUR, Data_Type, "Land", Data_StageName, "{st_lit}", '
                        f'Data_CloseDate, ">="&{q_start}, Data_CloseDate, "<"&{q_end}) '
                        f'+ SUMIFS(Data_ARR_EUR, Data_Type, "Expand", Data_StageName, "{st_lit}", '
                        f'Data_CloseDate, ">="&{q_start}, Data_CloseDate, "<"&{q_end})'
                    ),
                )
                c.font = xref_font
                c.number_format = "#,##0"

    ws.column_dimensions["A"].width = 32
    for col in range(2, 16):
        ws.column_dimensions[get_column_letter(col)].width = 18


def _build_velocity(wb: Workbook) -> None:
    """Stage age proxy via CreatedDate (no OFH today). Per stage: avg age
    of open L+E opps + count >60d + count >180d. Honest about the proxy:
    age is opp lifetime, NOT time-in-current-stage. A young deal that
    sat in early stages and just advanced shows the same age as a deal
    that's been in this stage for months."""
    ws = wb.create_sheet("Velocity")
    _set_header(
        ws,
        1,
        ["Stage", "# Open opps", "Avg age (days)", "# > 60 days old", "# > 180 days old"],
    )
    ws.cell(row=2, column=1, value="").font = Font()  # spacer for caveat
    ws.cell(
        row=1,
        column=6,
        value=(
            "Caveat: 'age' is days since CreatedDate, NOT time in current stage. "
            "True time-in-stage requires OpportunityFieldHistory wiring (deferred)."
        ),
    ).font = Font(italic=True, color=BRAND_GRAY)

    xref_font = Font(color=XREF_COLOR)
    input_font = Font(color=INPUT_COLOR)

    # Threshold inputs (so a stakeholder can edit and re-recompute).
    ws.cell(row=2, column=4, value=60).font = input_font
    ws.cell(row=2, column=5, value=180).font = input_font
    # Stage rows
    for i, s in enumerate(GRAPH.stages, start=3):
        st_label = f"{s.number} - {s.name}"
        st_lit = st_label.replace('"', '""')
        ws.cell(row=i, column=1, value=st_label).font = input_font
        # Count of open L+E opps in this stage
        c = ws.cell(
            row=i,
            column=2,
            value=(
                f'=COUNTIFS(Data_Type, "Land", Data_StageName, "{st_lit}") '
                f'+ COUNTIFS(Data_Type, "Expand", Data_StageName, "{st_lit}")'
            ),
        )
        c.font = xref_font
        # Avg age — SUMPRODUCT trick (avoid div-by-zero)
        c = ws.cell(
            row=i,
            column=3,
            value=(
                "=IFERROR("
                f'SUMPRODUCT(((Data_Type="Land")+(Data_Type="Expand"))*(Data_StageName="{st_lit}")*(today-Data_CreatedDate))/B{i},'
                '"-")'
            ),
        )
        c.font = xref_font
        c.number_format = "#,##0"
        # Count > 60 days
        c = ws.cell(
            row=i,
            column=4,
            value=(
                "=SUMPRODUCT("
                f'((Data_Type="Land")+(Data_Type="Expand"))*(Data_StageName="{st_lit}")'
                f"*((today-Data_CreatedDate)>$D$2))"
            ),
        )
        c.font = xref_font
        # Count > 180 days
        c = ws.cell(
            row=i,
            column=5,
            value=(
                "=SUMPRODUCT("
                f'((Data_Type="Land")+(Data_Type="Expand"))*(Data_StageName="{st_lit}")'
                f"*((today-Data_CreatedDate)>$E$2))"
            ),
        )
        c.font = xref_font
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 18
    ws.column_dimensions["F"].width = 60
    ws.freeze_panes = "A3"


def _build_concentration(wb: Workbook, snapshot: dict | None, period: str) -> None:
    """Concentration risk — what share of pipeline sits in the top N
    accounts / top N owners. Single-deal-risk flag if any one open L+E
    deal exceeds 25% of the CFQ-closeable headline.

    Top-N values are seeded as INPUTS (Python pre-derives the ranking) so
    the model doesn't depend on dynamic-array LARGE+IF combinations that
    older Excel rejects. Ratios are XREF formulas referencing Data
    (so totals tie back even if the user edits values)."""
    ws = wb.create_sheet("Concentration")
    raw = (snapshot or {}).get("raw_opps") or []

    title_font = Font(bold=True, size=12, color=BRAND_PRIMARY)
    input_font = Font(color=INPUT_COLOR)
    xref_font = Font(color=XREF_COLOR)
    note_font = Font(italic=True, color=BRAND_GRAY)

    row = 1
    ws.cell(row=row, column=1, value="Concentration risk").font = Font(
        bold=True, size=14, color=BRAND_PRIMARY
    )
    row += 1
    ws.cell(
        row=row,
        column=1,
        value=(
            f"How concentrated is open Land+Expand pipeline in this director's "
            f"book? Single-deal flag fires if ANY one open L+E deal > 25% of "
            f"the {period} closeable forecast (Pipeline_Total!B2)."
        ),
    ).font = note_font
    ws.cell(row=row, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[row].height = 32
    row += 2

    # Single-deal risk: pull the largest open L+E ARR. Compare to total
    # open Land+Expand pipeline (CFQ + beyond) so the share is meaningful
    # regardless of whether the largest deal closes in CFQ.
    le_opps = [
        (r.get("AccountName") or "(unknown)", float(r.get("ARR_EUR") or 0))
        for r in raw
        if r.get("Type") in ("Land", "Expand")
    ]
    le_opps.sort(key=lambda kv: kv[1], reverse=True)
    largest_acct, largest_arr = le_opps[0] if le_opps else ("-", 0.0)

    ws.cell(row=row, column=1, value="Single-deal risk").font = title_font
    row += 1
    ws.cell(row=row, column=1, value="Largest open L+E deal — account").font = Font(bold=True)
    ws.cell(row=row, column=2, value=largest_acct).font = input_font
    row += 1
    ws.cell(row=row, column=1, value="Largest open L+E deal — ARR (EUR)").font = Font(bold=True)
    c = ws.cell(row=row, column=2, value=round(largest_arr, 2))
    c.font = input_font
    c.number_format = "#,##0"
    largest_arr_row = row
    row += 1
    ws.cell(row=row, column=1, value="Share of total open Land+Expand pipeline")
    # Denominator = Pipeline_Total CFQ closeable + beyond-CFQ. Both live
    # on Pipeline_Total!B2 and !B3 respectively.
    c = ws.cell(
        row=row,
        column=2,
        value=(f"=IFERROR(B{largest_arr_row}/(Pipeline_Total!$B$2+Pipeline_Total!$B$3),0)"),
    )
    c.font = xref_font
    c.number_format = "0.0%"
    share_row = row
    row += 1
    ws.cell(row=row, column=1, value="25% threshold tripped?")
    c = ws.cell(
        row=row,
        column=2,
        value=f'=IF(B{share_row}>0.25,"YES — single-deal risk","no")',
    )
    c.font = xref_font
    row += 2

    # Top-N account share
    account_totals: dict[str, float] = {}
    for n, a in le_opps:
        account_totals[n] = account_totals.get(n, 0.0) + a
    top_accts = sorted(account_totals.items(), key=lambda kv: kv[1], reverse=True)
    grand = sum(a for _, a in top_accts) or 1.0  # avoid div-by-zero on empty data

    ws.cell(row=row, column=1, value="Account concentration (open L+E ARR)").font = title_font
    row += 1
    _set_header(ws, row, ["Slice", "ARR (EUR)", "% of total"])
    row += 1
    for label, n in [
        ("Top 1 account", 1),
        ("Top 3 accounts", 3),
        ("Top 5 accounts", 5),
        ("Top 10 accounts", 10),
    ]:
        slice_total = sum(a for _, a in top_accts[:n])
        ws.cell(row=row, column=1, value=label).font = input_font
        c = ws.cell(row=row, column=2, value=round(slice_total, 2))
        c.font = input_font
        c.number_format = "#,##0"
        c = ws.cell(row=row, column=3, value=slice_total / grand)
        c.font = input_font
        c.number_format = "0.0%"
        row += 1
    row += 1

    # Top-N owner share
    owner_totals: dict[str, float] = {}
    for r in raw:
        if r.get("Type") not in ("Land", "Expand"):
            continue
        nm = r.get("OwnerName") or "(unknown)"
        owner_totals[nm] = owner_totals.get(nm, 0.0) + float(r.get("ARR_EUR") or 0)
    top_owners = sorted(owner_totals.items(), key=lambda kv: kv[1], reverse=True)

    ws.cell(row=row, column=1, value="Owner concentration (open L+E ARR)").font = title_font
    row += 1
    _set_header(ws, row, ["Slice", "ARR (EUR)", "% of total"])
    row += 1
    for label, n in [("Top 1 owner", 1), ("Top 3 owners", 3), ("Top 5 owners", 5)]:
        slice_total = sum(a for _, a in top_owners[:n])
        ws.cell(row=row, column=1, value=label).font = input_font
        c = ws.cell(row=row, column=2, value=round(slice_total, 2))
        c.font = input_font
        c.number_format = "#,##0"
        c = ws.cell(row=row, column=3, value=slice_total / grand)
        c.font = input_font
        c.number_format = "0.0%"
        row += 1

    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 14


def _build_weighted_forecast(wb: Workbook, backtest: dict | None) -> None:
    """Probability-weighted forecast — formula-driven so a stakeholder can
    click any cell and trace.

      Open ARR per stage  → '=Pipeline_By_Stage!B<n>'    (XREF green)
      Forward rate        → INPUT cell, blue, editable   (from backtest)
      Weighted ARR        → '=B<row>*C<row>'             (LOCAL black)
      TOTAL row           → '=SUM(D2:D9)'                (LOCAL black, bold)

    Forward rates come from `state/forecast_backtest_q4.json`
    (org-wide rates from OFH 4-quarter backtest). They are written as
    INPUT cells so a stakeholder can override one and see the weighted
    forecast move. The "rate source" column tells the audit reader where
    each rate came from (org-wide backtest vs override).
    """
    ws = wb.create_sheet("Weighted_Forecast")
    _set_header(
        ws,
        1,
        ["Stage", "Open ARR (EUR)", "Forward rate", "Weighted ARR (EUR)", "Rate source"],
    )

    input_font = Font(color=INPUT_COLOR)
    xref_font = Font(color=XREF_COLOR)
    local_bold = Font(color=LOCAL_COLOR, bold=True)
    note_font = Font(italic=True, color=BRAND_GRAY)

    forward_rates = ((backtest or {}).get("forward_rates") or {}) if backtest else {}

    for i, s in enumerate(GRAPH.stages, start=2):
        # Stage label (XREF — references Stages sheet)
        ws.cell(row=i, column=1, value=f"=Stages!B{i}").font = xref_font

        # Open ARR (XREF — references Pipeline_By_Stage)
        c = ws.cell(row=i, column=2, value=f"=Pipeline_By_Stage!B{i}")
        c.font = xref_font
        c.number_format = "#,##0"

        # Forward rate — INPUT cell. If backtest data has a rate for this
        # stage use it; otherwise blank (formula will yield 0 weighted).
        rate_key = f"stage_{s.number}_forward_rate"
        rate_val = float(forward_rates.get(rate_key) or 0.0)
        c = ws.cell(row=i, column=3, value=rate_val)
        c.font = input_font
        c.number_format = "0.0%"

        # Weighted ARR (LOCAL — same-sheet multiply)
        c = ws.cell(row=i, column=4, value=f"=B{i}*C{i}")
        c.font = Font(color=LOCAL_COLOR)
        c.number_format = "#,##0"

        # Note (text)
        note = (
            "Org-wide backtest (last 4 fiscal quarters)"
            if rate_val
            else "(no backtest rate available — input as 0)"
        )
        ws.cell(row=i, column=5, value=note).font = note_font

    # TOTAL row — local sum
    total_row = 1 + len(GRAPH.stages) + 1
    ws.cell(row=total_row, column=1, value="TOTAL weighted").font = local_bold
    c = ws.cell(row=total_row, column=4, value=f"=SUM(D2:D{total_row - 1})")
    c.font = local_bold
    c.number_format = "#,##0"

    # Caveat / methodology row
    caveat_row = total_row + 2
    ws.cell(row=caveat_row, column=1, value="How to read this sheet").font = Font(
        bold=True, color=BRAND_PRIMARY
    )
    ws.cell(
        row=caveat_row + 1,
        column=1,
        value=(
            "Open ARR per stage is pulled from Pipeline_By_Stage (which itself "
            "is SUMIFS over Data filtered to CFQ-closing Land+Expand). "
            "Forward rate is the org-wide P(advanced) per stage from "
            "OpportunityFieldHistory over the last 4 fiscal quarters — these "
            "are inputs (blue) and editable. Weighted ARR = Open × Rate. "
            "Click any blue cell to see what's editable; click any green or "
            "black cell to see the formula. Caveat: rates are population-level, "
            "not director-specific."
        ),
    ).font = note_font
    ws.cell(row=caveat_row + 1, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[caveat_row + 1].height = 60

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 50
    ws.freeze_panes = "A2"


# ──────────────────────────────────────────────────────────────────────────
# Closed-history analytical sheets — formula-driven replacements for the
# legacy precomputed ARR_Roll / Trend_MoM / Trend_QoQ / Retention /
# Wins_Losses_QTD blocks in excel_companion.py. Each references the
# ClosedCFQ_* / ClosedWon6mo_* / Renewals12mo_* named ranges so click-to-
# trace audit works the same as the open-pipeline sheets above.
# ──────────────────────────────────────────────────────────────────────────


def _last_n_months(n: int) -> list[tuple[int, int]]:
    """List of (year, month) pairs covering the last `n` calendar months
    ending with the current month, oldest first."""
    today = date.today()
    months: list[tuple[int, int]] = []
    y, m = today.year, today.month
    for _ in range(n):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.reverse()
    return months


def _build_arr_roll(wb: Workbook) -> None:
    """6-month closed-won Land+Expand booked-ARR roll.

    Rows = the 6 calendar months ending with the current month. Booked
    ARR per month is a SUMIFS over ClosedWon6mo_ARR_EUR with a date
    half-open interval [DATE(y,m,1), DATE(next_y,next_m,1)). # Won is the
    matching COUNTIFS. TOTAL row is a same-sheet SUM (LOCAL black) since
    the underlying records ARE all in this 6-month window.
    """
    ws = wb.create_sheet("ARR_Roll")
    _set_header(ws, 1, ["Month", "Booked ARR (EUR)", "# Won"])

    input_font = Font(color=INPUT_COLOR)
    xref_font = Font(color=XREF_COLOR)
    local_bold = Font(color=LOCAL_COLOR, bold=True)

    months = _last_n_months(6)
    for i, (y, m) in enumerate(months, start=2):
        # Month label as YYYY-MM string (input — blue) so stakeholders can
        # see the period without parsing a serial.
        ws.cell(row=i, column=1, value=f"{y:04d}-{m:02d}").font = input_font
        # Compute exclusive upper bound (first day of NEXT month) inline.
        ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
        c = ws.cell(
            row=i,
            column=2,
            value=(
                f"=SUMIFS(ClosedWon6mo_ARR_EUR, "
                f'ClosedWon6mo_CloseDate, ">="&DATE({y},{m},1), '
                f'ClosedWon6mo_CloseDate, "<"&DATE({ny},{nm},1))'
            ),
        )
        c.font = xref_font
        c.number_format = "#,##0"
        c2 = ws.cell(
            row=i,
            column=3,
            value=(
                f'=COUNTIFS(ClosedWon6mo_CloseDate, ">="&DATE({y},{m},1), '
                f'ClosedWon6mo_CloseDate, "<"&DATE({ny},{nm},1))'
            ),
        )
        c2.font = xref_font

    # TOTAL row — same-sheet sum, LOCAL color.
    last_data_row = 1 + len(months)  # header + 6 month rows
    total_row = last_data_row + 1
    ws.cell(row=total_row, column=1, value="TOTAL").font = local_bold
    c = ws.cell(row=total_row, column=2, value=f"=SUM(B2:B{last_data_row})")
    c.font = local_bold
    c.number_format = "#,##0"
    c = ws.cell(row=total_row, column=3, value=f"=SUM(C2:C{last_data_row})")
    c.font = local_bold

    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 10
    ws.freeze_panes = "A2"


def _build_trend_mom(wb: Workbook) -> None:
    """Month-over-month delta on the 6-month roll. Pulls month label, #
    Won, and Booked ARR straight from ARR_Roll (XREF), then computes
    Δ MoM as IFERROR((C<n>-C<n-1>)/C<n-1>,"-") — LOCAL same-sheet."""
    ws = wb.create_sheet("Trend_MoM")
    _set_header(ws, 1, ["Month", "# Won", "Booked ARR (EUR)", "Δ MoM (Booked ARR)"])

    xref_font = Font(color=XREF_COLOR)
    local_font = Font(color=LOCAL_COLOR)

    # 6 months pulled from ARR_Roll!A2:A7 / B2:B7 / C2:C7. Δ MoM is "-"
    # on the first row (no prior period to compare against).
    n = 6
    for i in range(2, 2 + n):
        c = ws.cell(row=i, column=1, value=f"=ARR_Roll!A{i}")
        c.font = xref_font
        # ARR_Roll col B = Booked ARR; col C = # Won. Surface # Won first
        # for parity with the spec's column order (Month / # Won / Booked
        # ARR / Δ MoM).
        c = ws.cell(row=i, column=2, value=f"=ARR_Roll!C{i}")
        c.font = xref_font
        c = ws.cell(row=i, column=3, value=f"=ARR_Roll!B{i}")
        c.font = xref_font
        c.number_format = "#,##0"
        if i == 2:
            c = ws.cell(row=i, column=4, value="-")
            c.font = local_font
        else:
            c = ws.cell(
                row=i,
                column=4,
                value=f'=IFERROR((C{i}-C{i - 1})/C{i - 1},"-")',
            )
            c.font = local_font
            c.number_format = "0.0%"

    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 16
    ws.freeze_panes = "A2"


def _build_trend_qoq(wb: Workbook) -> None:
    """Quarter-over-quarter on the same 6-month closed-won window.

    The 6 months bucket into ~2 calendar quarters (sometimes 3 if the
    window straddles a boundary). Quarters are pre-derived in Python
    (input-blue label) and the per-quarter # Won + Booked ARR cells are
    SUMIFS/COUNTIFS over ClosedWon6mo_* (XREF green) with DATE() bounds.
    Δ QoQ uses the same IFERROR percent pattern as Trend_MoM."""
    ws = wb.create_sheet("Trend_QoQ")
    _set_header(ws, 1, ["Quarter", "# Won", "Booked ARR (EUR)", "Δ QoQ (Booked ARR)"])

    input_font = Font(color=INPUT_COLOR)
    xref_font = Font(color=XREF_COLOR)
    local_font = Font(color=LOCAL_COLOR)

    # Bucket the 6-month window into quarters, oldest first.
    quarters: list[tuple[int, int]] = []  # (year, q) pairs
    for y, m in _last_n_months(6):
        q = (m - 1) // 3 + 1
        if (y, q) not in quarters:
            quarters.append((y, q))

    for i, (y, q) in enumerate(quarters, start=2):
        start_month = (q - 1) * 3 + 1
        end_year = y + (1 if q == 4 else 0)
        end_month = start_month + 3 if q != 4 else 1
        ws.cell(row=i, column=1, value=f"{y:04d}-Q{q}").font = input_font
        c = ws.cell(
            row=i,
            column=2,
            value=(
                f'=COUNTIFS(ClosedWon6mo_CloseDate, ">="&DATE({y},{start_month},1), '
                f'ClosedWon6mo_CloseDate, "<"&DATE({end_year},{end_month},1))'
            ),
        )
        c.font = xref_font
        c = ws.cell(
            row=i,
            column=3,
            value=(
                f"=SUMIFS(ClosedWon6mo_ARR_EUR, "
                f'ClosedWon6mo_CloseDate, ">="&DATE({y},{start_month},1), '
                f'ClosedWon6mo_CloseDate, "<"&DATE({end_year},{end_month},1))'
            ),
        )
        c.font = xref_font
        c.number_format = "#,##0"
        if i == 2:
            ws.cell(row=i, column=4, value="-").font = local_font
        else:
            c = ws.cell(
                row=i,
                column=4,
                value=f'=IFERROR((C{i}-C{i - 1})/C{i - 1},"-")',
            )
            c.font = local_font
            c.number_format = "0.0%"

    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 16
    ws.freeze_panes = "A2"


def _build_retention(wb: Workbook) -> None:
    """GRR proxy — Won Renewal ACV / (Won + Lost Renewal ACV) over the
    last 12 months of opp-driven Renewals.

    NOT a true GRR: auto-renewals (the bulk of renewal volume at SimCorp)
    don't surface as opps and are excluded from this denominator. The
    caveat row makes that explicit so a stakeholder reading the cell
    doesn't take it as the published org-wide GRR."""
    ws = wb.create_sheet("Retention")
    _set_header(ws, 1, ["Metric", "Value"])

    xref_font = Font(color=XREF_COLOR)
    local_font = Font(color=LOCAL_COLOR)
    note_font = Font(italic=True, color=BRAND_GRAY)

    # Row 2: Won Renewal ACV (XREF — references Renewals12mo_*).
    ws.cell(row=2, column=1, value="Won Renewal ACV (last 12mo)").font = Font(bold=True)
    c = ws.cell(
        row=2,
        column=2,
        value="=SUMIFS(Renewals12mo_ACV_EUR, Renewals12mo_IsWon, TRUE)",
    )
    c.font = xref_font
    c.number_format = "#,##0"

    # Row 3: Lost Renewal ACV.
    ws.cell(row=3, column=1, value="Lost Renewal ACV (last 12mo)").font = Font(bold=True)
    c = ws.cell(
        row=3,
        column=2,
        value="=SUMIFS(Renewals12mo_ACV_EUR, Renewals12mo_IsWon, FALSE)",
    )
    c.font = xref_font
    c.number_format = "#,##0"

    # Row 4: GRR proxy % — same-sheet division, LOCAL black.
    ws.cell(row=4, column=1, value="GRR proxy %").font = Font(bold=True)
    c = ws.cell(row=4, column=2, value="=IFERROR(B2/(B2+B3), 0)")
    c.font = local_font
    c.number_format = "0.0%"

    # Row 5: caveat — italic gray, spanning conceptually (we just write
    # to col A and let it overflow visually).
    ws.cell(
        row=5,
        column=1,
        value=(
            "PROXY caveat: Won Renewal ACV / (Won + Lost). NOT the org's true "
            "GRR — auto-renewals (majority of renewal volume) never become "
            "opps and are excluded from this denominator."
        ),
    ).font = note_font
    ws.cell(row=5, column=1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[5].height = 36

    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 22
    ws.freeze_panes = "A2"


def _build_wins_losses_qtd(wb: Workbook) -> None:
    """Closed-this-Q outcomes — count + ARR (Land+Expand) + ACV (Renewal)
    split into Won and Lost rows. Every # / ARR / ACV cell is a SUMIFS or
    COUNTIFS over the ClosedCFQ_* named ranges → XREF green."""
    ws = wb.create_sheet("Wins_Losses_QTD")
    _set_header(ws, 1, ["Outcome", "#", "ARR (Land+Expand, EUR)", "ACV (Renewal, EUR)"])

    xref_font = Font(color=XREF_COLOR)

    # Row 2 — Won.
    ws.cell(row=2, column=1, value="Won").font = Font(bold=True)
    c = ws.cell(row=2, column=2, value="=COUNTIFS(ClosedCFQ_IsWon, TRUE)")
    c.font = xref_font
    c = ws.cell(
        row=2,
        column=3,
        value=(
            '=SUMIFS(ClosedCFQ_ARR_EUR, ClosedCFQ_IsWon, TRUE, ClosedCFQ_Type, "Land") '
            '+ SUMIFS(ClosedCFQ_ARR_EUR, ClosedCFQ_IsWon, TRUE, ClosedCFQ_Type, "Expand")'
        ),
    )
    c.font = xref_font
    c.number_format = "#,##0"
    c = ws.cell(
        row=2,
        column=4,
        value=('=SUMIFS(ClosedCFQ_ACV_EUR, ClosedCFQ_IsWon, TRUE, ClosedCFQ_Type, "Renewal")'),
    )
    c.font = xref_font
    c.number_format = "#,##0"

    # Row 3 — Lost.
    ws.cell(row=3, column=1, value="Lost").font = Font(bold=True)
    c = ws.cell(row=3, column=2, value="=COUNTIFS(ClosedCFQ_IsWon, FALSE)")
    c.font = xref_font
    c = ws.cell(
        row=3,
        column=3,
        value=(
            '=SUMIFS(ClosedCFQ_ARR_EUR, ClosedCFQ_IsWon, FALSE, ClosedCFQ_Type, "Land") '
            '+ SUMIFS(ClosedCFQ_ARR_EUR, ClosedCFQ_IsWon, FALSE, ClosedCFQ_Type, "Expand")'
        ),
    )
    c.font = xref_font
    c.number_format = "#,##0"
    c = ws.cell(
        row=3,
        column=4,
        value=('=SUMIFS(ClosedCFQ_ACV_EUR, ClosedCFQ_IsWon, FALSE, ClosedCFQ_Type, "Renewal")'),
    )
    c.font = xref_font
    c.number_format = "#,##0"

    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 8
    ws.column_dimensions["C"].width = 26
    ws.column_dimensions["D"].width = 26
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
            "Pivots (ad-hoc slicing)",
            "Data is a real Excel Table named tblData — click anywhere in Data and "
            "use Insert > PivotTable to slice by stage / owner / industry / country / "
            "age. The Pivots sheet has 5 pre-built cross-tabs (Stage × Industry, "
            "Owner × Stage, Country × Type, Top-10 Accounts × Stage, Stage × Quarter); "
            "row/column headers are inputs (blue), matrix cells are SUMIFS over "
            "Data (green).",
        ),
        (
            "Velocity",
            "Per-stage avg deal age + count of deals over 60 / 180 days old. "
            "Caveat: 'age' is days since CreatedDate, NOT time in current stage. "
            "True time-in-stage requires OpportunityFieldHistory wiring (deferred).",
        ),
        (
            "Concentration",
            "Top-1/3/5/10 account share + top-1/3/5 owner share of total open "
            "Land+Expand pipeline (CFQ + beyond). Single-deal risk fires when any "
            "one open L+E deal exceeds 25% of total open pipeline.",
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
