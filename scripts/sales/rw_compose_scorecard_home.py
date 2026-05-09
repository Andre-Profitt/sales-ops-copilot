"""Compose the front 'VP Ops Scorecard' page of rpt_vp_ops_scorecard.

PR1 layout (see spec): exception spine + movement-spine placeholder +
4-card KPI strip. Replaces the prior 45-visualContainer card wall.

Run:
    python3 -m scripts.sales.rw_compose_scorecard_home
"""

from __future__ import annotations

from scripts.sales._pbir_helpers import (
    build_card_visual_with_objects,
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
from scripts.sales.rw_zebra_kg_native_emit import emit_native_visuals
from scripts.sales.rw_zebra_kg_recipe import Recipe, VisualRecipe

PAGE = "VP Ops Scorecard"

KPI_STRIP_MEASURES = [
    "Total Closed Won ARR",
    "Win Rate ARR",
    "Stage Forward Pct (LE)",
    "Renewal Retention Pct (Period)",
]


def _build_exception_spine() -> dict:
    """KG-pipeline-driven native exception spine.

    Hand-builds a VisualRecipe referencing RW measure names (the deployed
    model uses bespoke names that don't match Zebra's IBCS slot names —
    PR2's smoke confirmed 0/13 matches when crawling sales-dashboard Landing).
    The recipe goes through emit_native_visuals which translates to a native
    tableEx via build_table_visual.

    Architectural value: the spine now goes through the same Recipe → emit
    pipeline that PR3.1 will use for the movement waterfall and the KPI
    strip's Zebra Cards upgrade. When the Zebra tenant block is lifted,
    swap visual_type from "ZebraBITables..." back to the Zebra GUID and
    emit_native_visuals will route to a Zebra Tables visual instead. One
    line, no other changes.
    """
    recipe_visual = VisualRecipe(
        visual_type="ZebraBITables98F88148E5424E949E69864664EE1860",
        position={"x": 0, "y": 80, "w": 1280, "h": 264},
        role_bindings={
            "Category": ["d_region.region"],
            "Values": [
                "f_opportunity.Exception ARR",
                "f_opportunity.Exception Opps Count",
                "f_opportunity.At Risk Opps ARR",
                "f_opportunity.Watch Opps ARR",
            ],
        },
        scenarios_used=["AC"],
        tables_referenced=["d_region", "f_opportunity"],
        measure_refs=[
            "Exception ARR",
            "Exception Opps Count",
            "At Risk Opps ARR",
            "Watch Opps ARR",
        ],
    )
    recipe = Recipe(
        source_template="rw-internal:exception-spine",
        source_page="VP Ops Scorecard",
        visuals=[recipe_visual],
    )
    rw_map = fetch_measures_by_table()
    visuals = emit_native_visuals(recipe, rw_map)
    if not visuals:
        raise RuntimeError(
            "KG pipeline produced no visual for the exception spine — "
            "verify all 4 measures (Exception ARR, Exception Opps Count, "
            "At Risk Opps ARR, Watch Opps ARR) are in the deployed RW model."
        )
    return visuals[0]


def _build_movement_spine_placeholder() -> dict:
    """Textbox placeholder for the movement waterfall (PR2).

    Reserves the vertical real-estate so PR2's bridge visual lands cleanly,
    and signals to the executive viewer that 'what changed' is coming —
    rather than the rebuild looking permanently incomplete.
    """
    return build_textbox_visual(
        text=(
            "Movement spine — see PR2 (Pipeline ARR last 7d waterfall, "
            "pending new ARR-7d measures and Commercial Approval Gate "
            "Exception ARR measure)"
        ),
        x=0,
        y=360,
        w=1280,
        h=224,
        font_size_pt=11,
        color="#666666",
    )


def _build_kpi_strip() -> list[dict]:
    """4 native cards, evenly spaced across 1280px at y=600.

    Each card binds one measure from KPI_STRIP_MEASURES. Sparklines and
    variance arrows are PR2 work (Zebra Cards binding pattern unproven).
    Tables are sourced per-measure from the deployed RW semantic model.
    """
    kpi_tables = {
        "Total Closed Won ARR": "f_opportunity",
        "Win Rate ARR": "f_opportunity",
        "Stage Forward Pct (LE)": "f_stage_transition",
        "Renewal Retention Pct (Period)": "f_opportunity",
    }
    cards: list[dict] = []
    for i, measure_name in enumerate(KPI_STRIP_MEASURES):
        cards.append(
            build_card_visual_with_objects(
                measure_table=kpi_tables[measure_name],
                measure_name=measure_name,
                display_title=measure_name,
                x=i * 320,
                y=600,
                w=320,
                h=120,
            )
        )
    return cards


def _find_page(rj: dict) -> dict:
    for s in rj["sections"]:
        if s.get("displayName") == PAGE:
            return s
    raise SystemExit(
        f"page {PAGE!r} not found; have: {[s.get('displayName') for s in rj['sections']]}"
    )


def _compose(section: dict) -> None:
    """Compose the VP Ops Scorecard front page (PR1.5).

    Emits exactly 7 visualContainers:
      1. Page title (textbox at y=0)
      2. Exception spine (native tableEx at y=80; Zebra fallback per PR1.5)
      3. Movement-spine placeholder (textbox at y=360)
      4-7. KPI strip (4 native cards at y=600)

    Total layout closes to 720px with intentional 16px breathing-room gaps.

    Drops the inherited page-level filters. The prior 45-card layout had a
    `FilterYear` page filter targeting `d_calendar[year] = 2026`. That filter
    intersects badly with `Total Closed Won ARR` which has its own date logic
    in the deployed DAX, surfacing as $0. Each measure does its own scoping;
    the page is filter-agnostic at the page level.
    """
    section["filters"] = "[]"
    section["visualContainers"] = [
        build_textbox_visual(
            text="VP Ops Scorecard",
            x=0,
            y=0,
            w=1280,
            h=64,
            font_size_pt=20,
            color="#1F2937",
            bold=True,
        ),
        _build_exception_spine(),
        _build_movement_spine_placeholder(),
        *_build_kpi_strip(),
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
