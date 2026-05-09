"""Compose the front 'VP Ops Scorecard' page of rpt_vp_ops_scorecard.

PR1 layout (see spec): exception spine + movement-spine placeholder +
4-card KPI strip. Replaces the prior 45-visualContainer card wall.

Run:
    python3 -m scripts.sales.rw_compose_scorecard_home
"""

from __future__ import annotations

from scripts.sales._pbir_helpers import (
    ZEBRA_BI_TABLES_VISUAL_TYPE,
    build_card_visual_with_objects,
    build_textbox_visual,
    build_zebra_bi_table_visual,
)
from scripts.sales.rw_add_visual import (
    REPORT_ID,
    WORKSPACE_ID,
    _token,
    get_current_report_json,
    push_report,
)
from scripts.sales.rw_validate import fetch_measures_by_table, validate_visual_dict

PAGE = "VP Ops Scorecard"

KPI_STRIP_MEASURES = [
    "Total Closed Won ARR",
    "Win Rate ARR",
    "Stage Forward Pct (LE)",
    "Renewal Retention Pct (Period)",
]


def _build_exception_spine() -> dict:
    """Zebra BI Tables: regional exception view.

    Lifts the binding pattern verbatim from
    rw_apply_zebra_lab_proof.apply_zebra_exceptions_proof, with positions
    re-anchored to the live VP Ops Scorecard layout zone (y=80, h=264).

    Value order is positional — Zebra Tables uses it for IBCS column grouping.
    Do not reorder without re-rendering against the live model.
    """
    return build_zebra_bi_table_visual(
        visual_type=ZEBRA_BI_TABLES_VISUAL_TYPE,
        categories=[
            {"table": "d_region", "field": "region", "title": "Region"},
        ],
        values=[
            {"table": "f_opportunity", "field": "Exception ARR", "title": "Exception ARR"},
            {"table": "f_opportunity", "field": "Exception Opps Count", "title": "Exception opps"},
            {"table": "f_opportunity", "field": "At Risk Opps ARR", "title": "At-risk ARR"},
            {"table": "f_opportunity", "field": "Watch Opps ARR", "title": "Watch ARR"},
        ],
        x=0,
        y=80,
        w=1280,
        h=264,
    )


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
    """Compose the VP Ops Scorecard front page (PR1).

    Emits exactly 7 visualContainers:
      1. Page title (textbox at y=0)
      2. Exception spine (Zebra BI Tables at y=80)
      3. Movement-spine placeholder (textbox at y=360)
      4-7. KPI strip (4 native cards at y=600)

    Total layout closes to 720px with intentional 16px breathing-room gaps.
    """
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
