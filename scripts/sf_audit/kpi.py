"""Phase 1 — KPI ingestion + SF execution.

Parses RW/AP KPI workbook (Master sheet) and runs templated SOQL for the
KPIs whose definitions map cleanly to fields in this org. Writes back a
populated workbook with three new columns: Current Value, SF Query, Status.

The Excel source defaults to ~/Downloads/Metrics_and_KPIs_with_SF_metrics.xlsx
but can be overridden with --src.

KPIs that don't have a template → Status: needs SOQL design (so a human
can iterate on this file as templates get added).

Usage:
  python3 -m scripts.sf_audit.kpi
  python3 -m scripts.sf_audit.kpi --src /path/to/file.xlsx --out reports/
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import openpyxl

logger = logging.getLogger("sf_audit.kpi")

DEFAULT_SRC = Path.home() / "Downloads" / "Metrics_and_KPIs_with_SF_metrics.xlsx"
DEFAULT_OUT = Path("reports")

# ────────────────────────────────────────────────────────────────────────────
# SF helpers (stand-alone — don't depend on scan.py to keep this script
# independently invocable).
# ────────────────────────────────────────────────────────────────────────────


def sf_query(soql: str) -> list[dict[str, Any]]:
    """Run SOQL via sf CLI and return records (unwrapped from envelope)."""
    proc = subprocess.run(
        ["sf", "data", "query", "--query", soql, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"sf query failed: {proc.stderr[:300]}")
    out = proc.stdout
    out = out[out.find("{") :]  # skip any leading update-warning lines
    res = json.loads(out)
    return list(res.get("result", {}).get("records") or [])


def sf_count(soql: str) -> int:
    proc = subprocess.run(
        ["sf", "data", "query", "--query", soql, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"sf count failed: {proc.stderr[:300]}")
    out = proc.stdout[proc.stdout.find("{") :]
    return int(json.loads(out).get("result", {}).get("totalSize", 0))


# ────────────────────────────────────────────────────────────────────────────
# KPI templates.
#
# Each template is a SOQL query + a function that extracts a final value
# from the records list, plus an optional formatter for display.
#
# Notes for SimCorp data per Andre's memory:
#   - APTS_Opportunity_ARR__c is the ARR field for Land/Expand
#   - APTS_Renewal_ACV__c is the ACV field for Renewals
#   - Never sum standard Amount across record types (it blends ARR + ACV)
#   - Real Asset object is Apttus_Config2__AssetLineItem__c (not standard Asset)
# ────────────────────────────────────────────────────────────────────────────

Template = dict[str, Any]


def _ratio(num: float, denom: float) -> float | None:
    return (num / denom) if denom else None


KPI_TEMPLATES: dict[str, Template] = {
    "Pipeline Value / Pipeline Coverage": {
        # Per ARR/ACV separation memory: pipeline = NEW-BUSINESS only, in
        # the current-quarter window (matches brief.py pull_salesforce_snapshot
        # convention). Renewal ACV reported separately by another KPI.
        "soql": (
            "SELECT SUM(APTS_Opportunity_ARR__c) totalARR "
            "FROM Opportunity "
            "WHERE IsClosed = false AND Type IN ('Land','Expand') "
            "AND CloseDate = THIS_QUARTER"
        ),
        "extract": lambda recs: (recs[0].get("totalARR") if recs else 0) or 0,
        "format": lambda v: f"${v:,.0f} (this-quarter L+E)" if v else "$0",
    },
    "Opportunity Win Rate (Close Rate)": {
        "soql_won": "SELECT COUNT(Id) FROM Opportunity WHERE IsWon = true AND IsClosed = true",
        "soql_lost": "SELECT COUNT(Id) FROM Opportunity WHERE IsWon = false AND IsClosed = true",
        "extract": lambda data: _ratio(data["won"], data["won"] + data["lost"]),
        "format": lambda v: f"{v:.1%}" if v is not None else "—",
        "kind": "compound",
    },
    "Sales Cycle Length (Average Time to Close) Closed Won Deals": {
        # Cycle length only computable for Closed Won; record-level since SOQL
        # has no direct AVG(date_diff). Sample last 12 months, compute client-side.
        "soql": (
            "SELECT CreatedDate, CloseDate FROM Opportunity "
            "WHERE IsWon = true AND CloseDate = LAST_N_MONTHS:12"
        ),
        "extract": lambda recs: _avg_days(recs, "CreatedDate", "CloseDate"),
        "format": lambda v: f"{v:.0f} days" if v else "—",
    },
    "Number of New opportunites created by region": {
        "soql": "SELECT COUNT(Id) FROM Opportunity WHERE CreatedDate = LAST_N_MONTHS:1",
        "extract": lambda recs: 0,  # this is COUNT(); use sf_count instead
        "format": lambda v: f"{v:,}",
        "kind": "count",
        "count_soql": "SELECT COUNT() FROM Opportunity WHERE CreatedDate = LAST_N_MONTHS:1",
    },
    "Opportunity Age / Stale Opportunities": {
        # Median age in days for open opps
        "soql": "SELECT CreatedDate FROM Opportunity WHERE IsClosed = false LIMIT 5000",
        "extract": lambda recs: _median_age_days(recs, "CreatedDate"),
        "format": lambda v: f"{v:.0f} days (median)" if v else "—",
    },
    "Closed won Average Deal Size by month": {
        "soql": (
            "SELECT AVG(APTS_Opportunity_ARR__c) avgARR "
            "FROM Opportunity WHERE IsWon = true AND Type IN ('Land','Expand') "
            "AND CloseDate = LAST_N_MONTHS:12"
        ),
        "extract": lambda recs: (recs[0].get("avgARR") if recs else 0) or 0,
        "format": lambda v: f"${v:,.0f}" if v else "$0",
    },
    "Forecast & Closed Won": {
        # New-business only — sum Won (already-booked) + Open (forecast) for Q.
        "soql_won": (
            "SELECT SUM(APTS_Opportunity_ARR__c) v "
            "FROM Opportunity WHERE IsWon = true AND Type IN ('Land','Expand') "
            "AND CloseDate = THIS_QUARTER"
        ),
        "soql_open": (
            "SELECT SUM(APTS_Opportunity_ARR__c) v "
            "FROM Opportunity WHERE IsClosed = false AND Type IN ('Land','Expand') "
            "AND CloseDate = THIS_QUARTER"
        ),
        "extract": lambda data: data["won"] + data["open"],
        "format": lambda v: f"${v:,.0f} (L+E only)" if v else "$0",
        "kind": "compound_sum",
    },
    "Stage 3 approvals by month": {
        # Andre's memory + the alerts.py code: Stage 3+ deals ≥$500K need
        # Commercial Approval. Here we just count Stage 3+ created this month.
        "soql": (
            "SELECT COUNT() FROM Opportunity "
            "WHERE CreatedDate = LAST_N_MONTHS:1 "
            "AND (StageName LIKE '3%' OR StageName LIKE 'Stage 3%')"
        ),
        "extract": lambda recs: 0,
        "format": lambda v: f"{v:,}",
        "kind": "count",
        "count_soql": (
            "SELECT COUNT() FROM Opportunity "
            "WHERE CreatedDate = LAST_N_MONTHS:1 "
            "AND (StageName LIKE '3%' OR StageName LIKE 'Stage 3%')"
        ),
    },
    "Lost ARR By Quarter - with reason codes": {
        "soql": (
            "SELECT SUM(APTS_Opportunity_ARR__c) lost "
            "FROM Opportunity "
            "WHERE IsWon = false AND IsClosed = true "
            "AND Type IN ('Land','Expand') AND CloseDate = THIS_QUARTER"
        ),
        "extract": lambda recs: (recs[0].get("lost") if recs else 0) or 0,
        "format": lambda v: f"${v:,.0f} (L+E only)" if v else "$0",
    },
    "Lead to Opportunity Time": {
        # Lead.ConvertedDate − Lead.CreatedDate, sample last 12 months
        "soql": (
            "SELECT CreatedDate, ConvertedDate FROM Lead "
            "WHERE IsConverted = true AND ConvertedDate = LAST_N_MONTHS:12"
        ),
        "extract": lambda recs: _avg_days(recs, "CreatedDate", "ConvertedDate"),
        "format": lambda v: f"{v:.1f} days" if v else "—",
    },
    "Lead Win/Loss Ratio": {
        # Conversion rate of leads created in last 12 months
        "soql_total": "SELECT COUNT() FROM Lead WHERE CreatedDate = LAST_N_MONTHS:12",
        "soql_converted": (
            "SELECT COUNT() FROM Lead WHERE CreatedDate = LAST_N_MONTHS:12 AND IsConverted = true"
        ),
        "extract": lambda data: _ratio(data["converted"], data["total"]),
        "format": lambda v: f"{v:.1%}" if v is not None else "—",
        "kind": "ratio",
    },
}


def _parse_dt(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def _coerce_aware(s: str) -> dt.datetime:
    """Parse a SF datetime/date string and force UTC tz-awareness so date and
    datetime fields can be subtracted without TypeError."""
    if "T" in s:
        return _parse_dt(s)
    return dt.datetime.fromisoformat(s).replace(tzinfo=dt.UTC)


def _avg_days(recs: list[dict], start_field: str, end_field: str) -> float | None:
    diffs: list[float] = []
    for r in recs:
        s, e = r.get(start_field), r.get(end_field)
        if not (s and e):
            continue
        try:
            diffs.append((_coerce_aware(e) - _coerce_aware(s)).total_seconds() / 86400)
        except (ValueError, AttributeError):
            continue
    return sum(diffs) / len(diffs) if diffs else None


def _median_age_days(recs: list[dict], created_field: str) -> float | None:
    now = dt.datetime.now(dt.UTC)
    ages: list[float] = []
    for r in recs:
        c = r.get(created_field)
        if not c:
            continue
        try:
            cd = _parse_dt(c)
            ages.append((now - cd).total_seconds() / 86400)
        except ValueError:
            continue
    if not ages:
        return None
    ages.sort()
    n = len(ages)
    return ages[n // 2] if n % 2 else (ages[n // 2 - 1] + ages[n // 2]) / 2


# ────────────────────────────────────────────────────────────────────────────
# Execution
# ────────────────────────────────────────────────────────────────────────────


def execute_template(name: str, tpl: Template) -> dict[str, Any]:
    """Run the template's queries; return value + query string + status."""
    kind = tpl.get("kind", "scalar")
    try:
        if kind == "scalar":
            recs = sf_query(tpl["soql"])
            value = tpl["extract"](recs)
            display = tpl["format"](value)
            return {"value": value, "display": display, "soql": tpl["soql"], "status": "OK"}
        if kind == "count":
            value = sf_count(tpl["count_soql"])
            display = tpl["format"](value)
            return {"value": value, "display": display, "soql": tpl["count_soql"], "status": "OK"}
        if kind == "compound":
            won = sf_count(tpl["soql_won"].replace("COUNT(Id)", "COUNT()"))
            lost = sf_count(tpl["soql_lost"].replace("COUNT(Id)", "COUNT()"))
            value = tpl["extract"]({"won": won, "lost": lost})
            display = tpl["format"](value)
            return {
                "value": value,
                "display": display,
                "soql": f"{tpl['soql_won']} ; {tpl['soql_lost']}",
                "status": "OK",
            }
        if kind == "compound_sum":
            won_recs = sf_query(tpl["soql_won"])
            open_recs = sf_query(tpl["soql_open"])
            won_v = (won_recs[0].get("v") if won_recs else 0) or 0
            open_v = (open_recs[0].get("v") if open_recs else 0) or 0
            value = tpl["extract"]({"won": won_v, "open": open_v})
            return {
                "value": value,
                "display": tpl["format"](value),
                "soql": f"{tpl['soql_won']} ; {tpl['soql_open']}",
                "status": "OK",
            }
        if kind == "ratio":
            total = sf_count(tpl["soql_total"])
            converted = sf_count(tpl["soql_converted"])
            value = tpl["extract"]({"total": total, "converted": converted})
            return {
                "value": value,
                "display": tpl["format"](value),
                "soql": f"{tpl['soql_total']} ; {tpl['soql_converted']}",
                "status": "OK",
            }
        return {"value": None, "display": "—", "soql": "", "status": f"unknown kind={kind}"}
    except Exception as e:
        logger.warning("template %r failed: %s", name, e)
        return {
            "value": None,
            "display": "ERR",
            "soql": tpl.get("soql", ""),
            "status": f"ERR: {type(e).__name__}: {str(e)[:200]}",
        }


# ────────────────────────────────────────────────────────────────────────────
# Excel I/O
# ────────────────────────────────────────────────────────────────────────────


def find_kpi_column_indices(sheet: Any) -> dict[str, int]:
    """Detect the column layout of the Master sheet by scanning the header row.
    Returns {column_name_normalized: 1-based_col_index}."""
    # Header row in this workbook is row 4 (timeline / id / initiative...).
    # But there may be section header rows above it. Scan rows 1..30 for
    # the row that contains 'Initiative/KPI' as a cell.
    header_row_idx = None
    for r_idx, row in enumerate(sheet.iter_rows(min_row=1, max_row=30, values_only=True), start=1):
        if any(c and "Initiative/KPI" in str(c) for c in row):
            header_row_idx = r_idx
            break
    if not header_row_idx:
        return {}
    header_cells = list(
        sheet.iter_rows(min_row=header_row_idx, max_row=header_row_idx, values_only=True)
    )[0]
    out = {}
    for i, cell in enumerate(header_cells, start=1):
        if cell:
            out[str(cell).strip().lower().replace("/", "_")] = i
    out["_header_row"] = header_row_idx
    return out


def populate_workbook(src: Path, out: Path) -> dict[str, Any]:
    """Copy src → out, then for each KPI row in Master sheet, look up the
    template and inject Current Value / SF Query / Status into appended cols."""
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, out)
    wb = openpyxl.load_workbook(out)
    if "Master" not in wb.sheetnames:
        raise RuntimeError("source workbook missing 'Master' sheet")
    sheet = wb["Master"]
    cols = find_kpi_column_indices(sheet)
    if "initiative_kpi" not in cols:
        raise RuntimeError("could not find 'Initiative/KPI' column on Master sheet")

    name_col = cols["initiative_kpi"]
    header_row = cols["_header_row"]

    # Append three new header cells at end of header row
    last_col = sheet.max_column
    cv_col = last_col + 1
    sq_col = last_col + 2
    st_col = last_col + 3
    sheet.cell(row=header_row, column=cv_col, value="Current Value")
    sheet.cell(row=header_row, column=sq_col, value="SF Query")
    sheet.cell(row=header_row, column=st_col, value="Status")

    summary = {"total": 0, "auto_mapped": 0, "needs_soql": 0, "errors": 0}
    for row_idx in range(header_row + 1, sheet.max_row + 1):
        kpi_name = sheet.cell(row=row_idx, column=name_col).value
        if not kpi_name:
            continue
        kpi_name = str(kpi_name).strip()
        summary["total"] += 1
        # Template lookup is case-insensitive prefix match
        tpl = None
        for tpl_name, t in KPI_TEMPLATES.items():
            if tpl_name.lower() in kpi_name.lower() or kpi_name.lower() in tpl_name.lower():
                tpl = t
                break
        if not tpl:
            sheet.cell(row=row_idx, column=cv_col, value="—")
            sheet.cell(row=row_idx, column=sq_col, value="")
            sheet.cell(row=row_idx, column=st_col, value="needs SOQL design")
            summary["needs_soql"] += 1
            continue
        result = execute_template(kpi_name, tpl)
        sheet.cell(row=row_idx, column=cv_col, value=result["display"])
        sheet.cell(row=row_idx, column=sq_col, value=result["soql"][:32000])
        sheet.cell(row=row_idx, column=st_col, value=result["status"])
        if result["status"] == "OK":
            summary["auto_mapped"] += 1
        else:
            summary["errors"] += 1

    wb.save(out)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="KPI ingestion + SF execution")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--out", type=Path, default=None, help="output xlsx path")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    if not args.src.exists():
        print(f"source workbook not found: {args.src}", file=sys.stderr)
        return 2

    out_path = args.out or (DEFAULT_OUT / f"kpi_values_{dt.date.today().isoformat()}.xlsx")

    print(f"ingesting {args.src.name} → {out_path}")
    summary = populate_workbook(args.src, out_path)
    print(
        f"\nKPIs total: {summary['total']}\n"
        f"  auto-mapped (executed against SF): {summary['auto_mapped']}\n"
        f"  needs SOQL design (no template):   {summary['needs_soql']}\n"
        f"  errors:                            {summary['errors']}"
    )
    print(f"\nWrote: {out_path}")
    print(f"  Templates known: {len(KPI_TEMPLATES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
