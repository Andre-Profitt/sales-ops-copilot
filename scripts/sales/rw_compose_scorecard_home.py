"""Compose the front 'VP Ops Scorecard' page of rpt_vp_ops_scorecard.

This replaces the legacy 26-card landing page with an executive triage page.
The KPI graph decides what earns front-page space, but the canvas stays
business-facing: exceptions first, commercial engine second, deal evidence last.

Run:
    python3 -m scripts.sales.rw_compose_scorecard_home
"""

from __future__ import annotations

from scripts.sales._pbir_helpers import (
    build_clustered_bar_chart_visual,
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
RED = "#b3261e"
AMBER = "#a86400"
GREEN = "#2f7d32"
RED_TINT = "#fff4f4"
AMBER_TINT = "#fffbef"
GREEN_TINT = "#f5fbf5"

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
        parts.append(kpi.target_text)
    return "Targets: " + " | ".join(parts)


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


def _metric_card(
    section: dict,
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
    value_font_size: int,
) -> None:
    section["visualContainers"].append(
        build_rag_card_visual(
            table,
            measure,
            title,
            x=x,
            y=y,
            w=w,
            h=h,
            tint=tint,
            accent=accent,
            value_font_size=value_font_size,
            label_font_size=10,
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
        build_shape_visual(x=20, y=16, w=1208, h=58, fill=NAVY, line=NAVY, z=40, radius=2)
    )
    section["visualContainers"].append(
        build_textbox_visual(
            "RW VP OPS CONTROL ROOM",
            x=40,
            y=22,
            w=520,
            h=38,
            font_size_pt=17,
            color="#ffffff",
        )
    )
    section["visualContainers"].append(
        build_textbox_visual(
            "FY26 operating triage | EUR reporting currency | ARR and renewal ACV stay separated",
            x=600,
            y=30,
            w=600,
            h=34,
            font_size_pt=9,
            color="#d8dbe8",
            bold=False,
        )
    )

    # Left rail: filters and operating contract.
    _panel(section, x=20, y=92, w=208, h=236, fill=LIGHT, line=BORDER, accent=BLUE)
    section["visualContainers"].append(
        build_textbox_visual("FILTERS", x=36, y=106, w=172, h=36, font_size_pt=10, color=NAVY)
    )
    slicers = [
        ("d_region", "region", "Region", 134),
        ("d_calendar", "fiscal_quarter", "Fiscal Quarter", 198),
        ("f_opportunity", "motion_type", "Motion", 262),
    ]
    for table, column, title, y in slicers:
        section["visualContainers"].append(
            build_slicer_visual(table, column, title, x=36, y=y, w=176, h=50)
        )

    _panel(section, x=20, y=348, w=208, h=340, fill="#ffffff", line=BORDER, accent=NAVY)
    section["visualContainers"].append(
        build_textbox_visual("CONTRACT", x=36, y=364, w=172, h=36, font_size_pt=10, color=NAVY)
    )
    for text, y in [
        ("ARR: Land + Expand", 414),
        ("ACV: Renewal", 470),
        ("No blended headline", 526),
        ("Open Value is labeled", 582),
    ]:
        section["visualContainers"].append(
            build_textbox_visual(text, x=36, y=y, w=172, h=40, font_size_pt=9, color=MUTED)
        )

    # Top strip: one executive answer first, then the supporting RAG signals.
    section["visualContainers"].append(
        build_textbox_visual(
            "1. EXECUTIVE READ - LAND+EXPAND EXCEPTIONS",
            x=248,
            y=88,
            w=980,
            h=34,
            font_size_pt=10,
            color=MUTED,
        )
    )
    _panel(section, x=248, y=126, w=980, h=116, fill="#ffffff", line=BORDER, accent=RED)
    _metric_card(
        section,
        table="f_opportunity",
        measure="Exception ARR",
        title="Exception ARR",
        x=274,
        y=150,
        w=184,
        h=76,
        tint=RED_TINT,
        accent=RED,
        value_font_size=28,
    )
    _metric_card(
        section,
        table="f_opportunity",
        measure="Exception Opps Count",
        title="Exception deals",
        x=474,
        y=150,
        w=132,
        h=76,
        tint=RED_TINT,
        accent=RED,
        value_font_size=28,
    )
    _metric_card(
        section,
        table="f_opportunity",
        measure="At Risk Opps ARR",
        title="At-risk ARR",
        x=624,
        y=150,
        w=132,
        h=76,
        tint=RED_TINT,
        accent=RED,
        value_font_size=21,
    )
    _metric_card(
        section,
        table="f_opportunity",
        measure="Watch Opps ARR",
        title="Watch ARR",
        x=774,
        y=150,
        w=132,
        h=76,
        tint=AMBER_TINT,
        accent=AMBER,
        value_font_size=21,
    )
    _metric_card(
        section,
        table="f_opportunity",
        measure="Healthy Moves ARR",
        title="Forward ARR",
        x=924,
        y=150,
        w=136,
        h=76,
        tint=GREEN_TINT,
        accent=GREEN,
        value_font_size=21,
    )
    _metric_card(
        section,
        table="f_opportunity",
        measure="Healthy Moves Count",
        title="Forward moves",
        x=1078,
        y=150,
        w=122,
        h=76,
        tint=GREEN_TINT,
        accent=GREEN,
        value_font_size=24,
    )

    # Middle band: chart-led diagnosis. Cards tell severity; charts tell where.
    section["visualContainers"].append(
        build_textbox_visual(
            "2. COMMERCIAL ENGINE - WHERE THE VALUE SITS",
            x=248,
            y=264,
            w=980,
            h=34,
            font_size_pt=10,
            color=MUTED,
        )
    )
    _panel(section, x=248, y=302, w=480, h=194, fill="#ffffff", line=BORDER, accent=RED)
    _panel(section, x=748, y=302, w=480, h=194, fill="#ffffff", line=BORDER, accent=BLUE)
    section["visualContainers"].append(
        build_textbox_visual(
            "EXCEPTION ARR BY REGION",
            x=264,
            y=312,
            w=440,
            h=34,
            font_size_pt=10,
            color=MUTED,
        )
    )
    section["visualContainers"].append(
        build_clustered_bar_chart_visual(
            category_table="d_region",
            category_column="region",
            category_title="Region",
            measure_table="f_opportunity",
            measure_name="Exception ARR",
            measure_title="Exception ARR",
            x=264,
            y=348,
            w=448,
            h=132,
            fill=RED,
        )
    )
    section["visualContainers"].append(
        build_textbox_visual(
            "OPEN VALUE BY STAGE",
            x=764,
            y=312,
            w=440,
            h=34,
            font_size_pt=10,
            color=MUTED,
        )
    )
    section["visualContainers"].append(
        build_clustered_bar_chart_visual(
            category_table="f_opportunity",
            category_column="stage_name",
            category_title="Stage",
            measure_table="f_opportunity",
            measure_name="Total Open Pipeline Value",
            measure_title="Open Value",
            x=764,
            y=348,
            w=448,
            h=132,
            fill=BLUE,
        )
    )

    # Bottom band: operating pulse plus named deal queue.
    _panel(section, x=248, y=506, w=432, h=202, fill="#ffffff", line=BORDER, accent=NAVY)
    _panel(section, x=700, y=506, w=528, h=202, fill="#ffffff", line=BORDER, accent=NAVY)
    section["visualContainers"].append(
        build_textbox_visual(
            "KPI OPERATING PULSE",
            x=264,
            y=516,
            w=392,
            h=34,
            font_size_pt=10,
            color=MUTED,
        )
    )
    for table, measure, title, x, y, accent, width in [
        ("f_opportunity", "Total Closed Won ARR", "Won ARR", 264, 550, BLUE, 186),
        ("f_opportunity", "Win Rate ARR", "Win rate", 464, 550, BLUE, 186),
        ("f_stage_transition", "Stage Forward Pct (LE)", "Stage fwd", 264, 632, AMBER, 186),
        ("f_opportunity", "Renewal Retention Pct (Period)", "Renewal retention", 464, 632, GREEN, 186),
    ]:
        _metric_card(
            section,
            table=table,
            measure=measure,
            title=title,
            x=x,
            y=y,
            w=width,
            h=76,
            tint="#ffffff",
            accent=accent,
            value_font_size=18,
        )
    section["visualContainers"].append(
        build_textbox_visual(
            "DEAL INSPECTION QUEUE",
            x=716,
            y=516,
            w=488,
            h=34,
            font_size_pt=10,
            color=MUTED,
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
            x=716,
            y=556,
            w=496,
            h=132,
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
