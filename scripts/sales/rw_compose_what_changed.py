"""Compose the 'What Changed' tab of rpt_vp_ops_scorecard.

Idempotent: re-running clears the tab and rebuilds from scratch.

Plan: docs/superpowers/plans/2026-05-08-rw-tab-what-changed.md
Spec: docs/superpowers/specs/2026-05-08-rw-dashboard-redesign-design.md § Tab 1

Run:
    python3 -m scripts.sales.rw_compose_what_changed
"""

from __future__ import annotations

from scripts.sales._pbir_helpers import build_card_visual, build_table_visual
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
        y=20    Risk band hero — 3 columns × (count card 320×120 + ARR card 320×80)
        y=255   Change buckets — 5 cards across (Stage Moves count + ARR, New, Won, Lost)
        y=510   Detail table — 1200×260 spanning the page
        Spec calls for a window slicer at (1000, 20). Field-parameter slicer
        shape not yet captured in _pbir_shapes.py — defer until a textbox
        or field-parameter slicer is browser-authored and captured via
        rw_capture_visual. Today's cards use the 7d window baked into the
        measure name.
    """
    # ── Phase 1: Risk band ──────────────────────────────────────
    # Hero cards. ARR shown via a separate small card under each count
    # — a single card hosts one Measure per the current builder.
    # Combine into one card via objects block in a follow-up after we
    # capture the right shape via rw_capture_visual.
    risk_band = [
        ("At Risk Opps Count", "At Risk Opps ARR", "At Risk", 20),
        ("Watch Opps Count", "Watch Opps ARR", "Watch", 360),
        ("Healthy Moves Count", "Healthy Moves ARR", "Healthy", 700),
    ]
    for count_msr, arr_msr, title, x in risk_band:
        section["visualContainers"].append(
            build_card_visual(
                "f_opportunity", count_msr, f"{title} — count", x=x, y=20, w=320, h=120
            )
        )
        section["visualContainers"].append(
            build_card_visual("f_opportunity", arr_msr, f"{title} — ARR", x=x, y=145, w=320, h=80)
        )

    # ── Phase 2: Change buckets (3 of 4 spec'd; Slips deferred) ──
    # Spec calls for Stage Moves · Slips · New Opps · Closed.
    # Slips defers until f_ofh_close_date ETL ships
    # (see docs/sales/RW_VPOPS_DASHBOARD_BUILD.md Foundation Phase).
    change_buckets = [
        # (table, measure, title, x, y, w, h)
        ("f_stage_transition", "Stage Moves Count 7d", "Stage Moves (7d)", 20, 255, 240, 120),
        ("f_stage_transition", "Stage Moves ARR 7d", "Stage Moves (7d) — ARR", 20, 380, 240, 80),
        ("f_opportunity", "New Opps Count 7d", "New Opps (7d)", 280, 255, 240, 120),
        ("f_opportunity", "Closed Won Count 7d", "Won (7d)", 540, 255, 240, 120),
        ("f_opportunity", "Closed Lost Count 7d", "Lost (7d)", 800, 255, 240, 120),
    ]
    for tbl, msr, title, x, y, w, h in change_buckets:
        section["visualContainers"].append(build_card_visual(tbl, msr, title, x=x, y=y, w=w, h=h))

    # ── Phase 3: Detail table ──────────────────────────────────
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
            y=510,
            w=1200,
            h=260,
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
