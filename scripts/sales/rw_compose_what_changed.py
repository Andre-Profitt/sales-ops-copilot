"""Compose the 'What Changed' tab of rpt_vp_ops_scorecard.

Idempotent: re-running clears the tab and rebuilds from scratch.

Plan: docs/superpowers/plans/2026-05-08-rw-tab-what-changed.md
Spec: docs/superpowers/specs/2026-05-08-rw-dashboard-redesign-design.md § Tab 1

Run:
    python3 -m scripts.sales.rw_compose_what_changed
"""

from __future__ import annotations

from scripts.sales._pbir_helpers import (
    build_rag_card_visual,
    build_shape_visual,
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
        y=12    Risk band header
        y=42    Risk band hero - 3 columns x (count card 320x78 + ARR card 320x56)
        y=198   Change buckets header
        y=228   Change buckets - compact cards
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
        build_textbox_visual("Exception Movement", x=20, y=12, w=1200, h=24)
    )
    # Hero cards. ARR shown via a separate small card under each count
    # — a single card hosts one Measure per the current builder.
    # Combine into one card via objects block in a follow-up after we
    # capture the right shape via rw_capture_visual.
    risk_band = [
        ("At Risk Opps Count", "At Risk Opps ARR", "At Risk", 20, "#ffeeee", "#cc3333"),
        ("Watch Opps Count", "Watch Opps ARR", "Watch", 360, "#fff8e6", "#dd8800"),
        ("Healthy Moves Count", "Healthy Moves ARR", "Healthy", 700, "#eef9ee", "#339933"),
    ]
    for count_msr, arr_msr, title, x, tint, accent in risk_band:
        section["visualContainers"].append(
            build_shape_visual(
                x=x - 4,
                y=38,
                w=328,
                h=146,
                fill=tint,
                line=accent,
                z=100,
                radius=4,
            )
        )
        section["visualContainers"].append(
            build_rag_card_visual(
                "f_opportunity",
                count_msr,
                f"{title} - count",
                x=x,
                y=42,
                w=320,
                h=78,
                tint=tint,
                accent=accent,
                value_font_size=28,
            )
        )
        section["visualContainers"].append(
            build_rag_card_visual(
                "f_opportunity",
                arr_msr,
                f"{title} - ARR",
                x=x,
                y=124,
                w=320,
                h=56,
                tint=tint,
                accent=accent,
                value_font_size=24,
                display_units=1,
            )
        )

    # ── Phase 2: Change buckets (3 of 4 spec'd; Slips deferred) ──
    section["visualContainers"].append(
        build_textbox_visual("7-Day Operating Movement", x=20, y=198, w=1200, h=24)
    )
    # Spec calls for Stage Moves · Slips · New Opps · Closed.
    # Slips defers until f_ofh_close_date ETL ships
    # (see docs/sales/RW_VPOPS_DASHBOARD_BUILD.md Foundation Phase).
    change_buckets = [
        # (table, measure, title, x, y, w, h, tint, accent, value_color, units)
        (
            "f_stage_transition",
            "Stage Moves Count 7d",
            "Stage Moves (7d)",
            20,
            228,
            240,
            72,
            "#F4F7FB",
            "#2B5C8A",
            "#1A1D31",
            None,
        ),
        (
            "f_stage_transition",
            "Stage Moves ARR 7d",
            "Stage Moves (7d) - ARR",
            20,
            305,
            240,
            54,
            "#F4F7FB",
            "#2B5C8A",
            "#1A1D31",
            1000000,
        ),
        (
            "f_opportunity",
            "New Opps Count 7d",
            "New Opps (7d)",
            280,
            228,
            240,
            90,
            "#F4F7FB",
            "#2B5C8A",
            "#1A1D31",
            None,
        ),
        (
            "f_opportunity",
            "Closed Won Count 7d",
            "Won (7d)",
            540,
            228,
            240,
            90,
            "#EEF9EE",
            "#3B8A3E",
            "#1F6F3B",
            None,
        ),
        (
            "f_opportunity",
            "Closed Lost Count 7d",
            "Lost (7d)",
            800,
            228,
            240,
            90,
            "#FFEEEE",
            "#C33A32",
            "#B3261E",
            None,
        ),
    ]
    for tbl, msr, title, x, y, w, h, tint, accent, value_color, units in change_buckets:
        section["visualContainers"].append(
            build_rag_card_visual(
                tbl,
                msr,
                title,
                x=x,
                y=y,
                w=w,
                h=h,
                tint=tint,
                accent=accent,
                value_color=value_color,
                label_color="#5C6670",
                value_font_size=22 if h >= 72 else 18,
                label_font_size=8,
                display_units=units,
            )
        )

    # ── Phase 3: Detail table ──────────────────────────────────
    section["visualContainers"].append(
        build_textbox_visual(
            "Top Open ARR Movement Queue", x=20, y=386, w=1200, h=24
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
                    "title": "Open ARR",
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
            objects=build_table_style_objects(
                header_fill="#EEF2F6",
                header_text="#1A1D31",
                row_text="#202124",
                grid="#E3E7EE",
                font_size=8,
            ),
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
