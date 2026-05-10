"""Compose the 'What Changed' tab of rpt_vp_ops_scorecard.

Idempotent: re-running clears the tab and rebuilds from scratch.

Plan: docs/superpowers/plans/2026-05-08-rw-tab-what-changed.md
Spec: docs/superpowers/specs/2026-05-08-rw-dashboard-redesign-design.md § Tab 1

Run:
    python3 -m scripts.sales.rw_compose_what_changed
"""

from __future__ import annotations

from scripts.sales._pbir_helpers import (
    build_table_visual,
    build_textbox_visual,
)
from scripts.sales.rw_zebra_kg_ibcs_synth import (
    zebra_compact_movement_ledger_objects,
    zebra_detail_table_objects,
    zebra_exception_ledger_objects,
)

PAGE = "What Changed"


def _find_page(rj: dict) -> dict:
    for s in rj["sections"]:
        if s.get("displayName") == PAGE:
            return s
    raise SystemExit(
        f"page {PAGE!r} not found; have: {[s.get('displayName') for s in rj['sections']]}"
        " — run `python3 -m scripts.sales.rw_add_visual --ensure-pages` first"
    )


def _compose(section: dict) -> None:
    """Append all visuals for the What Changed tab to section['visualContainers'].

    Layout grid:
        y=12    Exception ledger header
        y=48    Exception ledger - compact table, no KPI card furniture
        y=188   Movement ledger header
        y=218   Movement ledger - compact one-row table of 7d measures
        y=386   Detail header
        y=414   Detail table - 1200x280 spanning the page
        Spec calls for a window slicer at (1000, 20). Field-parameter slicer
        shape not yet captured in _pbir_shapes.py — defer until a textbox
        or field-parameter slicer is browser-authored and captured via
        rw_capture_visual. Today's cards use the 7d window baked into the
        measure name.
    """
    # ── Phase 1: Risk band ──────────────────────────────────────
    section["visualContainers"].append(
        build_textbox_visual(
            "Exception Movement", x=20, y=12, w=1200, h=28, font_size_pt=18, color="#1A1D31"
        )
    )
    section["visualContainers"].append(
        build_table_visual(
            name="what_changed_exception_ledger",
            columns=[
                {
                    "table": "f_opportunity",
                    "field": "At Risk Opps Count",
                    "kind": "measure",
                    "title": "At-risk opp count",
                },
                {
                    "table": "f_opportunity",
                    "field": "At Risk Opps ARR",
                    "kind": "measure",
                    "title": "At-risk ARR (Land + Expand)",
                },
                {
                    "table": "f_opportunity",
                    "field": "Watch Opps Count",
                    "kind": "measure",
                    "title": "Watch opp count",
                },
                {
                    "table": "f_opportunity",
                    "field": "Watch Opps ARR",
                    "kind": "measure",
                    "title": "Watch ARR (Land + Expand)",
                },
                {
                    "table": "f_opportunity",
                    "field": "Healthy Moves Count",
                    "kind": "measure",
                    "title": "Healthy move count",
                },
                {
                    "table": "f_opportunity",
                    "field": "Healthy Moves ARR",
                    "kind": "measure",
                    "title": "Healthy ARR (Land + Expand)",
                },
            ],
            x=20,
            y=48,
            w=1020,
            h=118,
            objects=zebra_exception_ledger_objects(),
        )
    )

    # ── Phase 2: Movement ledger (compact matrix instead of card wall) ──
    section["visualContainers"].append(
        build_textbox_visual("7-Day Operating Movement Ledger (counts + ARR Land + Expand)", x=20, y=188, w=1200, h=24, font_size_pt=12, color="#1A1D31")
    )
    # Spec calls for Stage Moves · Slips · New Opps · Closed. The prior
    # version rendered these as five micro-cards and tripped the visual QA
    # wall_of_cards heuristic. Keep the same RW KPI intent, but consolidate the
    # operational deltas into one consultant-grade one-row ledger. Slips still
    # defers until f_ofh_close_date ETL ships (see RW_VPOPS_DASHBOARD_BUILD).
    section["visualContainers"].append(
        build_table_visual(
            name="what_changed_movement_ledger",
            columns=[
                {
                    "table": "f_stage_transition",
                    "field": "Stage Moves Count 7d",
                    "kind": "measure",
                    "title": "Stage move count",
                },
                {
                    "table": "f_stage_transition",
                    "field": "Stage Moves ARR 7d",
                    "kind": "measure",
                    "title": "Stage ARR (Land + Expand)",
                },
                {
                    "table": "f_opportunity",
                    "field": "New Opps Count 7d",
                    "kind": "measure",
                    "title": "New opp count",
                },
                {
                    "table": "f_opportunity",
                    "field": "Closed Won Count 7d",
                    "kind": "measure",
                    "title": "Won count",
                },
                {
                    "table": "f_opportunity",
                    "field": "Closed Lost Count 7d",
                    "kind": "measure",
                    "title": "Lost count",
                },
            ],
            x=20,
            y=218,
            w=1020,
            h=150,
            objects=zebra_compact_movement_ledger_objects(
                max_field="f_stage_transition.Stage Moves ARR 7d",
                databar_column="Stage Moves ARR 7d",
                accent="#083EA7",
            ),
        )
    )

    # ── Phase 3: Detail table ──────────────────────────────────
    section["visualContainers"].append(
        build_textbox_visual(
            "Top Open ARR (Land + Expand) Movement Queue", x=20, y=386, w=1200, h=24, font_size_pt=12, color="#1A1D31"
        )
    )
    # Open opps by Open Pipeline ARR. Spec's "Change" + "Risk class"
    # columns require row-context measures — deferred. Top-20 filter
    # is applied via the PBI Visual filter pane today; build_table_visual
    # may grow a top_n kwarg later.
    section["visualContainers"].append(
        build_table_visual(
            name="what_changed_detail",
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
                    "field": "Total Open Pipeline ARR",
                    "kind": "measure",
                    "title": "Open ARR (Land + Expand)",
                },
                {
                    "table": "f_opportunity",
                    "field": "last_stage_change_date",
                    "kind": "column",
                    "title": "Last Stage Move",
                },
            ],
            x=20,
            y=414,
            w=1200,
            h=280,
            objects=zebra_detail_table_objects(),
        )
    )


def main() -> None:
    from scripts.sales.rw_add_visual import (
        REPORT_ID,
        WORKSPACE_ID,
        _token,
        get_current_report_json,
        push_report,
    )
    from scripts.sales.rw_validate import fetch_measures_by_table, validate_visual_dict

    print(f"composing {PAGE!r} on rpt_vp_ops_scorecard")
    token = _token()
    print("  fetching report.json...")
    rj = get_current_report_json(token)
    section = _find_page(rj)
    print(f"  current visuals: {len(section.get('visualContainers', []))} (clearing)")
    section["visualContainers"] = []

    _compose(section)
    print(f"  composed: {len(section['visualContainers'])} visuals")

    # Pre-flight: every measure ref must resolve against the deployed model.
    print("  pre-flighting measure refs...")
    by_table = fetch_measures_by_table()
    errors: list[str] = []
    for vc in section["visualContainers"]:
        errors.extend(validate_visual_dict(vc, by_table))
    if errors:
        raise SystemExit("\n".join(["pre-flight validation FAILED:"] + errors))
    print(
        f"  pre-flight: all refs resolve against {sum(len(v) for v in by_table.values())} measures ✓"
    )

    print(f"\npushing; total visuals on {PAGE!r}: {len(section['visualContainers'])}")
    push_report(token, rj)
    print(
        f"\ndone. open: https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/reports/{REPORT_ID}"
    )


if __name__ == "__main__":
    main()
