"""Build per-director think-cell `.ppttc` files for LAND monthly.

Emits .ppttc files. Hand the output to libs/tcrender for the headless
render step (Mac -> SSH -> VM ppttc.exe -> ferry-back). Do NOT use
libs/tc_com_driver for production rendering — that lib is the COM-dispatch
utility surface for bespoke UpdateBatch / interactive flows, not the
factory bulk-render path.

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

import yaml
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

# Mirrors scripts/factory.py LEGACY_SEED_MARKERS. Duplicated intentionally
# (per PR 1 of docs/plans/2026-05-04-land-review-factory-rebuild.md): both
# scripts are sibling CLIs and a shared helper is YAGNI for two call sites.
LEGACY_SEED_MARKERS = (
    "LAND_thinkcell_seed",
    "/legacy/",
    "Patrick-Gaughan-LAND",
    "_polished",
    "pre-stripdev",
    "pre-jinja-cleanup",
)


def _is_legacy_template(template_path: Path) -> bool:
    s = str(template_path)
    return any(marker in s for marker in LEGACY_SEED_MARKERS)


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


class NamedRangeError(KeyError):
    """Raised when a workbook-scoped named range cannot be resolved.

    Subclasses KeyError so existing `except KeyError` blocks still
    catch it, but is distinct enough for callers to handle it
    specifically when they want to.
    """


def _resolve_named_destination(workbook: Any, name: str) -> tuple[str, str]:
    """Resolve a workbook-scoped defined-name to (sheet, range) strings.

    Raises NamedRangeError if the name is not defined or has more than
    one destination (we do not currently support union/non-contiguous
    named ranges).
    """
    if name not in workbook.defined_names:
        raise NamedRangeError(
            f"Named range '{name}' not defined in workbook. "
            "Run `scripts/add_chart_binding_named_ranges.py` to migrate."
        )
    defn = workbook.defined_names[name]
    destinations = list(defn.destinations)
    if len(destinations) != 1:
        raise NamedRangeError(
            f"Named range '{name}' has {len(destinations)} destinations; "
            "only single-destination named ranges are supported."
        )
    sheet, ref = destinations[0]
    # Strip absolute-anchor `$` characters so callers can feed the result
    # straight into openpyxl's range_boundaries() helper.
    return sheet, ref.replace("$", "")


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

    def named_range(self, name: str) -> list[list[Any]]:
        """Read a workbook-scoped named range and return its matrix.

        Resolves the defined name -> (sheet, range), then delegates to
        :meth:`matrix`. Raises :class:`NamedRangeError` if the name is
        not defined or is non-contiguous. The returned matrix is
        identical to a manual ``matrix(sheet, range)`` call for the
        same destination.
        """
        sheet, ref = _resolve_named_destination(self.workbook, name)
        return self.matrix(sheet, ref)

    def named_cell(self, name: str) -> Any:
        """Read a workbook-scoped single-cell named range.

        Convenience for the Parameters / Concentration / Sales_Velocity
        single-cell bindings. Raises :class:`NamedRangeError` if the
        name is not defined or points at a multi-cell range.
        """
        sheet, ref = _resolve_named_destination(self.workbook, name)
        if ":" in ref:
            raise NamedRangeError(
                f"Named range '{name}' points at a multi-cell range '{ref}'; "
                "use `named_range()` for matrices."
            )
        return self.cell_value(sheet, ref)


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
    return text.replace("**", "").replace("__", "").replace("`", "").replace("_", "").strip()


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


def _scale_eur_to_meur(rows: list[list[Any]]) -> list[list[Any]]:
    """Idempotent EUR -> mEUR scaler. Handles two table shapes:

      - Header-column shape: row 0 has '(EUR)' in column header text.
        S24_AccountExpansion: "Land ARR (EUR)" / "Expand ARR (EUR)" / etc.

      - Label-value shape: column 0 has '(EUR)' in row label text.
        S21_ConcentrationTable: "Largest open L+E deal — ARR (EUR)" with
        the value in column B.

    Catches the F-01/F-02 class (raw EUR shipped as mEUR) — verified by
    scripts/validate_numeric_sanity.py.
    """
    if not rows:
        return rows
    eur_cols: set[int] = set()
    if rows[0]:
        for i, h in enumerate(rows[0]):
            if isinstance(h, str) and "(EUR)" in h:
                eur_cols.add(i)
    eur_label_rows: set[int] = set()
    for r_idx, row in enumerate(rows):
        if not row:
            continue
        label = row[0] if isinstance(row[0], str) else ""
        # "(EUR)" is the explicit marker; "ACV" / "ARR" are convention markers
        # (the deck factory always denominates these in EUR).
        if "(EUR)" in label or " ACV " in f" {label} " or " ARR " in f" {label} ":
            eur_label_rows.add(r_idx)
    if not eur_cols and not eur_label_rows:
        return rows

    def _scale(v: Any) -> Any:
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return round(v / 1_000_000, 2)
        return v

    out: list[list[Any]] = []
    for r_idx, row in enumerate(rows):
        new = list(row) if row else []
        for c in eur_cols:
            if r_idx > 0 and c < len(new):
                new[c] = _scale(new[c])
        if r_idx in eur_label_rows:
            for c in range(1, len(new)):
                new[c] = _scale(new[c])
        out.append(new)
    return out


_scale_eur_columns_to_meur = _scale_eur_to_meur


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
    # F-06 refactor: read by Excel named range so a Forecast_Category
    # layout shift won't silently corrupt S13. See
    # `state/thinkcell_bridge/excel_named_ranges/.../binding_to_range_manifest.json`.
    return model.named_range("S13_ForecastCategory")


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


def _stage_label(value: Any) -> str:
    label = str(value or "")
    if " - " in label:
        number, name = label.split(" - ", 1)
        return f"{number} {name}"
    return label


def _stage_name(value: Any) -> str:
    label = str(value or "")
    if " - " in label:
        return label.split(" - ", 1)[1]
    return label


def _compact_stage_label(value: Any) -> str:
    name = _stage_name(value)
    return {
        "Prospecting": "Prospect.",
        "Discovery": "Discovery",
        "Engagement": "Engage.",
        "Shortlisted": "Shortlist",
        "Preferred": "Preferred",
        "Contracting": "Contract",
        "Opt-out": "Opt-out",
        "Won": "Won",
    }.get(name, name)


def _week_label(value: Any) -> str:
    if isinstance(value, datetime):
        return f"{value:%b} {value.day}"
    if isinstance(value, date):
        return f"{value:%b} {value.day}"
    return str(value)


def _eur_millions(value: Any) -> float:
    return round(_number_or_zero(value) / 1_000_000, 1)


def _eur_millions_for_k_scaled_donor(value: Any) -> float:
    """Convert raw EUR to millions (mEUR). Production xlsx ships RAW EUR; the
    historical 'k_scaled_donor' name reflected an earlier donor-template
    convention (input was already in kEUR) that no longer applies. Bug F-01
    (audit 2026-05-03) — was /1_000 (gave kEUR labeled as mEUR), now /1_000_000.
    """
    return round(_number_or_zero(value) / 1_000_000, 1)


def _for_k_scaled_donor(value: Any) -> float:
    """Identity-passthrough; input is in target units already. Bug F-01
    (audit 2026-05-03) — was *1_000 (gave 100x-3-orders of magnitude wrong
    output for share %), now passthrough with rounding."""
    return round(_number_or_zero(value), 1)


def _eur_thousands(value: Any) -> float:
    return round(_number_or_zero(value) / 1_000, 0)


def _pipe_movement_label(label: Any) -> str:
    text = str(label or "").strip()
    return text.removeprefix("(+) ").removeprefix("(-) ")


def _pipe_movement_value(label: Any, value: Any) -> float:
    numeric = _number_or_zero(value)
    if str(label or "").strip().startswith("(-)"):
        numeric = -abs(numeric)
    return _eur_millions(numeric)


def _pipe_movement_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.named_range("S04_PipeMovement")
    rows = [(row[0], row[1]) for row in matrix if row[0] not in (None, "")]
    categories = [_pipe_movement_label(label) for label, _ in rows]
    values = [_pipe_movement_value(label, value) for label, value in rows]
    return _chart_entry(
        "S04_PipeMovement", categories=categories, series_rows=[("ARR (mEUR)", values)]
    )


def _pipeline_by_stage_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.named_range("S05_PipelineByStage")
    categories = [row[0] for row in matrix if row[0] not in (None, "")]
    values = [_eur_millions(row[1]) for row in matrix if row[0] not in (None, "")]
    return _chart_entry(
        "S05_PipelineByStage",
        categories=categories,
        series_rows=[("Open ARR (mEUR)", values)],
    )


def _pipeline_aging_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.named_range("S06_PipelineAging")
    categories = [row[0] for row in matrix if row[0] not in (None, "")]
    values = [_eur_millions(row[3]) for row in matrix if row[0] not in (None, "")]
    return _chart_entry(
        "S06_PipelineAging",
        categories=categories,
        series_rows=[("Open ARR (mEUR)", values)],
    )


def _forecast_category_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = _forecast_category_matrix(model)
    categories = [row[0] for row in matrix[1:] if row[0] not in (None, "")]
    values = [
        _eur_millions_for_k_scaled_donor(row[2]) for row in matrix[1:] if row[0] not in (None, "")
    ]
    return _chart_entry(
        "S13_ForecastCategory",
        categories=categories,
        series_rows=[("ARR (mEUR)", values)],
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
        series_rows=[("Open ARR (mEUR)", [_eur_millions(arr) for _, arr in rows])],
    )


def _stage_by_industry_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.named_range("S16_StageByIndustry")
    headers = matrix[0]
    industries = [str(header) for header in headers[1:] if header not in (None, "")]
    data_rows = [
        (str(row[0]), [_number_or_zero(value) for value in row[1 : 1 + len(industries)]])
        for row in matrix[1:]
        if row[0] not in (None, "")
    ]
    totals = [(idx, sum(values[idx] for _, values in data_rows)) for idx in range(len(industries))]
    top_indices = [
        idx for idx, total in sorted(totals, key=lambda item: item[1], reverse=True) if total > 0
    ][:5]
    other_indices = [idx for idx, total in totals if total > 0 and idx not in top_indices]
    selected_indices = top_indices + ([-1] if other_indices else [])
    categories = ["Other" if idx == -1 else industries[idx] for idx in selected_indices]
    raw_series: list[tuple[str, list[Any]]] = []
    for stage_name, row_values in data_rows:
        values = [
            _eur_millions(sum(row_values[i] for i in other_indices))
            if idx == -1
            else _eur_millions(row_values[idx])
            for idx in selected_indices
        ]
        if any(values):
            raw_series.append((_stage_name(stage_name), values))
    top_stage_names = {
        name
        for name, _ in sorted(
            raw_series,
            key=lambda item: sum(_number_or_zero(value) for value in item[1]),
            reverse=True,
        )[:3]
    }
    series_rows: list[tuple[str, list[Any]]] = []
    other_values = [0.0 for _ in categories]
    for name, values in raw_series:
        if name in top_stage_names:
            series_rows.append((name, values))
        else:
            other_values = [
                left + _number_or_zero(right) for left, right in zip(other_values, values)
            ]
    if any(other_values):
        series_rows.append(("Other stages", [round(value, 1) for value in other_values]))
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
        series_rows=[("Open ARR (mEUR)", [_eur_millions(arr) for _, arr in rows])],
    )


def _wins_losses_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.named_range("S18_WinsLossesQTD")
    categories = [row[0] for row in matrix[1:]]
    arr = [_eur_millions_for_k_scaled_donor(row[2]) for row in matrix[1:]]
    acv = [_eur_millions_for_k_scaled_donor(row[3]) for row in matrix[1:]]
    return _chart_entry(
        "S18_WinsLossesQTD",
        categories=categories,
        series_rows=[
            ("ARR (Land+Expand, mEUR)", arr),
            ("ACV (Renewal, mEUR)", acv),
        ],
    )


def _velocity_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.named_range("S19_Velocity")
    categories = [_compact_stage_label(row[0]) for row in matrix]
    # Bug F-02 (audit 2026-05-03): Velocity!C is already in days; the *1_000
    # multiplier was producing kilodays (e.g. 1,344,000 days for Shortlisted).
    # Removed.
    values = [_number_or_none(row[2]) for row in matrix]
    return _chart_entry(
        "S19_Velocity",
        categories=categories,
        series_rows=[("Median age (days)", values)],
    )


def _concentration_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.named_range("S21_ConcentrationTable")
    categories = [row[0] for row in matrix[1:]]
    shares = [_for_k_scaled_donor(_number_or_zero(row[2]) * 100) for row in matrix[1:]]
    return _chart_entry(
        "S21_ConcentrationRiskChart",
        categories=categories,
        series_rows=[("Share (%)", shares)],
    )


def _stale_activity_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.named_range("S22_StaleActivity")
    categories = [row[0] for row in matrix[1:]]
    values = [_eur_millions(row[2]) for row in matrix[1:]]
    return _chart_entry(
        "S22_StaleActivity",
        categories=categories,
        series_rows=[("ARR (mEUR)", values)],
    )


def _pipeline_creation_velocity_chart_entry(model: ModelWorkbook) -> dict[str, Any]:
    matrix = model.named_range("S25_PipelineCreationVelocity")
    categories = [_week_label(row[0]) for row in matrix[1:]]
    arr_values = [_eur_millions_for_k_scaled_donor(row[2]) for row in matrix[1:]]
    return _chart_entry(
        "S25_PipelineCreationVelocity",
        categories=categories,
        series_rows=[("New ARR (mEUR)", arr_values)],
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
        # Note column has no named ranges (it's free-form prose, not
        # surfaced as a binding to think-cell), so it keeps its
        # positional read.
        value = model.named_cell(f"S23_{metric_name}_src")
        note = model.cell_value("Sales_Velocity", f"C{offset}")
        if metric_name == "WinRate":
            value_text = _format_percentage(value)
        elif metric_name in {"AvgDealSize", "Velocity"}:
            value_text = _format_currency(value)
            if metric_name == "Velocity":
                value_text = f"{value_text} / day"
        elif metric_name == "AvgCycleDays":
            value_text = (
                f"{int(round(float(value)))} days"
                if isinstance(value, (int, float))
                else str(value)
            )
        else:
            value_text = str(int(value)) if isinstance(value, (int, float)) else str(value)
        entries.append(_text_entry(f"S23_{metric_name}Value", value_text))
        if note:
            entries.append(_text_entry(f"S23_{metric_name}Note", str(note)))
    return entries


def _concentration_entries(model: ModelWorkbook) -> list[dict[str, Any]]:
    account = model.named_cell("S21_LargestAccount_src")
    arr = model.named_cell("S21_LargestArr_src")
    share = model.named_cell("S21_LargestShare_src")
    threshold = model.named_cell("S21_ThresholdFlag_src")
    return [
        _text_entry("S21_LargestAccount", str(account or "")),
        _text_entry("S21_LargestArr", _format_currency(arr)),
        _text_entry("S21_LargestShare", _format_percentage(share)),
        _text_entry("S21_ThresholdFlag", str(threshold or "")),
        _table_entry(
            "S21_ConcentrationTable",
            _scale_eur_to_meur(model.named_range("S21_ConcentrationTable")),
        ),
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
            _table_entry(
                "S07_TopDealsLand", legacy.matrix("Top_Deals_Land", f"A1:H{top_land_last}")
            ),
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
            _table_entry(
                "S12_GRRProxyTable",
                _scale_eur_to_meur(model.named_range("S12_GRRProxyTable")),
            ),
            _text_entry(
                "S12_GRRProxyFootnote",
                str(model.named_cell("S12_GRRProxyFootnote_src") or ""),
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
                "S22_StaleActivityFootnote",
                str(model.named_cell("S22_StaleActivityFootnote_src") or ""),
            ),
            _table_entry(
                "S24_AccountExpansion",
                _scale_eur_columns_to_meur(model.named_range("S24_AccountExpansion")),
            ),
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


# Six valid leaf cell tags per the official ppttc schema, sourced from
# state/thinkcell_bridge/official_docs_corpus/<ts>/extraction.json
# section A_ppttc_schema. `null` is represented by the JSON null literal,
# not by an object; it is therefore checked separately.
_PPTTC_VALID_CELL_KEYS: frozenset[str] = frozenset(
    {"string", "number", "percentage", "date", "fill"}
)


def _validate_ppttc_shape(parsed: Any) -> list[str]:
    """Return shape-violation messages for a parsed `.ppttc` payload.

    The check is structural only -- it does not attempt to validate
    that emitted numbers make business sense, only that the JSON
    matches the official think-cell schema (top-level array of
    template-objects; each entry has `name` + `table`; each cell is
    None or a single-key object whose key is in `_PPTTC_VALID_CELL_KEYS`).
    """
    violations: list[str] = []

    if not isinstance(parsed, list):
        violations.append("top-level must be a JSON array")
        return violations
    if not parsed:
        violations.append("top-level array is empty (need at least one template object)")
        return violations

    for tpl_idx, tpl in enumerate(parsed):
        loc = f"template[{tpl_idx}]"
        if not isinstance(tpl, dict):
            violations.append(f"{loc}: must be an object, got {type(tpl).__name__}")
            continue
        template_value = tpl.get("template")
        if not isinstance(template_value, str) or not template_value:
            violations.append(f"{loc}: 'template' must be a non-empty string")
        data_entries = tpl.get("data")
        if not isinstance(data_entries, list):
            violations.append(f"{loc}: 'data' must be an array")
            continue

        seen_names: dict[str, int] = {}
        for ent_idx, entry in enumerate(data_entries):
            entry_loc = f"{loc}.data[{ent_idx}]"
            if not isinstance(entry, dict):
                violations.append(f"{entry_loc}: must be an object")
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                violations.append(f"{entry_loc}: 'name' must be a non-empty string")
            else:
                seen_names[name] = seen_names.get(name, 0) + 1
            table = entry.get("table")
            if not isinstance(table, list):
                violations.append(f"{entry_loc} ({name!r}): 'table' must be a list")
                continue
            for row_idx, row in enumerate(table):
                row_loc = f"{entry_loc} ({name!r}).table[{row_idx}]"
                if not isinstance(row, list):
                    violations.append(f"{row_loc}: row must be a list")
                    continue
                for col_idx, cell in enumerate(row):
                    cell_loc = f"{row_loc}[{col_idx}]"
                    if cell is None:
                        continue
                    if not isinstance(cell, dict):
                        violations.append(
                            f"{cell_loc}: cell must be null or a single-key object, "
                            f"got {type(cell).__name__}"
                        )
                        continue
                    keys = set(cell.keys())
                    extra = keys - _PPTTC_VALID_CELL_KEYS
                    if extra:
                        violations.append(
                            f"{cell_loc}: unknown cell key(s) {sorted(extra)} "
                            f"(valid: {sorted(_PPTTC_VALID_CELL_KEYS)})"
                        )
                    # `fill` may co-exist with one of the data keys; otherwise we
                    # expect exactly one key.
                    data_keys = keys & (_PPTTC_VALID_CELL_KEYS - {"fill"})
                    if len(data_keys) > 1:
                        violations.append(
                            f"{cell_loc}: cell has multiple data keys {sorted(data_keys)}; "
                            "expected at most one of string/number/percentage/date"
                        )

        for dup_name, count in seen_names.items():
            if count > 1:
                violations.append(
                    f"{loc}: duplicate binding name {dup_name!r} appears {count} times"
                )

    return violations


def _write_ppttc(
    artifacts: DirectorArtifacts,
    *,
    template_path: Path,
    entries: list[dict[str, Any]],
) -> Path:
    out_path = artifacts.director_dir / f"{artifacts.slug}-LAND-{artifacts.period}.ppttc"
    payload = _build_payload(template_path, entries)
    violations = _validate_ppttc_shape(payload)
    if violations:
        joined = "\n  - ".join(violations)
        raise SystemExit(f"ppttc shape validation failed for {artifacts.name}:\n  - {joined}")
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


def _build_director_context_for_narrative(
    artifacts: DirectorArtifacts,
    *,
    trends: dict[str, Any],
    model: ModelWorkbook,
) -> Any:
    """Build a tcrender.narrative.DirectorContext from existing artifacts.

    Lazy-imports tcrender.narrative so this script keeps importing cleanly
    even when tcrender is missing on the path (e.g. when the venv has not
    been installed).
    """
    sys.path.insert(0, str(ROOT / "libs" / "tcrender"))
    from tcrender.narrative import DirectorContext  # noqa: PLC0415

    closeable_arr = float(_number_or_zero(model.cell_value("Forecast_Category", "C5") or 0.0))
    renewal_acv = float(_number_or_zero(model.cell_value("Retention", "B2") or 0.0))
    largest_share = model.cell_value("Concentration", "B7")
    largest_share_pct: float | None
    if isinstance(largest_share, (int, float)) and not isinstance(largest_share, bool):
        largest_share_pct = float(largest_share) * 100.0
    else:
        largest_share_pct = None

    risks = tuple(_extract_risk_claims(trends)[:5])
    actions = tuple(_extract_action_item_claims(trends, limit=5))
    top_deals_rows: list[dict[str, Any]] = []
    try:
        top_land = LiteralWorkbook(artifacts.legacy_path).matrix("Top_Deals_Land", "A2:H7")
    except Exception:  # noqa: BLE001 - best-effort
        top_land = []
    for row in top_land:
        if not row or row[0] in (None, ""):
            continue
        top_deals_rows.append(
            {
                "account": str(row[0]),
                "stage": str(row[3] or ""),
                "owner": str(row[2] or ""),
                "arr_eur": _number_or_zero(row[7] if len(row) > 7 else 0.0),
            }
        )

    return DirectorContext(
        name=artifacts.name,
        slug=artifacts.slug,
        period=artifacts.period,
        scope_label=artifacts.scope_label,
        closeable_arr_eur=closeable_arr,
        renewal_acv_eur=renewal_acv,
        largest_account_share_pct=largest_share_pct,
        risk_claims=risks,
        action_items=actions,
        top_deals=tuple(top_deals_rows[:6]),
    )


def _count_cache_files(cache_dir: Path) -> int:
    if not cache_dir.exists():
        return 0
    return sum(1 for _ in cache_dir.glob("*.txt"))


def _override_narrative_entries(
    entries: list[dict[str, Any]],
    artifacts: DirectorArtifacts,
    *,
    trends: dict[str, Any],
    model: ModelWorkbook,
    rich_narrative: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, str], int]:
    """Replace S02 Left/Right + S27 entries with Claude-generated bullets.

    When ``rich_narrative`` is true, also overrides:
        - S01_Subtitle (cover page director-specific framing)
        - S{NN}_Insight bindings for every chart with non-empty data
          (S04, S05, S06, S07, S13, S15, S16, S17, S18, S19, S21, S22, S25)
        - S98_AnomalyWatch (3-5 Claude-detected anomalies)
        - S26_ActionsRanked (top-5 actions ranked by impact x urgency)
        - S03/S10/S20/S25_Header (per-section subtitles, picked up by
          polish_pass when present on the appropriate slides)

    Caches under ``state/narrative_cache/`` (created on first use). Falls
    back to the rule-based entries on any NarrativeError so the .ppttc is
    always emittable.

    Returns:
        (updated_entries, sample_narratives, claude_call_count) -- the
        second item maps binding_name -> the verbatim text written; the
        third is the number of cache misses (i.e. real ``claude -p``
        invocations) made during this call. Cached hits do not count.
    """
    sys.path.insert(0, str(ROOT / "libs" / "tcrender"))
    from tcrender.narrative import (  # noqa: PLC0415
        NarrativeError,
        generate_anomaly_watch,
        generate_chart_insights,
        generate_cover_subtitle,
        generate_exec_summary,
        generate_ranked_actions,
        generate_risks_outlook,
        generate_section_subtitles,
        load_thinkcell_vocabulary_primer,
    )

    ctx = _build_director_context_for_narrative(artifacts, trends=trends, model=model)
    cache_dir = ROOT / "state" / "narrative_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_before = _count_cache_files(cache_dir)
    samples: dict[str, str] = {}

    try:
        left, right = generate_exec_summary(ctx, cache_dir=cache_dir)
        risks_body = generate_risks_outlook(ctx, cache_dir=cache_dir)
    except NarrativeError as exc:
        print(
            f"warning: claude narrative generation failed ({exc}); "
            "keeping rule-based S02/S27 bullets.",
            file=sys.stderr,
        )
        return entries, samples, _count_cache_files(cache_dir) - cache_before

    left_text = "\n".join(f"- {b}" for b in left) or "(no highlights generated)"
    right_text = "\n".join(f"- {b}" for b in right) or "(no risks generated)"

    overrides: dict[str, str] = {
        "S02_ExecSummaryLeft": left_text,
        "S02_ExecSummaryRight": right_text,
        "S27_RisksOutlook": risks_body,
    }

    if rich_narrative:
        primer = load_thinkcell_vocabulary_primer()
        # Per-chart insights -- best-effort, individual failures are
        # silently skipped inside generate_chart_insights.
        try:
            insight_map = generate_chart_insights(ctx, entries, cache_dir=cache_dir, primer=primer)
            overrides.update(insight_map)
        except NarrativeError as exc:
            print(f"warning: chart insights pass failed ({exc})", file=sys.stderr)

        # S98 anomaly watch
        try:
            overrides["S98_AnomalyWatch"] = generate_anomaly_watch(
                ctx, cache_dir=cache_dir, primer=primer
            )
        except NarrativeError as exc:
            print(f"warning: anomaly watch failed ({exc})", file=sys.stderr)

        # S26 ranked actions (separate binding from the rule-based S26_ActionItems
        # table; polish_pass / native_fallback can decide which to render).
        try:
            overrides["S26_ActionsRanked"] = generate_ranked_actions(
                ctx, cache_dir=cache_dir, primer=primer
            )
        except NarrativeError as exc:
            print(f"warning: ranked actions failed ({exc})", file=sys.stderr)

        # S01 cover-page subtitle
        try:
            overrides["S01_Subtitle"] = generate_cover_subtitle(
                ctx, cache_dir=cache_dir, primer=primer
            )
        except NarrativeError as exc:
            print(f"warning: cover subtitle failed ({exc})", file=sys.stderr)

        # Per-section subtitles
        try:
            section_map = generate_section_subtitles(ctx, cache_dir=cache_dir, primer=primer)
            overrides.update(section_map)
        except NarrativeError as exc:
            print(f"warning: section subtitles failed ({exc})", file=sys.stderr)

    samples.update(overrides)

    new_entries: list[dict[str, Any]] = []
    seen_overrides: set[str] = set()
    for entry in entries:
        name = entry.get("name")
        if isinstance(name, str) and name in overrides:
            new_entries.append(_text_entry(name, overrides[name]))
            seen_overrides.add(name)
        else:
            new_entries.append(entry)
    # If a binding wasn't in the original entry list, append it.
    for name, text in overrides.items():
        if name not in seen_overrides:
            new_entries.append(_text_entry(name, text))

    cache_after = _count_cache_files(cache_dir)
    return new_entries, samples, cache_after - cache_before


def _build_for_director(
    director: dict[str, Any],
    *,
    period: str,
    template_path: Path,
    strict_template_contract: bool = False,
    narrative_enabled: bool = False,
    rich_narrative_enabled: bool = False,
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
    if narrative_enabled or rich_narrative_enabled:
        entries, narrative_samples, claude_calls = _override_narrative_entries(
            entries,
            artifacts,
            trends=trends,
            model=model,
            rich_narrative=rich_narrative_enabled,
        )
        # Order matters: cover/section before exec, then chart insights,
        # then ranked actions + anomaly watch.
        ordered_keys: list[str] = [
            "S01_Subtitle",
            "S03_Header",
            "S10_Header",
            "S20_Header",
            "S25_Header",
            "S02_ExecSummaryLeft",
            "S02_ExecSummaryRight",
            "S04_Insight",
            "S05_Insight",
            "S06_Insight",
            "S07_Insight",
            "S13_Insight",
            "S15_Insight",
            "S16_Insight",
            "S17_Insight",
            "S18_Insight",
            "S19_Insight",
            "S21_Insight",
            "S22_Insight",
            "S25_Insight",
            "S26_ActionsRanked",
            "S98_AnomalyWatch",
            "S27_RisksOutlook",
        ]
        for name in ordered_keys:
            text = narrative_samples.get(name)
            if text:
                print(f"-- narrative {name} --")
                for line in text.splitlines():
                    print(line)
                print()
        kind_label = "rich-narrative" if rich_narrative_enabled else "narrative"
        print(
            f"[{kind_label}] {artifacts.slug}: {claude_calls} claude call(s) "
            f"(cache misses); {len(narrative_samples)} bindings overridden",
            file=sys.stderr,
        )
    entry_names = {entry["name"] for entry in entries}
    if resolved_template != template_path:
        backed_names = template_named_elements(resolved_template)
        entries = [entry for entry in entries if entry["name"] in backed_names]
    elif strict_template_contract:
        backed_names = template_named_elements(template_path)
        missing_names = sorted(entry_names - backed_names)
        if missing_names:
            raise SystemExit(
                f"Template is missing {len(missing_names)} expected named elements for "
                f"{artifacts.name}: {', '.join(missing_names)}"
            )
    return _write_ppttc(artifacts, template_path=resolved_template, entries=entries)


# ---------------------------------------------------------------------------
# Registry-driven path (PR 6 of 2026-05-04-land-review-factory-rebuild)
# ---------------------------------------------------------------------------
#
# The functions below provide a parallel emission path that reads bindings
# from `config/thinkcell/land_review_full_28.binding_registry.yml` instead of
# the hard-coded chart/text helpers above. This is the new default. The
# legacy bindings path stays reachable via `--legacy-bindings` for forensic
# comparison until a future PR deprecates it.


def _load_registry(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def _resolve_source(source: str, ctx: dict[str, Any]) -> Any:
    """Resolve a registry `source` reference against the director context.

    Examples:
      'director.name'                          -> ctx['director']['name']
      'insight_titles.S05'                     -> ctx['insight_titles']['S05']
      'source_notes.S05'                       -> ctx['source_notes']['S05']
      'literal.Pipeline'                       -> 'Pipeline'
      'model.named_range.S05_PipelineByStage'  -> ctx['model']['named_range']['S05_PipelineByStage']
      'workbook.range.Top_Deals_Land!A1:H11'   -> handled at refresh-image time, not here
      'workbook.named_ranges.<X>'              -> handled at refresh-image time, not here
    """
    if source.startswith("literal."):
        return source.split(".", 1)[1]
    parts = source.split(".")
    cur: Any = ctx
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p)
        else:
            return None
    return cur


def _build_director_context_for_registry(
    director_name: str,
    period: str,
    director_dir: Path,
    insight_titles_path: Path | None = None,
    source_notes_path: Path | None = None,
) -> dict[str, Any]:
    """Build the context dict that the registry's `source` references resolve against.

    Layered: director + period + insight_titles + source_notes + brief + trends
    + (optional) model named ranges. Skips entries that don't exist on disk;
    consumers see None and the binding becomes 'suppressed'.
    """
    ctx: dict[str, Any] = {
        "director": {
            "name": director_name,
            "scope_label": f"{director_name} · {period}",
        },
        "period": {
            "label": period,
        },
        "insight_titles": {},
        "source_notes": {},
        "model": {"named_range": {}},
        "brief": {},
        "trends": {},
        "sales_velocity": {},
    }
    if insight_titles_path and insight_titles_path.exists():
        try:
            ctx["insight_titles"] = json.loads(insight_titles_path.read_text())
        except Exception:
            ctx["insight_titles"] = {}
    if source_notes_path and source_notes_path.exists():
        try:
            ctx["source_notes"] = json.loads(source_notes_path.read_text())
        except Exception:
            ctx["source_notes"] = {}
    trends_path = director_dir / "trends.json"
    if trends_path.exists():
        try:
            ctx["trends"] = json.loads(trends_path.read_text())
        except Exception:
            ctx["trends"] = {}
    return ctx


def _build_ppttc_from_registry(
    director_ctx: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Returns (ppttc_data_array, evidence_bindings).

    For ppttc_text: emit a {"name": ..., "table": [[{"v": str(value)}]]} entry.
    For ppttc_chart: emit a {"name": ..., "table": value} where value is 2D.
    For excel_table_image: defer to refresh script — record evidence only.
    For static: skip emission, record evidence as 'static'.

    Each registry element produces exactly one entry in evidence_bindings.
    """
    data_items: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for slide in registry.get("slides", []):
        sid = slide.get("slide_id", "")
        for el in slide.get("elements", []):
            name = el.get("name", "")
            kind = el.get("kind", "")
            lane = el.get("lane", "")
            base_evidence: dict[str, Any] = {
                "name": name,
                "kind": kind,
                "lane": lane,
                "required": el.get("required", False),
                "slide_id": sid,
            }
            if lane == "static":
                evidence.append({**base_evidence, "status": "static"})
                continue
            if lane == "excel_table_image":
                evidence.append(
                    {
                        **base_evidence,
                        "status": "deferred",
                        "deferred_to": "excel_updatebatch",
                    }
                )
                continue
            source = el.get("source", "")
            value = _resolve_source(source, director_ctx)
            if value is None and el.get("required"):
                evidence.append(
                    {
                        **base_evidence,
                        "status": "suppressed",
                        "reason": f"source '{source}' resolved to None",
                    }
                )
                continue
            if value is None:
                evidence.append({**base_evidence, "status": "absent"})
                continue
            if lane == "ppttc_text":
                data_items.append({"name": name, "table": [[{"v": str(value)}]]})
                evidence.append({**base_evidence, "status": "bound", "expected_text": str(value)})
            elif lane == "ppttc_chart":
                if isinstance(value, list):
                    data_items.append({"name": name, "table": value})
                    evidence.append({**base_evidence, "status": "bound"})
                else:
                    evidence.append(
                        {
                            **base_evidence,
                            "status": "suppressed",
                            "reason": (
                                f"chart source must be 2D table, got {type(value).__name__}"
                            ),
                        }
                    )
            else:
                evidence.append(
                    {
                        **base_evidence,
                        "status": "suppressed",
                        "reason": f"unknown lane '{lane}'",
                    }
                )
    return data_items, evidence


def _run_registry_driven(
    *,
    director_name: str,
    period: str,
    registry_path: Path,
    template_path: Path,
    out_dir: Path | None,
    emit_evidence_manifest: bool,
) -> int:
    registry = _load_registry(registry_path)

    # Try to resolve a canonical director (normalises display name + slug).
    # If the director isn't canonical, fall back to the raw input — the
    # registry path is also useful for synthetic / fixture builds where the
    # director may not exist in `_directors.canonical_directors()`.
    try:
        director = _resolve_director(director_name)
        canonical_name = director["name"]
        slug = _slugify_director_name(canonical_name)
    except SystemExit:
        canonical_name = director_name
        slug = _slugify_director_name(director_name)

    director_dir = out_dir if out_dir is not None else (ROOT / "state" / period / slug)
    director_dir.mkdir(parents=True, exist_ok=True)

    insight_titles_path = director_dir / "insight_titles.json"
    source_notes_path = director_dir / "source_notes.json"

    ctx = _build_director_context_for_registry(
        director_name=canonical_name,
        period=period,
        director_dir=director_dir,
        insight_titles_path=insight_titles_path,
        source_notes_path=source_notes_path,
    )

    data_items, evidence = _build_ppttc_from_registry(ctx, registry)
    payload = [{"template": template_path.name, "data": data_items}]

    out_path = director_dir / f"{slug}-LAND-{period}.ppttc"
    out_path.write_text(json.dumps(payload, indent=2))

    if emit_evidence_manifest:
        manifest_path = director_dir / "render_evidence_manifest.json"
        manifest = {
            "director": canonical_name,
            "period": period,
            "template": str(template_path),
            "registry": str(registry_path),
            "bindings": evidence,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f"OK: registry-driven .ppttc -> {out_path}")
    return 0


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
    parser.add_argument(
        "--narrative",
        action="store_true",
        help=(
            "Override S02_ExecSummary{Left,Right} and S27_RisksOutlook with "
            "Claude-generated narrative bullets matching the prior shipped "
            "deck style (uses tcrender.narrative + tcrender.narrative_templates "
            "style-guide injection). Cached under state/narrative_cache/. "
            "Falls back to rule-based bullets on any narrative error."
        ),
    )
    parser.add_argument(
        "--rich-narrative",
        action="store_true",
        help=(
            "Implies --narrative. Additionally generates per-chart S{NN}_Insight "
            "captions (S04..S25), S98_AnomalyWatch, S26_ActionsRanked, "
            "S01_Subtitle (cover framing), and S03/S10/S20/S25_Header (per-"
            "section subtitles). Cold-run cost: ~20 claude calls per director "
            "(~100 seconds). All cached under state/narrative_cache/ for "
            "subsequent runs to be free."
        ),
    )
    parser.add_argument(
        "--allow-legacy-seed",
        action="store_true",
        help=(
            "Allow legacy debris seed paths. Required if --template points at "
            "assets/LAND_thinkcell_seed*, assets/legacy/, or any quarantined "
            "asset. Use only for forensic comparison."
        ),
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "config" / "thinkcell" / "land_review_full_28.binding_registry.yml",
        help=(
            "Path to binding registry. Default: land_review_full_28 registry. "
            "Used by the registry-driven emission path (the new default)."
        ),
    )
    parser.add_argument(
        "--emit-evidence-manifest",
        action="store_true",
        help="Write render_evidence_manifest.json alongside the .ppttc.",
    )
    parser.add_argument(
        "--legacy-bindings",
        action="store_true",
        help=("Use hard-coded bindings instead of the registry. For forensic comparison only."),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Override per-director output directory. Default: state/<period>/<slug>/.",
    )
    args = parser.parse_args()

    template_path = args.template.expanduser().resolve()

    if _is_legacy_template(template_path) and not args.allow_legacy_seed:
        raise SystemExit(
            f"refusing to use quarantined/legacy template: {template_path}\n"
            "pass --allow-legacy-seed for forensic-only override."
        )

    if not template_path.exists():
        raise SystemExit(f"Template not found: {template_path}")

    # Registry-driven path is the new default. Legacy bindings are reachable
    # only via --legacy-bindings or --all-directors (multi-director batch
    # still flows through the legacy path until a future PR ports it).
    if not args.legacy_bindings and not args.all_directors:
        return _run_registry_driven(
            director_name=args.director,
            period=args.period,
            registry_path=args.registry.expanduser().resolve(),
            template_path=template_path,
            out_dir=(args.out_dir.expanduser().resolve() if args.out_dir else None),
            emit_evidence_manifest=args.emit_evidence_manifest,
        )

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
        _build_for_director(
            director,
            period=args.period,
            template_path=template_path,
            strict_template_contract=args.strict_template,
            narrative_enabled=args.narrative or args.rich_narrative,
            rich_narrative_enabled=args.rich_narrative,
        )
        for director in directors
    ]
    for out_path in outputs:
        print(out_path)
    print(f"built {len(outputs)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
