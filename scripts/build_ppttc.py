"""Build per-director think-cell `.ppttc` files for LAND monthly.

The emitted JSON follows think-cell's official JSON automation format:
top-level ARRAY -> one template object -> `data[]` entries with `name`
and `table`.

Important constraint: the current `assets/LAND_template.pptx` is a visual
placeholder deck, not a fully wired think-cell automation template. The
auto-generated donor-chart template path is still experimental too: the
resulting `.pptx` can open directly in PowerPoint, but think-cell rejects
it as a `.ppttc` template on this machine.

Use a manually wired template for production `.ppttc` output. The default
auto-generated path now requires an explicit opt-in flag so broken files
are not emitted by accident.

Run after activating the project venv:

    source .venv/bin/activate
    python3 scripts/build_ppttc.py --director "Jesper Tyrer" --period 2026-Q2
    python3 scripts/build_ppttc.py --all-directors --period 2026-Q2
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import numbers
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    import formulas  # type: ignore[import-untyped]
except ImportError as exc:  # pragma: no cover - exercised by CLI usage.
    raise SystemExit(
        "Missing dependency 'formulas'. Activate the project virtualenv first."
    ) from exc

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import range_boundaries

from _directors import canonical_directors
from model_recalc import _parse_key, _unwrap
from ppttc_template import (
    build_director_template,
    template_has_named_elements,
    template_named_elements,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = ROOT / "assets/LAND_template.pptx"
DEFAULT_STYLE = ROOT / "assets/SimCorp-thinkcell-style.xml"


@dataclass(frozen=True)
class DirectorArtifacts:
    name: str
    scope_label: str
    slug: str
    period: str
    director_dir: Path
    model_path: Path
    legacy_path: Path
    trends_path: Path
    brief_path: Path


class ModelWorkbook:
    """Workbook reader that resolves formula cells through the formulas lib."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.workbook = load_workbook(path, data_only=False)
        self._formula_values = self._calculate_formula_values()

    def _calculate_formula_values(self) -> dict[tuple[str, str], Any]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            xl = formulas.ExcelModel().loads(str(self.path)).finish()
            solution = xl.calculate()

        values: dict[tuple[str, str], Any] = {}
        for key, value in solution.items():
            parsed = _parse_key(str(key))
            if parsed is None:
                continue
            _, sheet, cell = parsed
            values[(sheet.upper(), cell.upper())] = _unwrap(value)
        return values

    def cell_value(self, sheet_name: str, cell_ref: str) -> Any:
        raw = self.workbook[sheet_name][cell_ref].value
        if isinstance(raw, str) and raw.startswith("="):
            return self._formula_values.get((sheet_name.upper(), cell_ref.upper()))
        return raw

    def matrix(self, sheet_name: str, cell_range: str) -> list[list[Any]]:
        min_col, min_row, max_col, max_row = range_boundaries(cell_range)
        rows: list[list[Any]] = []
        for row_idx in range(min_row, max_row + 1):
            row: list[Any] = []
            for col_idx in range(min_col, max_col + 1):
                coord = f"{get_column_letter(col_idx)}{row_idx}"
                row.append(self.cell_value(sheet_name, coord))
            rows.append(row)
        return rows


class LiteralWorkbook:
    """Workbook reader for legacy sheets that already store literal values."""

    def __init__(self, path: Path) -> None:
        self.workbook = load_workbook(path, data_only=True)

    def cell_value(self, sheet_name: str, cell_ref: str) -> Any:
        return self.workbook[sheet_name][cell_ref].value

    def matrix(self, sheet_name: str, cell_range: str) -> list[list[Any]]:
        min_col, min_row, max_col, max_row = range_boundaries(cell_range)
        rows: list[list[Any]] = []
        for row_idx in range(min_row, max_row + 1):
            row: list[Any] = []
            for col_idx in range(min_col, max_col + 1):
                coord = f"{get_column_letter(col_idx)}{row_idx}"
                row.append(self.cell_value(sheet_name, coord))
            rows.append(row)
        return rows


def _slugify_director_name(name: str) -> str:
    return name.replace(" ", "-")


def _canonical_director_index() -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for director in canonical_directors():
        slug = _slugify_director_name(director["name"])
        idx[director["name"].casefold()] = director
        idx[slug.casefold()] = director
    return idx


def _resolve_director(director_name_or_slug: str) -> dict[str, Any]:
    idx = _canonical_director_index()
    try:
        return idx[director_name_or_slug.casefold()]
    except KeyError as exc:
        raise SystemExit(f"Unknown director: {director_name_or_slug}") from exc


def _director_artifacts(period: str, director: dict[str, Any]) -> DirectorArtifacts:
    slug = _slugify_director_name(director["name"])
    director_dir = ROOT / "state" / period / slug
    return DirectorArtifacts(
        name=director["name"],
        scope_label=director["scope_label"],
        slug=slug,
        period=period,
        director_dir=director_dir,
        model_path=director_dir / "land.model.xlsx",
        legacy_path=director_dir / "land.xlsx",
        trends_path=director_dir / "trends.json",
        brief_path=director_dir / "brief.md",
    )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _parse_markdown_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = _trim_lines(buf)
            current = line[3:].strip()
            buf = []
            continue
        if current is not None:
            buf.append(line.rstrip())
    if current is not None:
        sections[current] = _trim_lines(buf)
    return sections


def _trim_lines(lines: list[str]) -> list[str]:
    out = lines[:]
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


def _extract_headline_bullets(sections: dict[str, list[str]]) -> list[str]:
    bullets: list[str] = []
    for line in sections.get("Headline", []):
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(_strip_markdown_inline(stripped[2:].strip()))
    return bullets


def _extract_risk_claims(trends: dict[str, Any]) -> list[str]:
    claims = []
    for risk in trends.get("risks", []):
        claim = str(risk.get("claim") or "").strip()
        if claim:
            claims.append(claim)
    return claims


def _extract_action_item_claims(trends: dict[str, Any], *, limit: int | None = None) -> list[str]:
    claims = []
    for item in trends.get("action_items", []):
        claim = str(item.get("claim") or "").strip()
        if claim:
            claims.append(claim)
    return claims if limit is None else claims[:limit]


def _strip_markdown_inline(text: str) -> str:
    return (
        text.replace("**", "")
        .replace("__", "")
        .replace("`", "")
        .replace("_", "")
        .strip()
    )


def _format_bullets(items: list[str], *, fallback: str) -> str:
    if not items:
        return fallback
    return "\n".join(f"- {item}" for item in items)


def _format_currency(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return str(value)
    absolute = abs(float(value))
    if absolute >= 1_000_000:
        return f"EUR {value / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"EUR {value:,.0f}"
    return f"EUR {value:.0f}"


def _format_percentage(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return str(value)
    return f"{float(value) * 100:.1f}%"


def _json_cell(value: Any) -> dict[str, Any] | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return {"string": "TRUE" if value else "FALSE"}
    if isinstance(value, datetime):
        return {"date": value.date().isoformat()}
    if isinstance(value, date):
        return {"date": value.isoformat()}
    if isinstance(value, int):
        return {"number": value}
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return {"number": value}
    return {"string": str(value)}


def _json_table(rows: list[list[Any]]) -> list[list[dict[str, Any] | None]]:
    return [[_json_cell(cell) for cell in row] for row in rows]


def _text_entry(name: str, text: str) -> dict[str, Any]:
    return {"name": name, "table": [[{"string": text}]]}


def _table_entry(name: str, rows: list[list[Any]]) -> dict[str, Any]:
    return {"name": name, "table": _json_table(rows)}


def _chart_entry(
    name: str,
    *,
    categories: list[Any],
    series_rows: list[tuple[str, list[Any]]],
) -> dict[str, Any]:
    if not categories:
        return _table_entry(name, [[None]])
    table: list[list[Any]] = [[None, *categories]]
    for label, values in series_rows:
        table.append([label, *values])
    return _table_entry(name, table)


def _last_nonempty_row(
    workbook: LiteralWorkbook | ModelWorkbook,
    sheet_name: str,
    *,
    start_row: int,
    columns: list[str],
    max_row: int | None = None,
) -> int:
    ws = workbook.workbook[sheet_name]
    limit = max_row or ws.max_row
    last = start_row
    for row_idx in range(start_row, limit + 1):
        row_has_value = False
        for col in columns:
            value = workbook.cell_value(sheet_name, f"{col}{row_idx}")
            if value not in (None, ""):
                row_has_value = True
                break
        if row_has_value:
            last = row_idx
    return last


def _action_items_table(trends: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = [
        ["#", "Priority", "Rule", "Claim", "Suggested action", "Due date", "Owner"]
    ]
    for idx, item in enumerate(trends.get("action_items", []), start=1):
        rows.append(
            [
                idx,
                str(item.get("priority") or "").upper(),
                item.get("rule_id"),
                item.get("claim"),
                item.get("suggested_action"),
                item.get("due_date"),
                item.get("owner"),
            ]
        )
    if len(rows) == 1:
        rows.append(["(no action items generated)", None, None, None, None, None, None])
    return rows


def _territory_bar_matrix(model: ModelWorkbook) -> list[list[Any]]:
    rows = [["Country", "Open ARR (EUR)"]]
    last_row = _last_nonempty_row(model, "Territory_Performance", start_row=2, columns=["B", "D"])
    for row_idx in range(2, last_row + 1):
        country = model.cell_value("Territory_Performance", f"B{row_idx}")
        arr = model.cell_value("Territory_Performance", f"D{row_idx}")
        if country in (None, ""):
            continue
        rows.append([country, arr])
    return rows


def _forecast_category_matrix(model: ModelWorkbook) -> list[list[Any]]:
    return model.matrix("Forecast_Category", "A1:C7")


def _number_or_zero(value: Any) -> float:
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        numeric = float(value)
        if math.isfinite(numeric):
            return numeric
    return 0.0


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        numeric = float(value)
        if math.isfinite(numeric):
            return numeric
    return None


def _pipe_movement_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.matrix("Pipe_Movement", "A2:B6")
    categories = [row[0] for row in matrix if row[0] not in (None, "")]
    values = [_number_or_zero(row[1]) for row in matrix if row[0] not in (None, "")]
    return _chart_entry("S04_PipeMovement", categories=categories, series_rows=[("ARR (EUR)", values)])


def _pipeline_by_stage_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.matrix("Pipeline_By_Stage", "A2:B9")
    categories = [row[0] for row in matrix if row[0] not in (None, "")]
    values = [_number_or_zero(row[1]) for row in matrix if row[0] not in (None, "")]
    return _chart_entry(
        "S05_PipelineByStage",
        categories=categories,
        series_rows=[("Open ARR (EUR)", values)],
    )


def _pipeline_aging_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.matrix("Pipeline_Aging", "A2:E7")
    categories = [row[0] for row in matrix if row[0] not in (None, "")]
    values = [_number_or_zero(row[3]) for row in matrix if row[0] not in (None, "")]
    return _chart_entry(
        "S06_PipelineAging",
        categories=categories,
        series_rows=[("Open ARR (EUR)", values)],
    )


def _forecast_category_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = _forecast_category_matrix(model)
    categories = [row[0] for row in matrix[1:] if row[0] not in (None, "")]
    values = [_number_or_zero(row[2]) for row in matrix[1:] if row[0] not in (None, "")]
    return _chart_entry(
        "S13_ForecastCategory",
        categories=categories,
        series_rows=[("ARR (EUR)", values)],
    )


def _by_owner_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    last_row = _last_nonempty_row(model, "By_Owner", start_row=2, columns=["A", "B"])
    rows = []
    for owner, arr in model.matrix("By_Owner", f"A2:B{last_row}"):
        if owner in (None, ""):
            continue
        numeric = _number_or_zero(arr)
        if numeric <= 0:
            continue
        rows.append((owner, numeric))
    rows.sort(key=lambda item: item[1], reverse=True)
    return _chart_entry(
        "S15_ByOwner",
        categories=[owner for owner, _ in rows],
        series_rows=[("Open ARR (EUR)", [arr for _, arr in rows])],
    )


def _stage_by_industry_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.matrix("Pivots", "A5:M13")
    headers = matrix[0]
    categories = [row[0] for row in matrix[1:]]
    series_rows: list[tuple[str, list[Any]]] = []
    for col_idx, series_name in enumerate(headers[1:], start=1):
        values = [_number_or_zero(row[col_idx]) for row in matrix[1:]]
        if any(values):
            series_rows.append((str(series_name), values))
    return _chart_entry("S16_StageByIndustry", categories=categories, series_rows=series_rows)


def _territory_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    rows = []
    for country, arr in _territory_bar_matrix(model)[1:]:
        if country in (None, "", "TOTAL"):
            continue
        numeric = _number_or_zero(arr)
        if numeric <= 0:
            continue
        rows.append((country, numeric))
    rows.sort(key=lambda item: item[1], reverse=True)
    return _chart_entry(
        "S17_TerritoryPerformance",
        categories=[country for country, _ in rows],
        series_rows=[("Open ARR (EUR)", [arr for _, arr in rows])],
    )


def _wins_losses_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.matrix("Wins_Losses_QTD", "A1:D3")
    categories = [row[0] for row in matrix[1:]]
    arr = [_number_or_zero(row[2]) for row in matrix[1:]]
    acv = [_number_or_zero(row[3]) for row in matrix[1:]]
    return _chart_entry(
        "S18_WinsLossesQTD",
        categories=categories,
        series_rows=[
            ("ARR (Land+Expand, EUR)", arr),
            ("ACV (Renewal, EUR)", acv),
        ],
    )


def _velocity_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.matrix("Velocity", "A3:E10")
    categories = [row[0] for row in matrix]
    line_values = [_number_or_none(row[2]) for row in matrix]
    bar_values = [_number_or_zero(row[1]) for row in matrix]
    return _chart_entry(
        "S19_Velocity",
        categories=categories,
        series_rows=[
            ("Median age (days)", line_values),
            ("# Open opps", bar_values),
        ],
    )


def _concentration_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.matrix("Concentration", "A11:C15")
    categories = [row[0] for row in matrix[1:]]
    shares = [_number_or_zero(row[2]) * 100 for row in matrix[1:]]
    return _chart_entry(
        "S21_ConcentrationRiskChart",
        categories=categories,
        series_rows=[("Share (%)", shares)],
    )


def _stale_activity_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.matrix("Stale_Activity", "A1:C5")
    categories = [row[0] for row in matrix[1:]]
    values = [_number_or_zero(row[2]) for row in matrix[1:]]
    return _chart_entry(
        "S22_StaleActivity",
        categories=categories,
        series_rows=[("ARR (EUR)", values)],
    )


def _pipeline_creation_velocity_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.matrix("Pipeline_Creation_Velocity", "A1:C13")
    categories = [row[0] for row in matrix[1:]]
    arr_values = [_number_or_zero(row[2]) for row in matrix[1:]]
    count_values = [_number_or_zero(row[1]) for row in matrix[1:]]
    return _chart_entry(
        "S25_PipelineCreationVelocity",
        categories=categories,
        series_rows=[
            ("New ARR (EUR)", arr_values),
            ("# New opps", count_values),
        ],
    )


def _exec_summary_entries(
    trends: dict[str, Any],
    brief_sections: dict[str, list[str]],
) -> list[dict[str, Any]]:
    left_items = _extract_headline_bullets(brief_sections)
    if not left_items:
        left_items = _extract_action_item_claims(trends, limit=2)
    right_items = _extract_risk_claims(trends)
    if not right_items:
        right_items = _extract_action_item_claims(trends, limit=3)
    return [
        _text_entry(
            "S02_ExecSummaryLeft",
            _format_bullets(left_items, fallback="(no highlights generated)"),
        ),
        _text_entry(
            "S02_ExecSummaryRight",
            _format_bullets(right_items, fallback="(no risks generated)"),
        ),
    ]


def _sales_velocity_entries(model: ModelWorkbook) -> list[dict[str, Any]]:
    metric_names = [
        "OpenOpps",
        "WinRate",
        "AvgDealSize",
        "AvgCycleDays",
        "Velocity",
    ]
    entries: list[dict[str, Any]] = []
    for offset, metric_name in enumerate(metric_names, start=2):
        value = model.cell_value("Sales_Velocity", f"B{offset}")
        note = model.cell_value("Sales_Velocity", f"C{offset}")
        if metric_name == "WinRate":
            value_text = _format_percentage(value)
        elif metric_name in {"AvgDealSize", "Velocity"}:
            value_text = _format_currency(value)
            if metric_name == "Velocity":
                value_text = f"{value_text} / day"
        elif metric_name == "AvgCycleDays":
            value_text = f"{int(round(float(value)))} days" if isinstance(value, (int, float)) else str(value)
        else:
            value_text = str(int(value)) if isinstance(value, (int, float)) else str(value)
        entries.append(_text_entry(f"S23_{metric_name}Value", value_text))
        if note:
            entries.append(_text_entry(f"S23_{metric_name}Note", str(note)))
    return entries


def _concentration_entries(model: ModelWorkbook) -> list[dict[str, Any]]:
    account = model.cell_value("Concentration", "B5")
    arr = model.cell_value("Concentration", "B6")
    share = model.cell_value("Concentration", "B7")
    threshold = model.cell_value("Concentration", "B8")
    return [
        _text_entry("S21_LargestAccount", str(account or "")),
        _text_entry("S21_LargestArr", _format_currency(arr)),
        _text_entry("S21_LargestShare", _format_percentage(share)),
        _text_entry("S21_ThresholdFlag", str(threshold or "")),
        _table_entry("S21_ConcentrationTable", model.matrix("Concentration", "A11:C15")),
    ]


def _risks_outlook_entry(
    trends: dict[str, Any],
    brief_sections: dict[str, list[str]],
) -> dict[str, Any]:
    risk_claims = _extract_risk_claims(trends)
    if not risk_claims:
        risk_claims = _extract_action_item_claims(trends, limit=4)

    headline = _extract_headline_bullets(brief_sections)
    if headline:
        risk_claims.append(f"Outlook: {headline[0]}")

    return _text_entry(
        "S27_RisksOutlook",
        _format_bullets(risk_claims, fallback="(no risks or outlook generated)"),
    )


def _ppttc_entries_from_context(
    artifacts: DirectorArtifacts,
    *,
    trends: dict[str, Any],
    brief_sections: dict[str, list[str]],
    model: ModelWorkbook,
    legacy: LiteralWorkbook,
) -> list[dict[str, Any]]:
    pending_last = _last_nonempty_row(
        legacy,
        "Pending_Commercial_Approval",
        start_row=3,
        columns=["A", "B", "C", "D", "E", "F", "G", "H"],
    )
    renewal_last = _last_nonempty_row(
        legacy,
        "At_Risk_Renewals",
        start_row=1,
        columns=["A", "B", "C", "D", "E", "F", "G", "H"],
    )
    top_land_last = _last_nonempty_row(
        legacy,
        "Top_Deals_Land",
        start_row=1,
        columns=["A", "B", "C", "D", "E", "F", "G", "H"],
    )
    top_expand_last = _last_nonempty_row(
        legacy,
        "Top_Deals_Expand",
        start_row=1,
        columns=["A", "B", "C", "D", "E", "F", "G", "H"],
    )
    entries: list[dict[str, Any]] = [
        _text_entry("S01_DirectorName", artifacts.name),
        _text_entry("S01_Period", artifacts.period),
        _text_entry("S01_ScopeLabel", artifacts.scope_label),
    ]
    entries.extend(_exec_summary_entries(trends, brief_sections))
    entries.extend(
        [
            _pipe_movement_chart_entry(model),
            _pipeline_by_stage_chart_entry(model),
            _pipeline_aging_chart_entry(model),
            _table_entry("S07_TopDealsLand", legacy.matrix("Top_Deals_Land", f"A1:H{top_land_last}")),
            _table_entry(
                "S08_TopDealsExpand", legacy.matrix("Top_Deals_Expand", f"A1:H{top_expand_last}")
            ),
            _table_entry(
                "S09_PendingCommercialApproval",
                legacy.matrix("Pending_Commercial_Approval", f"A3:H{pending_last}"),
            ),
            _table_entry(
                "S11_RenewalPipeline", legacy.matrix("At_Risk_Renewals", f"A1:H{renewal_last}")
            ),
            _table_entry("S12_GRRProxyTable", model.matrix("Retention", "A1:B4")),
            _text_entry(
                "S12_GRRProxyFootnote", str(model.cell_value("Retention", "A5") or "")
            ),
            _forecast_category_chart_entry(model),
            _by_owner_chart_entry(model),
            _stage_by_industry_chart_entry(model),
            _territory_chart_entry(model),
            _wins_losses_chart_entry(model),
            _velocity_chart_entry(model),
            _concentration_chart_entry(model),
            _stale_activity_chart_entry(model),
            _text_entry(
                "S22_StaleActivityFootnote", str(model.cell_value("Stale_Activity", "A7") or "")
            ),
            _table_entry("S24_AccountExpansion", model.matrix("Account_Expansion", "A1:F16")),
            _pipeline_creation_velocity_chart_entry(model),
            _table_entry("S26_ActionItems", _action_items_table(trends)),
        ]
    )
    entries.extend(_concentration_entries(model))
    entries.extend(_sales_velocity_entries(model))
    entries.append(_risks_outlook_entry(trends, brief_sections))
    return entries


def _ppttc_entries(artifacts: DirectorArtifacts) -> list[dict[str, Any]]:
    trends = _load_json(artifacts.trends_path)
    brief_sections = _parse_markdown_sections(artifacts.brief_path.read_text())
    model = ModelWorkbook(artifacts.model_path)
    legacy = LiteralWorkbook(artifacts.legacy_path)
    return _ppttc_entries_from_context(
        artifacts,
        trends=trends,
        brief_sections=brief_sections,
        model=model,
        legacy=legacy,
    )


def _build_payload(template_path: Path, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"template": str(template_path.resolve()), "data": entries}]


def _write_ppttc(
    artifacts: DirectorArtifacts,
    *,
    template_path: Path,
    entries: list[dict[str, Any]],
) -> Path:
    out_path = artifacts.director_dir / f"{artifacts.slug}-LAND-{artifacts.period}.ppttc"
    payload = _build_payload(template_path, entries)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return out_path


def _validate_inputs(artifacts: DirectorArtifacts) -> None:
    missing = [
        path
        for path in (
            artifacts.director_dir,
            artifacts.model_path,
            artifacts.legacy_path,
            artifacts.trends_path,
            artifacts.brief_path,
        )
        if not path.exists()
    ]
    if missing:
        missing_str = ", ".join(str(path) for path in missing)
        raise SystemExit(f"Missing director artifacts for {artifacts.name}: {missing_str}")


def _build_for_director(
    director: dict[str, Any],
    *,
    period: str,
    template_path: Path,
) -> Path:
    artifacts = _director_artifacts(period, director)
    _validate_inputs(artifacts)
    trends = _load_json(artifacts.trends_path)
    brief_sections = _parse_markdown_sections(artifacts.brief_path.read_text())
    model = ModelWorkbook(artifacts.model_path)
    legacy = LiteralWorkbook(artifacts.legacy_path)

    resolved_template = template_path
    if template_path == DEFAULT_TEMPLATE.resolve():
        resolved_template = build_director_template(
            artifacts=artifacts,
            base_template_path=template_path,
            trends=trends,
            brief_sections=brief_sections,
            model=model,
            legacy=legacy,
        )

    entries = _ppttc_entries_from_context(
        artifacts,
        trends=trends,
        brief_sections=brief_sections,
        model=model,
        legacy=legacy,
    )
    if resolved_template != template_path:
        backed_names = template_named_elements(resolved_template)
        entries = [entry for entry in entries if entry["name"] in backed_names]
    return _write_ppttc(artifacts, template_path=resolved_template, entries=entries)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build think-cell .ppttc files for LAND monthly.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--director", help="Director display name or slug.")
    group.add_argument(
        "--all-directors",
        action="store_true",
        help="Build the .ppttc file for all 9 canonical directors.",
    )
    parser.add_argument("--period", required=True, help="Quarter label, e.g. 2026-Q2.")
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help="PowerPoint template path used in the emitted .ppttc.",
    )
    parser.add_argument(
        "--strict-template",
        action="store_true",
        help="Fail if the template does not appear to contain named think-cell elements.",
    )
    parser.add_argument(
        "--experimental-generated-template",
        action="store_true",
        help=(
            "Allow the default auto-generated director template path. "
            "This is research-only until think-cell accepts the generated "
            "template during real .ppttc import."
        ),
    )
    args = parser.parse_args()

    template_path = args.template.expanduser().resolve()
    if not template_path.exists():
        raise SystemExit(f"Template not found: {template_path}")

    if template_path == DEFAULT_TEMPLATE.resolve() and not args.experimental_generated_template:
        raise SystemExit(
            "The default auto-generated think-cell template path is still experimental: "
            "PowerPoint can open the generated .pptx, but think-cell rejects it during real "
            ".ppttc import with 'The template failed to load'. Use a manually wired template "
            "via --template for production output, or pass --experimental-generated-template "
            "for research-only builds."
        )

    if template_path != DEFAULT_TEMPLATE.resolve():
        template_wired = template_has_named_elements(template_path)
        if not template_wired:
            message = (
                "warning: template does not appear to contain named think-cell elements yet; "
                "emitted .ppttc files are structurally valid, but think-cell will ignore "
                "these names until a once-wired template is saved. "
                f"Style is also not part of JSON automation; keep {DEFAULT_STYLE} loaded in "
                "the saved template."
            )
            if args.strict_template:
                raise SystemExit(message)
            print(message, file=sys.stderr)

    if args.all_directors:
        directors = canonical_directors()
    else:
        directors = [_resolve_director(args.director)]

    outputs = [
        _build_for_director(director, period=args.period, template_path=template_path)
        for director in directors
    ]
    for out_path in outputs:
        print(out_path)
    print(f"built {len(outputs)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
