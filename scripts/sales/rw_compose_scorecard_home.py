"""Compose the front 'VP Ops Scorecard' page of rpt_vp_ops_scorecard.

This replaces the legacy 26-card landing page with a GraphRAG-routed
executive triage page. The KPI graph decides what earns front-page space:
risk signals first, then high-impact operating lanes, then two data surfaces
that point RW to the deeper tabs.

Run:
    python3 -m scripts.sales.rw_compose_scorecard_home
"""

from __future__ import annotations

from scripts.sales._pbir_helpers import (
    build_matrix_visual,
    build_matrix_style_objects,
    build_rag_card_visual,
    build_shape_visual,
    build_slicer_visual,
    build_table_style_objects,
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
from scripts.sales.rw_kpi_graph import find_kpi

PAGE = "VP Ops Scorecard"

NAVY = "#1A1D31"
BLUE = "#083EA7"
MUTED = "#666666"
LIGHT = "#f5f7fa"
BORDER = "#dddddd"
RED = "#cc3333"
AMBER = "#dd8800"
GREEN = "#339933"
RED_TINT = "#ffeeee"
AMBER_TINT = "#fff8e6"
GREEN_TINT = "#eef9ee"

FRONT_PAGE_KPI_ROUTES = {
    "growth_arr": ("forecast_closed_won", "opp_win_rate"),
    "pipeline_discipline": ("pipeline_coverage_3x", "stage_conversion"),
    "renewal_acv": ("renewal_retention_rate", "renewals_mom_trend"),
    "portfolio_map": ("stage_conversion", "pipeline_coverage_3x"),
    "deal_inspection": ("opp_age", "forecast_accuracy"),
}


def _target_line(route: str) -> str:
    parts = []
    for kpi_id in FRONT_PAGE_KPI_ROUTES[route]:
        kpi = find_kpi(kpi_id)
        if kpi is None:
            raise RuntimeError(f"front-page KPI route {route!r} references missing {kpi_id!r}")
        parts.append(f"{kpi.name}: {kpi.target_text}")
    return " | ".join(parts)


def _find_page(rj: dict) -> dict:
    for s in rj["sections"]:
        if s.get("displayName") == PAGE:
            return s
    raise SystemExit(
        f"page {PAGE!r} not found; have: {[s.get('displayName') for s in rj['sections']]}"
    )


def _panel(
    section: dict,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    fill: str = LIGHT,
    line: str = BORDER,
    accent: str | None = None,
    z: int = 80,
) -> None:
    section["visualContainers"].append(
        build_shape_visual(x=x, y=y, w=w, h=h, fill=fill, line=line, z=z, radius=4)
    )
    if accent:
        section["visualContainers"].append(
            build_shape_visual(x=x, y=y, w=6, h=h, fill=accent, line=accent, z=z + 1)
        )


def _risk_panel(
    section: dict,
    *,
    title: str,
    count_measure: str,
    value_measure: str,
    note: str,
    x: float,
    tint: str,
    accent: str,
) -> None:
    _panel(section, x=x, y=100, w=300, h=140, fill=tint, line=accent, accent=accent)
    section["visualContainers"].append(
        build_textbox_visual(title, x=x + 16, y=110, w=270, h=20, font_size_pt=10, color=accent)
    )
    section["visualContainers"].append(
        build_textbox_visual(
            note,
            x=x + 16,
            y=130,
            w=270,
            h=16,
            font_size_pt=8,
            color=MUTED,
            bold=False,
        )
    )
    section["visualContainers"].append(
        build_rag_card_visual(
            "f_opportunity",
            count_measure,
            "Deals",
            x=x + 16,
            y=150,
            w=126,
            h=72,
            tint=tint,
            accent=accent,
            value_font_size=28,
        )
    )
    section["visualContainers"].append(
        build_rag_card_visual(
            "f_opportunity",
            value_measure,
            "ARR exposure",
            x=x + 156,
            y=150,
            w=128,
            h=72,
            tint=tint,
            accent=accent,
            value_font_size=22,
            display_units=1000000,
        )
    )


def _lane_panel(
    section: dict,
    *,
    title: str,
    note: str,
    x: float,
    accent: str,
    cards: tuple[tuple[str, str, str, int | None], tuple[str, str, str, int | None]],
) -> None:
    _panel(section, x=x, y=286, w=300, h=132, fill="#ffffff", line=BORDER, accent=accent)
    section["visualContainers"].append(
        build_textbox_visual(title, x=x + 16, y=296, w=270, h=20, font_size_pt=10, color=accent)
    )
    section["visualContainers"].append(
        build_textbox_visual(
            note,
            x=x + 16,
            y=316,
            w=270,
            h=16,
            font_size_pt=8,
            color=MUTED,
            bold=False,
        )
    )
    for i, (table, measure, card_title, units) in enumerate(cards):
        section["visualContainers"].append(
            build_rag_card_visual(
                table,
                measure,
                card_title,
                x=x + 16 + i * 140,
                y=344,
                w=126,
                h=58,
                tint="#ffffff",
                accent=accent,
                value_font_size=20,
                display_units=units,
            )
        )


def _compose(section: dict) -> None:
    """Build the front-page control room.

    Contract:
    - No card wall: cards are grouped into explicit risk and operating lanes.
    - No ARR/ACV blend except the bottom matrix, explicitly labeled as the
      cross-motion Total Open Pipeline Value measure.
    - No canvas overflow on a 1280x720 page.
    """
    section["visualContainers"].append(
        build_textbox_visual(
            "RW VP OPS CONTROL ROOM",
            x=20,
            y=12,
            w=760,
            h=28,
            font_size_pt=16,
            color=NAVY,
        )
    )
    section["visualContainers"].append(
        build_textbox_visual(
            "GraphRAG-routed front page: retrieve high-impact KPI graph signals, group by operating job, route diagnosis to detail tabs.",
            x=20,
            y=42,
            w=920,
            h=20,
            font_size_pt=9,
            color=MUTED,
            bold=False,
        )
    )

    # Left rail: filters and operating contract.
    _panel(section, x=20, y=80, w=220, h=230, fill=LIGHT, line=BORDER, accent=BLUE)
    section["visualContainers"].append(
        build_textbox_visual("FILTERS", x=36, y=90, w=180, h=18, font_size_pt=10, color=NAVY)
    )
    slicers = [
        ("d_region", "region", "Region", 114),
        ("d_calendar", "fiscal_quarter", "Fiscal Quarter", 180),
        ("f_opportunity", "motion_type", "Motion", 246),
    ]
    for table, column, title, y in slicers:
        section["visualContainers"].append(
            build_slicer_visual(table, column, title, x=36, y=y, w=188, h=54)
        )

    _panel(section, x=20, y=330, w=220, h=350, fill="#ffffff", line=BORDER, accent=NAVY)
    section["visualContainers"].append(
        build_textbox_visual(
            "GRAPHRAG ROUTING", x=36, y=342, w=180, h=18, font_size_pt=10, color=NAVY
        )
    )
    for text, y in [
        ("31 target KPIs in KG", 374),
        ("Live high-impact retrieval", 404),
        ("ARR lane: Land + Expand", 434),
        ("ACV lane: Renewal only", 464),
        ("Cross-motion value labeled", 494),
        ("Diagnosis stays on job tabs", 524),
    ]:
        section["visualContainers"].append(
            build_textbox_visual(text, x=36, y=y, w=180, h=18, font_size_pt=9, color=MUTED)
        )

    # Top risk band. These are daily triage measures, not static scorecard KPIs.
    section["visualContainers"].append(
        build_textbox_visual(
            "OPERATING SIGNALS - what needs attention now",
            x=260,
            y=74,
            w=960,
            h=20,
            font_size_pt=10,
            color=MUTED,
        )
    )
    _risk_panel(
        section,
        title="AT RISK - slipped or backward",
        count_measure="At Risk Opps Count",
        value_measure="At Risk Opps ARR",
        note="Late-stage slippage, regression, or inspection breach",
        x=260,
        tint=RED_TINT,
        accent=RED,
    )
    _risk_panel(
        section,
        title="WATCH - stalled motion",
        count_measure="Watch Opps Count",
        value_measure="Watch Opps ARR",
        note="Stage 3-4 stalls and stalled open motion",
        x=580,
        tint=AMBER_TINT,
        accent=AMBER,
    )
    _risk_panel(
        section,
        title="HEALTHY - forward movement",
        count_measure="Healthy Moves Count",
        value_measure="Healthy Moves ARR",
        note="Forward progressions, new opps, or wins",
        x=900,
        tint=GREEN_TINT,
        accent=GREEN,
    )

    # GraphRAG-selected operating lanes from rw_kpi_graph.py.
    section["visualContainers"].append(
        build_textbox_visual(
            "KPI LANES - high-impact signals from the RW KPI graph",
            x=260,
            y=258,
            w=960,
            h=20,
            font_size_pt=10,
            color=MUTED,
        )
    )
    _lane_panel(
        section,
        title="GROWTH ARR",
        note=_target_line("growth_arr"),
        x=260,
        accent=BLUE,
        cards=(
            ("f_opportunity", "Total Closed Won ARR", "Won ARR", 1000000),
            ("f_opportunity", "Win Rate ARR", "Win rate", None),
        ),
    )
    _lane_panel(
        section,
        title="PIPELINE DISCIPLINE",
        note=_target_line("pipeline_discipline"),
        x=580,
        accent=AMBER,
        cards=(
            ("f_opportunity", "Total Open Pipeline ARR", "Open ARR", 1000000),
            ("f_stage_transition", "Stage Forward Pct (LE)", "Stage fwd", None),
        ),
    )
    _lane_panel(
        section,
        title="RENEWAL ACV",
        note=_target_line("renewal_acv"),
        x=900,
        accent=GREEN,
        cards=(
            ("f_opportunity", "Renewal Retention Pct (Period)", "Retention", None),
            ("f_opportunity", "Total Renewal ACV Won", "Won ACV", 1000000),
        ),
    )

    # Bottom: real data surfaces, not another row of KPI cards.
    _panel(section, x=252, y=432, w=476, h=256, fill="#ffffff", line=BORDER, accent=BLUE)
    _panel(section, x=736, y=432, w=492, h=256, fill="#ffffff", line=BORDER, accent=NAVY)
    section["visualContainers"].append(
        build_textbox_visual(
            "PORTFOLIO MAP - open value by stage and motion",
            x=260,
            y=442,
            w=460,
            h=20,
            font_size_pt=10,
            color=MUTED,
        )
    )
    section["visualContainers"].append(
        build_textbox_visual(
            _target_line("portfolio_map"),
            x=260,
            y=462,
            w=460,
            h=14,
            font_size_pt=8,
            color=MUTED,
            bold=False,
        )
    )
    section["visualContainers"].append(
        build_matrix_visual(
            rows=[{"table": "f_opportunity", "field": "stage_name", "title": "Stage"}],
            columns=[{"table": "f_opportunity", "field": "motion_type", "title": "Motion"}],
            values=[
                {
                    "table": "f_opportunity",
                    "field": "Total Open Pipeline Value",
                    "title": "Open Value",
                }
            ],
            x=260,
            y=482,
            w=460,
            h=198,
            objects=build_matrix_style_objects(),
        )
    )
    section["visualContainers"].append(
        build_textbox_visual(
            "NEXT DEALS TO INSPECT - open pipeline by value",
            x=744,
            y=442,
            w=476,
            h=20,
            font_size_pt=10,
            color=MUTED,
        )
    )
    section["visualContainers"].append(
        build_textbox_visual(
            _target_line("deal_inspection"),
            x=744,
            y=462,
            w=476,
            h=14,
            font_size_pt=8,
            color=MUTED,
            bold=False,
        )
    )
    section["visualContainers"].append(
        build_table_visual(
            name="front_page_deal_inspection",
            columns=[
                {"table": "f_opportunity", "field": "opp_name", "kind": "column", "title": "Opp"},
                {
                    "table": "f_opportunity",
                    "field": "account_name",
                    "kind": "column",
                    "title": "Account",
                },
                {"table": "f_opportunity", "field": "region", "kind": "column", "title": "Region"},
                {
                    "table": "f_opportunity",
                    "field": "stage_name",
                    "kind": "column",
                    "title": "Stage",
                },
                {
                    "table": "f_opportunity",
                    "field": "Total Open Pipeline Value",
                    "kind": "measure",
                    "title": "Open Value",
                },
            ],
            x=744,
            y=482,
            w=476,
            h=198,
            objects=build_table_style_objects(),
        )
    )


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
