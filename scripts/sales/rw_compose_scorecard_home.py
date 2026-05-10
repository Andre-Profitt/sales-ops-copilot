"""Compose the front 'VP Ops Scorecard' page of rpt_vp_ops_scorecard.

Native Zebra/IBCS layout: KPI pulse + exception spine + stage distribution +
stage hygiene + 7-day movement pulse. Replaces the prior card wall without
using tenant-blocked custom visuals.

Run:
    python3 -m scripts.sales.rw_compose_scorecard_home
"""

from __future__ import annotations

import json

from scripts.sales._pbir_helpers import (
    build_card_visual_with_objects,
    build_clustered_bar_chart_visual,
    build_matrix_visual,
    build_shape_visual,
    build_table_visual,
    build_textbox_visual,
)
from scripts.sales.rw_add_visual import (
    REPORT_ID,
    WORKSPACE_ID,
    _token,
    get_current_report_json,
    push_report,
)
from scripts.sales.rw_validate import fetch_measures_by_table, validate_visual_dict
from scripts.sales.rw_zebra_kg_ibcs_synth import (
    zebra_exception_ledger_objects,
    zebra_native_card_objects,
    zebra_stage_hygiene_table_objects,
)

PAGE = "VP Ops Scorecard"
CANVAS_W = 1280
CANVAS_H = 720
MARGIN = 24
GAP = 12

KPI_STRIP_MEASURES = [
    "Total Closed Won ARR",
    "Win Rate ARR",
    "Exception ARR",
    "Renewal Retention Pct (Period)",
]

MOVEMENT_PULSE_MEASURES = [
    "New Opps Count 7d",
    "Closed Won Count 7d",
    "Stage Moves ARR 7d",
    "Backward Moves Count 7d",
]


def _panel(x: float, y: float, w: float, h: float, *, fill: str = "#FFFFFF") -> dict:
    return build_shape_visual(x=x, y=y, w=w, h=h, fill=fill, line="#D8DEE8", z=40, radius=2)


def _literal(value: str | int | float | bool) -> dict:
    if isinstance(value, bool):
        encoded = "true" if value else "false"
    elif isinstance(value, int):
        encoded = f"{value}L"
    elif isinstance(value, float):
        encoded = f"{value}D"
    else:
        encoded = f"'{value}'"
    return {"expr": {"Literal": {"Value": encoded}}}


def _solid_color(color: str) -> dict:
    return {"solid": {"color": _literal(color)}}


def _with_title(vc: dict, title: str) -> dict:
    """Attach a native visual title. More reliable than free-floating textboxes."""
    config = json.loads(vc["config"])
    sv = config["singleVisual"]
    sv.setdefault("vcObjects", {})["title"] = [
        {
            "properties": {
                "show": _literal(True),
                "text": _literal(title),
                "fontColor": _solid_color("#1A1D31"),
                "fontSize": _literal("11"),
                "fontFamily": _literal("Segoe UI Semibold"),
                "titleWrap": _literal(False),
                "alignment": _literal("left"),
            }
        }
    ]
    vc["config"] = json.dumps(config)
    return vc


def _zebra_card_visual(
    *,
    table: str,
    measure: str,
    title: str,
    x: float,
    y: float,
    w: float,
    h: float,
    tint: str,
    accent: str,
    value_color: str,
    value_font_size: int,
    label_font_size: int,
    pattern: str,
    visual_intent: str,
) -> dict:
    return build_card_visual_with_objects(
        measure_table=table,
        measure_name=measure,
        display_title=title,
        x=x,
        y=y,
        w=w,
        h=h,
        objects=zebra_native_card_objects(
            pattern=pattern,
            visual_intent=visual_intent,
            tint=tint,
            accent=accent,
            value_color=value_color,
            label_color=accent,
            value_font_size=value_font_size,
            label_font_size=label_font_size,
        ),
    )


def _build_header() -> list[dict]:
    return [
        build_textbox_visual(
            text="RW VP Ops Control Room",
            x=28,
            y=12,
            w=520,
            h=28,
            font_size_pt=19,
            color="#1A1D31",
            bold=True,
        ),
        build_textbox_visual(
            text="Exceptions first. Basis stays explicit: ARR (Land + Expand), renewal ACV, ARR-wtd %, count rates.",
            x=28,
            y=42,
            w=840,
            h=20,
            font_size_pt=9,
            color="#5C6670",
            bold=False,
        ),
    ]


def _build_exception_spine() -> dict:
    """Native equivalent of the Zebra exception table.

    Region first, then IBCS-style actual/problem columns. This keeps the proven
    Zebra table binding order while avoiding custom visual tenant policy.
    """
    return build_table_visual(
        name="rw_exception_spine",
        columns=[
            {"table": "d_region", "field": "region", "kind": "column", "title": "Region"},
            {
                "table": "f_opportunity",
                "field": "Exception ARR",
                "kind": "measure",
                "title": "Exception ARR (Land + Expand)",
            },
            {
                "table": "f_opportunity",
                "field": "Exception Opps Count",
                "kind": "measure",
                "title": "Opp count",
            },
            {
                "table": "f_opportunity",
                "field": "At Risk Opps ARR",
                "kind": "measure",
                "title": "At-risk ARR (Land + Expand)",
            },
            {
                "table": "f_opportunity",
                "field": "Watch Opps ARR",
                "kind": "measure",
                "title": "Watch ARR (Land + Expand)",
            },
        ],
        x=40,
        y=258,
        w=736,
        h=210,
        objects=zebra_exception_ledger_objects(),
    )


def _build_kpi_strip() -> list[dict]:
    """Four executive KPI tiles, native-card version of Zebra BI Cards."""
    card_w = (CANVAS_W - 2 * MARGIN - 3 * GAP) / 4
    cards = [
        (
            "f_opportunity",
            "Total Closed Won ARR",
            "Closed won ARR (Land + Expand)",
            "#F4F7FB",
            "#2B5C8A",
            "#1A1D31",
            1000000,
        ),
        (
            "f_opportunity",
            "Win Rate ARR",
            "Win rate (ARR-wtd)",
            "#EEF9EE",
            "#3B8A3E",
            "#1F6F3B",
            None,
        ),
        (
            "f_opportunity",
            "Exception ARR",
            "Exception ARR (Land + Expand)",
            "#FFEEEE",
            "#C33A32",
            "#B3261E",
            1000000,
        ),
        (
            "f_opportunity",
            "Renewal Retention Pct (Period)",
            "Retention % (ACV-wtd)",
            "#EEF9EE",
            "#3B8A3E",
            "#1F6F3B",
            None,
        ),
    ]
    out: list[dict] = []
    for i, (table, measure, title, tint, accent, value_color, _display_units) in enumerate(cards):
        x = MARGIN + i * (card_w + GAP)
        out.append(build_shape_visual(x=x, y=88, w=card_w, h=116, fill="#FFFFFF", line="#D8DEE8", z=30, radius=2))
        out.append(
            _zebra_card_visual(
                table=table,
                measure=measure,
                title=title,
                x=x,
                y=88,
                w=card_w,
                h=116,
                tint=tint,
                accent=accent,
                value_color=value_color,
                value_font_size=24,
                label_font_size=9,
                pattern="vp-ops-scorecard-hero-card",
                visual_intent="executive KPI strip",
            )
        )
    return out


def _build_exception_panel() -> list[dict]:
    return [
        _panel(24, 226, 768, 260),
        _with_title(_build_exception_spine(), "Exception Spine by Region"),
    ]


def _build_stage_distribution_panel() -> list[dict]:
    chart = build_clustered_bar_chart_visual(
        category_table="f_opportunity",
        category_column="stage_name",
        category_title="Stage",
        measure_table="f_opportunity",
        measure_name="Total Open Pipeline ARR",
        measure_title="Open ARR (Land + Expand)",
        x=820,
        y=258,
        w=420,
        h=210,
        fill="#2B5C8A",
    )
    return [
        _panel(804, 226, 452, 260),
        _with_title(chart, "Open ARR (Land + Expand) by Stage"),
    ]


def _build_stage_hygiene_panel() -> list[dict]:
    matrix = build_matrix_visual(
        rows=[
            {
                "table": "f_stage_transition",
                "field": "from_stage_name",
                "title": "Stage",
            }
        ],
        columns=[],
        values=[
            {
                "table": "f_stage_transition",
                "field": "Stage Forward Pct (LE)",
                "title": "Forward % (count, Land + Expand)",
            },
            {
                "table": "f_stage_transition",
                "field": "Stage Backward Pct (LE)",
                "title": "Backward % (count, Land + Expand)",
            },
            {
                "table": "f_stage_transition",
                "field": "Avg Days In Prior Stage (LE)",
                "title": "Avg days",
            },
            {
                "table": "f_stage_transition",
                "field": "Stage Moves ARR 7d",
                "title": "7d ARR moved (Land + Expand)",
            },
        ],
        x=40,
        y=540,
        w=736,
        h=140,
        objects=zebra_stage_hygiene_table_objects(
            max_field="f_stage_transition.Stage Moves ARR 7d",
            databar_column="f_stage_transition.Stage Moves ARR 7d",
        ),
    )
    return [
        _panel(24, 508, 768, 188),
        _with_title(matrix, "Stage Hygiene (count rates, Land + Expand)"),
    ]


def _build_movement_pulse() -> list[dict]:
    specs = [
        (
            "f_opportunity",
            "New Opps Count 7d",
            "New opp count 7d",
            "#F4F7FB",
            "#2B5C8A",
            None,
        ),
        (
            "f_opportunity",
            "Closed Won Count 7d",
            "Won count 7d",
            "#EEF9EE",
            "#3B8A3E",
            None,
        ),
        (
            "f_stage_transition",
            "Stage Moves ARR 7d",
            "Stage ARR 7d (Land + Expand)",
            "#FFF8E6",
            "#D98A00",
            1000000,
        ),
        (
            "f_stage_transition",
            "Backward Moves Count 7d",
            "Back move count",
            "#FFEEEE",
            "#C33A32",
            None,
        ),
    ]
    out: list[dict] = [_panel(804, 508, 452, 188)]
    tile_w = 204
    tile_h = 60
    for i, (table, measure, title, tint, accent, _display_units) in enumerate(specs):
        col = i % 2
        row = i // 2
        x = 820 + col * (tile_w + 12)
        y = 540 + row * (tile_h + 10)
        out.append(build_shape_visual(x=x, y=y, w=tile_w, h=tile_h, fill="#FFFFFF", line="#D8DEE8", z=30, radius=2))
        out.append(
            _zebra_card_visual(
                table=table,
                measure=measure,
                title=title,
                x=x,
                y=y,
                w=tile_w,
                h=tile_h,
                tint=tint,
                accent=accent,
                value_color="#1A1D31",
                value_font_size=18,
                label_font_size=8,
                pattern="vp-ops-scorecard-movement-pulse-card",
                visual_intent="7-day movement pulse",
            )
        )
    return out


def _find_page(rj: dict) -> dict:
    for s in rj["sections"]:
        if s.get("displayName") == PAGE:
            return s
    raise SystemExit(
        f"page {PAGE!r} not found; have: {[s.get('displayName') for s in rj['sections']]}"
    )


def _compose(section: dict) -> None:
    """Compose the VP Ops Scorecard front page.

    Drops the inherited page-level filters. The original card-wall layout had a
    `FilterYear` page filter targeting `d_calendar[year] = 2026`. That filter
    intersects badly with `Total Closed Won ARR` which has its own date logic
    in the deployed DAX, surfacing as $0. Each measure does its own scoping;
    the page is filter-agnostic at the page level.
    """
    section["filters"] = "[]"
    section["visualContainers"] = [
        *_build_header(),
        *_build_kpi_strip(),
        *_build_exception_panel(),
        *_build_stage_distribution_panel(),
        *_build_stage_hygiene_panel(),
        *_build_movement_pulse(),
    ]


def main() -> None:
    print(f"composing {PAGE!r} on rpt_vp_ops_scorecard")
    token = _token()
    print("  fetching report.json...")
    rj = get_current_report_json(token)
    section = _find_page(rj)
    print(f"  current visuals: {len(section.get('visualContainers', []))} (clearing)")
    section["visualContainers"] = []

    _compose(section)
    print(f"  composed: {len(section['visualContainers'])} visuals")

    print("  pre-flighting measure refs...")
    by_table = fetch_measures_by_table()
    errors: list[str] = []
    for vc in section["visualContainers"]:
        errors.extend(validate_visual_dict(vc, by_table))
    if errors:
        raise SystemExit("\n".join(["pre-flight validation FAILED:"] + errors))
    print(
        f"  pre-flight: all refs resolve against {sum(len(v) for v in by_table.values())} measures"
    )

    print(f"\npushing; total visuals on {PAGE!r}: {len(section['visualContainers'])}")
    push_report(token, rj)
    print(
        f"\ndone. open: https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/reports/{REPORT_ID}"
    )


if __name__ == "__main__":
    main()
