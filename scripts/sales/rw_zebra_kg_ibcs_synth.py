"""IBCS column synthesis, DAX synthesis, conditional formatting + composite tile builders.

Encodes the rules documented in:
- docs/sales/RW_ZEBRA_BI_INFRASTRUCTURE_ATLAS.md §3 (column synthesis grammar)
- docs/sales/RW_ZEBRA_BI_INFRASTRUCTURE_ATLAS.md §6 (Cards rendering grammar)
- docs/sales/RW_POWER_BI_NATIVE_INFRASTRUCTURE_ATLAS.md §2 (CF reference)

This module is pure (no I/O, no network); consumed by rw_zebra_kg_translator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING


@dataclass(frozen=True)
class ColumnSpec:
    """One synthesized IBCS column.

    role: 'absolute' (raw scenario column), 'delta' (X - Y), or 'relative' (X-Y / |Y|).
    base: scenario tuple. ('AC',) for absolute, ('AC','PY') for delta/relative.
    format_code: 0=integer, 1=signed, 2=percent, 3=signed-decimal.
    is_cost: invert sign so positive = good (AC < PY for costs).
    """

    name: str
    role: str
    base: tuple[str, ...]
    format_code: int
    is_cost: bool = False


if TYPE_CHECKING:
    from scripts.sales.rw_zebra_kg_translator import MeasureCatalog

_FORMAT_STRINGS = {
    0: "#,##0",
    1: "+#,##0;-#,##0",
    2: "+0.0%;-0.0%",
    3: "+#,##0.0;-#,##0.0",
}


def format_string_for(format_code: int) -> str:
    """Map Zebra format-code enum to a Power BI format-string.

    Per Zebra atlas §4 encoding reference. Unknown codes fall back to integer.
    """
    return _FORMAT_STRINGS.get(format_code, "#,##0")


def synthesize_dax(spec: ColumnSpec, catalog: MeasureCatalog) -> str | None:
    """Generate the DAX expression for a synthesized IBCS column.

    Returns None if any base scenario isn't in the catalog.
    """
    resolved = [catalog.resolve(s) for s in spec.base]
    if any(r is None for r in resolved):
        return None
    names = [r[1] for r in resolved]
    if spec.role == "absolute":
        return f"[{names[0]}]"
    if spec.role == "delta":
        body = f"[{names[0]}] - [{names[1]}]"
        return f"({body}) * -1" if spec.is_cost else body
    if spec.role == "relative":
        body = f"DIVIDE([{names[0]}] - [{names[1]}], ABS([{names[1]}]))"
        return f"({body}) * -1" if spec.is_cost else body
    return None


_KNOWN_SCENARIOS = ("AC", "PY", "PL", "FC")
_NON_AC_ORDER = ("PY", "PL", "FC")


def synthesize_ibcs_columns(
    scenarios: set[str],
    is_cost: bool = False,
) -> list[ColumnSpec]:
    """Generate the canonical IBCS column set for a scenario combination.

    Encodes Zebra atlas §3 column synthesis rule: pair (AC, Y) projections
    auto-derive `<AC>-<Y>` (delta, format_code=1) and `<AC>-<Y> %` (relative,
    format_code=2). Variance pairs only emit when AC is present.

    Order: all known absolutes (AC, PY, PL, FC) in canonical order, then each
    (AC, Y) pair's delta + relative for Y in (PY, PL, FC).

    Unknown scenarios are silently dropped.
    """
    present = [s for s in _KNOWN_SCENARIOS if s in scenarios]
    out: list[ColumnSpec] = [
        ColumnSpec(name=s, role="absolute", base=(s,), format_code=0, is_cost=is_cost)
        for s in present
    ]
    if "AC" not in present:
        return out
    for y in _NON_AC_ORDER:
        if y in present:
            out.append(
                ColumnSpec(
                    name=f"AC-{y}",
                    role="delta",
                    base=("AC", y),
                    format_code=1,
                    is_cost=is_cost,
                )
            )
            out.append(
                ColumnSpec(
                    name=f"AC-{y} %",
                    role="relative",
                    base=("AC", y),
                    format_code=2,
                    is_cost=is_cost,
                )
            )
    return out


def build_databar_cf_objects(
    column_name: str,
    max_field: str,
    positive_color: str,
    negative_color: str = "#C00000",
) -> dict:
    """DataBars conditional-formatting block for one tableEx column.

    Returns a partial singleVisual.objects dict suitable for merging into
    build_table_visual(objects=...). Encodes the Zebra bullet-bar markerStyle=5
    look as native PBI dataBars: positive_color for the bar, negative_color for
    negative values, and a field-driven max via max_field ('Table.Measure' ref)
    so multiple columns share an axis (Zebra scaleGroup behaviour).

    Per native atlas §2 conditional-formatting reference.
    """
    if "." not in max_field:
        raise ValueError(f"max_field must be 'Table.Measure', got: {max_field!r}")
    max_table, max_measure = max_field.split(".", 1)
    return {
        "values": [
            {
                "selector": {"metadata": column_name},
                "properties": {
                    "axis": {
                        "solid": {"color": {"expr": {"Literal": {"Value": f"'{positive_color}'"}}}}
                    },
                    "negativeBarColor": {
                        "solid": {"color": {"expr": {"Literal": {"Value": f"'{negative_color}'"}}}}
                    },
                    "maxValue": {
                        "expr": {
                            "Measure": {
                                "Expression": {"SourceRef": {"Entity": max_table}},
                                "Property": max_measure,
                            }
                        }
                    },
                    "axisColor": {
                        "solid": {"color": {"expr": {"Literal": {"Value": "'#999999'"}}}}
                    },
                },
            }
        ]
    }


from scripts.sales._pbir_helpers import (  # noqa: E402
    build_card_visual_with_objects,
    build_textbox_visual,
)


def _card_literal(value: str | int | bool) -> dict:
    if isinstance(value, bool):
        encoded = "true" if value else "false"
    elif isinstance(value, int):
        encoded = f"{value}L"
    else:
        encoded = f"'{value}'"
    return {"expr": {"Literal": {"Value": encoded}}}


def _card_color(color: str) -> dict:
    return {"solid": {"color": _card_literal(color)}}


def zebra_card_style_objects(*, value_font_size: int = 18, label_font_size: int = 8, accent: str = "#083EA7") -> dict:
    return {
        "background": [{"properties": {"show": _card_literal(True), "color": _card_color("#FFFFFF"), "transparency": _card_literal(0)}}],
        "border": [{"properties": {"show": _card_literal(True), "color": _card_color("#D8DEE8"), "radius": _card_literal(4)}}],
        "labels": [{"properties": {"fontSize": _card_literal(value_font_size), "color": _card_color("#252423")}}],
        "categoryLabels": [{"properties": {"fontSize": _card_literal(label_font_size), "color": _card_color(accent)}}],
    }

def build_composite_kpi_tile(
    label: str,
    value_table: str,
    value_measure: str,
    variance_table: str | None,
    variance_measure: str | None,
    x: float,
    y: float,
    w: float,
    h: float,
) -> list[dict]:
    """Three-VC stack approximating the Zebra Cards KPI tile.

    - header textbox: top 24px, full width
    - value card: middle, full width minus variance footprint when variance present
    - variance card (optional): bottom-right corner, 30% width × 24px

    All VCs sit within the (x, y, w, h) bounding box per native atlas §6 row 14.
    """
    header_h = 24
    variance_w = w * 0.30 if variance_measure else 0.0
    variance_h = 24 if variance_measure else 0.0

    out: list[dict] = [
        build_textbox_visual(
            text=label,
            x=x,
            y=y,
            w=w,
            h=header_h,
            font_size_pt=10,
            color="#666666",
        ),
        build_card_visual_with_objects(
            measure_table=value_table,
            measure_name=value_measure,
            display_title=value_measure,
            x=x,
            y=y + header_h,
            w=w - variance_w,
            h=h - header_h,
            objects=zebra_card_style_objects(value_font_size=18, label_font_size=8),
        ),
    ]
    if variance_measure:
        out.append(
            build_card_visual_with_objects(
                measure_table=variance_table,
                measure_name=variance_measure,
                display_title="",
                x=x + (w - variance_w),
                y=y + (h - variance_h),
                w=variance_w,
                h=variance_h,
                objects=zebra_card_style_objects(value_font_size=6, label_font_size=4, accent="#3B8A3E"),
            )
        )
    return out
