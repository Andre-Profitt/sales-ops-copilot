"""IBCS column synthesis, DAX synthesis, conditional formatting + composite tile builders.

Encodes the rules documented in:
- docs/sales/RW_ZEBRA_BI_INFRASTRUCTURE_ATLAS.md §3 (column synthesis grammar)
- docs/sales/RW_ZEBRA_BI_INFRASTRUCTURE_ATLAS.md §6 (Cards rendering grammar)
- docs/sales/RW_POWER_BI_NATIVE_INFRASTRUCTURE_ATLAS.md §2 (CF reference)

This module is pure (no I/O, no network); consumed by rw_zebra_kg_translator.
"""

from __future__ import annotations

import json
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


def build_cell_background_cf_object(
    column_name: str,
    color_field: str,
    *,
    font_color: str = "#111111",
) -> dict:
    """Field-value cell background conditional formatting for one tableEx column.

    `color_field` is a DAX measure that returns a hex color string. This is the
    native Power BI heatmap path: the measure owns the scale logic, while the
    report JSON binds that scale to the cell background for the selected column.
    """
    if "." not in color_field:
        raise ValueError(f"color_field must be 'Table.Measure', got: {color_field!r}")
    color_table, color_measure = color_field.split(".", 1)
    color_expr = {
        "expr": {
            "Measure": {
                "Expression": {"SourceRef": {"Entity": color_table}},
                "Property": color_measure,
            }
        }
    }
    return {
        "selector": {"metadata": column_name},
        "properties": {
            "backColor": {"solid": {"color": color_expr}},
            "backColorPrimary": {"solid": {"color": color_expr}},
            "fontColor": _card_color(font_color),
            "fontColorPrimary": _card_color(font_color),
        },
    }


from scripts.sales._pbir_helpers import (  # noqa: E402
    build_card_visual_with_objects,
    build_rag_card_objects,
    build_shape_visual,
    build_table_style_objects,
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


ZEBRA_TRANSFER_SAFE_GROUPS = [
    "chartSettings",
    "coreSettings",
    "dataLabelSettings",
    "titleSettings",
]


def _with_zebra_transfer_metadata(objects: dict, *, pattern: str, visual_intent: str, grammar_schema: str) -> dict:
    """Attach safe Zebra-DNA lineage metadata to native visual objects.

    The metadata is deliberately tiny and contains no raw Zebra object payloads;
    it records which reusable grammar drove the native formatting so downstream
    audits can distinguish Zebra-derived styling from generic native defaults.
    """
    enriched = dict(objects)
    enriched["stylePreset"] = {
        "source": "zebra-visual-dna",
        "pattern": pattern,
        "visual_intent": visual_intent,
    }
    enriched["zebraGrammar"] = {
        "schema": grammar_schema,
        "safe_groups": ZEBRA_TRANSFER_SAFE_GROUPS,
    }
    return enriched


def tag_visual_with_zebra_transfer_metadata(
    visual: dict,
    *,
    pattern: str,
    visual_intent: str,
    grammar_schema: str = "rw-zebra-native-transfer.visualObjectGrammar.v1",
) -> dict:
    """Attach safe Zebra-DNA lineage metadata to an existing native visual."""
    config = json.loads(visual["config"])
    single_visual = config.setdefault("singleVisual", {})
    objects = single_visual.setdefault("objects", {})
    single_visual["objects"] = _with_zebra_transfer_metadata(
        objects,
        pattern=pattern,
        visual_intent=visual_intent,
        grammar_schema=grammar_schema,
    )
    visual["config"] = json.dumps(config)
    return visual


def zebra_native_card_objects(
    *,
    pattern: str = "composite-risk-kpi-card",
    visual_intent: str = "KPI strip",
    tint: str,
    accent: str,
    surface: str = "#FFFFFF",
    border: str = "#D8DEE8",
    value_color: str = "#222222",
    label_color: str | None = None,
    value_font_size: int = 28,
    label_font_size: int = 10,
    display_units: int | None = None,
    use_semantic_color: bool = False,
) -> dict:
    """Zebra-card-inspired native card object grammar for RW pages.

    Zebra/IBCS transfers should read like finance-operating dashboards:
    neutral card surfaces, quiet borders, and neutral label typography. Semantic
    color belongs in variance cells, bars, and heatmap encodings, not in every
    top-strip KPI tile.
    The source tint argument remains for API compatibility with older composers,
    but the native card background deliberately stays neutral to avoid pastel
    RAG tiles.
    """
    effective_value_color = value_color if use_semantic_color else "#1A1D31"
    effective_label_color = label_color if use_semantic_color else "#3A4653"
    return _with_zebra_transfer_metadata(
        build_rag_card_objects(
            tint=surface,
            accent=border,
            value_color=effective_value_color,
            label_color=effective_label_color or "#3A4653",
            value_font_size=value_font_size,
            label_font_size=label_font_size,
            display_units=display_units,
        ),
        pattern=pattern,
        visual_intent=visual_intent,
        grammar_schema="rw-zebra-native-transfer.visualObjectGrammar.v1",
    )


def zebra_kpi_strip_card_objects(
    *,
    pattern: str = "executive-kpi-strip-card",
    visual_intent: str = "executive KPI strip",
    value_font_size: int = 20,
    label_font_size: int = 8,
    display_units: int | None = None,
) -> dict:
    """Frameless KPI typography for cards placed inside a shared scorecard band.

    This is the native Power BI equivalent of a Zebra/IBCS scorecard strip: one
    shared panel provides the surface, while individual card visuals carry only
    value/label typography. It avoids the floating tile/card-wall look.
    """
    objects = build_rag_card_objects(
        tint="#FFFFFF",
        accent="#D8DEE8",
        value_color="#1A1D31",
        label_color="#3A4653",
        value_font_size=value_font_size,
        label_font_size=label_font_size,
        display_units=display_units,
    )
    objects["background"] = [{"properties": {"show": _card_literal(False)}}]
    objects["border"] = [{"properties": {"show": _card_literal(False)}}]
    return _with_zebra_transfer_metadata(
        objects,
        pattern=pattern,
        visual_intent=visual_intent,
        grammar_schema="rw-zebra-native-transfer.visualObjectGrammar.v1",
    )


def zebra_kpi_value_card_objects(
    *,
    pattern: str = "executive-kpi-strip-value",
    visual_intent: str = "executive KPI strip value",
    value_font_size: int = 22,
    display_units: int | None = None,
) -> dict:
    """Value-only card grammar for strip metrics with labels rendered separately."""
    objects = build_rag_card_objects(
        tint="#FFFFFF",
        accent="#FFFFFF",
        value_color="#1A1D31",
        label_color="#3A4653",
        value_font_size=value_font_size,
        label_font_size=7,
        display_units=display_units,
        show_category_label=False,
    )
    objects["background"] = [{"properties": {"show": _card_literal(False)}}]
    objects["border"] = [{"properties": {"show": _card_literal(False)}}]
    return _with_zebra_transfer_metadata(
        objects,
        pattern=pattern,
        visual_intent=visual_intent,
        grammar_schema="rw-zebra-native-transfer.visualObjectGrammar.v1",
    )


def zebra_kpi_strip_metric(
    *,
    measure_table: str,
    measure_name: str,
    title: str,
    x: float,
    y: float,
    w: float,
    h: float,
    pattern: str,
    visual_intent: str,
    display_units: int | None = None,
    value_font_size: int = 22,
    divider: bool = False,
) -> list[dict]:
    """Consulting-style strip metric: static label + value-only native card."""
    visuals: list[dict] = [
        build_textbox_visual(
            title,
            x=x + 8,
            y=y + 4,
            w=w - 16,
            h=26,
            font_size_pt=8,
            color="#5C6670",
            bold=False,
        ),
        build_card_visual_with_objects(
            measure_table=measure_table,
            measure_name=measure_name,
            display_title=title,
            x=x + 4,
            y=y + 30,
            w=w - 8,
            h=max(62, h - 30),
            objects=zebra_kpi_value_card_objects(
                pattern=pattern,
                visual_intent=visual_intent,
                value_font_size=value_font_size,
                display_units=display_units,
            ),
        ),
    ]
    if divider:
        visuals.append(
            build_shape_visual(
                x=x - 8,
                y=y + 12,
                w=1,
                h=h - 24,
                fill="#E3E7EE",
                line="#E3E7EE",
                z=60,
                radius=0,
            )
        )
    return visuals


def zebra_compact_movement_ledger_objects(*, max_field: str, databar_column: str, accent: str = "#083EA7") -> dict:
    """Compact tableEx style for movement-ledger scans derived from Zebra tables."""
    objects = build_table_style_objects(
        header_fill="#FFFFFF",
        header_text="#1A1D31",
        row_text="#202124",
        grid="#D8DEE8",
        font_size=9,
    )
    objects = _with_zebra_transfer_metadata(
        objects,
        pattern="compact-movement-ledger",
        visual_intent="movement table",
        grammar_schema="rw-zebra-native-transfer.columnGrammar.v1",
    )
    objects["dataBars"] = build_databar_cf_objects(databar_column, max_field, accent)
    return objects


def zebra_exception_ledger_objects() -> dict:
    """Compact IBCS-style exception ledger for What Changed.

    This deliberately replaces KPI-card furniture with a single scan table:
    the business read is exception magnitude by status, not three decorative
    scorecards.
    """
    return _with_zebra_transfer_metadata(
        build_table_style_objects(
            header_fill="#FFFFFF",
            header_text="#1A1D31",
            row_text="#202124",
            grid="#D8DEE8",
            font_size=9,
        ),
        pattern="exception-band-ledger",
        visual_intent="exception movement ledger",
        grammar_schema="rw-zebra-native-transfer.columnGrammar.v1",
    )


def zebra_detail_table_objects() -> dict:
    """Dense opportunity-queue table style derived from the Zebra detail-ledger grammar."""
    return _with_zebra_transfer_metadata(
        build_table_style_objects(
            header_fill="#FFFFFF",
            header_text="#1A1D31",
            row_text="#202124",
            grid="#E3E7EE",
            font_size=8,
        ),
        pattern="detail-ledger",
        visual_intent="detail ledger",
        grammar_schema="rw-zebra-native-transfer.columnGrammar.v1",
    )


def zebra_heatmap_matrix_objects(
    *,
    pattern: str = "product-retention-heatmap",
    visual_intent: str = "product x segment heatmap matrix",
    databar_specs: tuple[tuple[str, str, str], ...] = (),
    background_specs: tuple[tuple[str, str], ...] = (),
) -> dict:
    """Matrix/table style for Zebra-inspired heatmap reads.

    Data bars carry Zebra bullet-bar intent; field-value cell backgrounds carry
    the actual heatmap encoding. A visual named heatmap should have
    background_specs, otherwise it is only a variance/data-bar table.
    """
    objects = _with_zebra_transfer_metadata(
        build_table_style_objects(
            header_fill="#FFFFFF",
            header_text="#1A1D31",
            row_text="#202124",
            grid="#D8DEE8",
            font_size=8,
        ),
        pattern=pattern,
        visual_intent=visual_intent,
        grammar_schema="rw-zebra-native-transfer.columnGrammar.v1",
    )
    if databar_specs:
        objects["dataBars"] = {
            "values": [
                bar
                for column_name, max_field, positive_color in databar_specs
                for bar in build_databar_cf_objects(column_name, max_field, positive_color)[
                    "values"
                ]
            ]
        }
    if background_specs:
        objects.setdefault("values", []).extend(
            build_cell_background_cf_object(column_name, color_field)
            for column_name, color_field in background_specs
        )
        objects["heatmapEncoding"] = {
            "type": "field-value-cell-background",
            "columns": [
                {"column": column_name, "colorMeasure": color_field}
                for column_name, color_field in background_specs
            ],
        }
    return objects


def zebra_stage_hygiene_table_objects(*, max_field: str, databar_column: str, accent: str = "#2B5C8A") -> dict:
    """Stage conversion/time-in-stage table style derived from Zebra variance grammar.

    This is intentionally tableEx-oriented, not a broad framework abstraction:
    Stage Hygiene needs a compact IBCS scan table where forward/backward rates,
    average age, transition counts, and moved ARR keep deterministic order, while
    a native data bar carries the Zebra scaleGroup/bullet-bar intent for the real
    ARR movement measure.
    """
    objects = build_table_style_objects(
        header_fill="#FFFFFF",
        header_text="#1A1D31",
        row_text="#202124",
        grid="#D8DEE8",
        font_size=8,
    )
    objects = _with_zebra_transfer_metadata(
        objects,
        pattern="stage-hygiene-variance-table",
        visual_intent="stage conversion and time-in-stage table",
        grammar_schema="rw-zebra-native-transfer.columnGrammar.v1",
    )
    objects["dataBars"] = build_databar_cf_objects(databar_column, max_field, accent)
    return objects


def zebra_card_style_objects(*, value_font_size: int = 18, label_font_size: int = 8, accent: str = "#5C6670") -> dict:
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
                objects=zebra_card_style_objects(value_font_size=6, label_font_size=4, accent="#5C6670"),
            )
        )
    return out
