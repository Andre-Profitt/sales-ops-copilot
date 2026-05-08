"""Visual-schema knowledge graph — verified PBIR-Legacy visualType shapes.

For each visualType, captures:
  - the singleVisual.visualType string Power BI expects
  - which prototypeQuery.Select node kinds are valid (Column / Measure)
  - which projections keys are required (Values / Rows / Columns)
  - what evidence we have that the shape works (provenance)

Per-tab plans should consult this registry BEFORE inventing a new visual
config. New shapes are added by:
  1. Manually building one in the live PBI editor (browser).
  2. Pulling report.json via fetch_live_report() in rw_validate.
  3. Copying the singleVisual config into a SHAPES entry below.
  4. Recording verified_at / source_visual_id so future you can re-verify.

Schemas are deliberately data-only — builders live in _pbir_helpers.py.
This module is the catalog; helpers are the constructors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class VisualShape:
    visual_type: str
    select_kinds: tuple[Literal["Column", "Measure"], ...]
    projection_keys: tuple[str, ...]
    builder: str  # name of the function in _pbir_helpers.py
    verified_at: str  # ISO date
    source_report_id: str  # which report we live-verified against
    notes: str = ""
    requires_aliases: bool = True
    cross_table_ok: bool = False
    extras: dict = field(default_factory=dict)


# Reference rpt_vp_ops_scorecard live in apro@simcorp.com's
# Salesforce Analytics - Sales Manager workspace.
_RPT_VP_OPS = "d7362a11-f3dd-4bd1-a69a-68c941c2598b"


SHAPES: dict[str, VisualShape] = {
    "card": VisualShape(
        visual_type="card",
        select_kinds=("Measure",),
        projection_keys=("Values",),
        builder="build_card_visual",
        verified_at="2026-05-07",
        source_report_id=_RPT_VP_OPS,
        notes=(
            "Single-measure tile. Differs from SalesManager's Aggregation+Column "
            "pattern: we use Measure on properly-defined DAX measures, not raw "
            "column aggregation."
        ),
    ),
    "slicer": VisualShape(
        visual_type="slicer",
        select_kinds=("Column",),
        projection_keys=("Values",),
        builder="build_slicer_visual",
        verified_at="2026-05-07",
        source_report_id=_RPT_VP_OPS,
        notes=(
            "Column-driven filter widget. orientation:1D in objects.general "
            "renders as horizontal chip list. Single dim-table column."
        ),
    ),
    "tableEx": VisualShape(
        visual_type="tableEx",
        select_kinds=("Column", "Measure"),
        projection_keys=("Values",),
        builder="build_table_visual",
        verified_at="2026-05-08",
        source_report_id=_RPT_VP_OPS,
        cross_table_ok=True,
        notes=(
            "Multi-column flat table; mix of Column + Measure refs OK. Order of "
            "columns in input list = display order. Use for commit-risk lists, "
            "stall lists, renewal cohort tables."
        ),
    ),
    "pivotTable": VisualShape(
        visual_type="pivotTable",
        select_kinds=("Column", "Measure"),
        projection_keys=("Rows", "Columns", "Values"),
        builder="build_matrix_visual",
        verified_at="2026-05-08",
        source_report_id=_RPT_VP_OPS,
        cross_table_ok=True,
        notes=(
            "Matrix / pivot. Rows + Columns are Column refs; Values are Measure "
            "refs. Use for Stage × Motion, region × FQ, stage hygiene grids."
        ),
    ),
}


# ── Visual types known to exist in PBI but not yet captured in this KG ──
# Sourced from the salesmanager_report.json reference fixture (tests/sales/
# fixtures/) which contains these visualType values from a hand-built report:
#
#   barChart, basicShape, clusteredBarChart, clusteredColumnChart, donutChart,
#   gauge, hundredPercentStackedColumnChart, image, map, textbox, treemap,
#   actionButton, HorizontalFunnel1449177164235 (custom visual)
#
# When you need one of these in a per-tab plan:
#   1. Either check the salesmanager_report.json fixture for an exact shape
#      to copy (preferred), OR
#   2. Build it manually in the live editor, pull report.json, copy the
#      singleVisual block, add an entry below.
PENDING: tuple[str, ...] = (
    "barChart",
    "clusteredBarChart",
    "clusteredColumnChart",
    "donutChart",
    "gauge",
    "hundredPercentStackedColumnChart",
    "lineChart",
    "areaChart",
    "kpi",
    "multiRowCard",
    "decompositionTreeVisual",
    "waterfallChart",
    "treemap",
    "textbox",
    "actionButton",
    "basicShape",
    "image",
)


def get_shape(visual_type: str) -> VisualShape | None:
    """Return the registered shape, or None if not yet captured."""
    return SHAPES.get(visual_type)


def shape_or_raise(visual_type: str) -> VisualShape:
    """Return the shape; raise with a helpful message if not captured yet."""
    shape = SHAPES.get(visual_type)
    if shape is None:
        if visual_type in PENDING:
            raise NotImplementedError(
                f"visualType={visual_type!r} is on the PENDING list in _pbir_shapes.py. "
                f"Live-probe it first, capture into SHAPES, then retry."
            )
        raise KeyError(
            f"visualType={visual_type!r} is not in the schema KG. "
            f"Known: {sorted(SHAPES)}. Pending: {list(PENDING)}."
        )
    return shape


def list_shapes() -> list[str]:
    return sorted(SHAPES)


def report_coverage() -> str:
    """Print a coverage summary."""
    captured = len(SHAPES)
    pending = len(PENDING)
    total = captured + pending
    lines = [
        f"PBIR visual-schema KG coverage: {captured}/{total} ({captured * 100 // total}%)",
        "",
        "Captured (verified live):",
    ]
    for name in sorted(SHAPES):
        s = SHAPES[name]
        lines.append(f"  ✓ {name:14s}  builder={s.builder:24s}  verified_at={s.verified_at}")
    lines.append("")
    lines.append("Pending (need live-probe + capture):")
    for name in PENDING:
        lines.append(f"  · {name}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report_coverage())
