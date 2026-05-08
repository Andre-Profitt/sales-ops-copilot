"""Compose the 'Forecast' tab of rpt_vp_ops_scorecard.

Idempotent: re-running clears the tab and rebuilds from scratch.

Spec: docs/superpowers/specs/2026-05-08-rw-dashboard-redesign-design.md § Tab 2

Path-(a) deferrals (vs spec):
- Quota attainment + Pipeline coverage hero cards: needs Quota__c per region.
  Defer until ETL adds it; ship Days Remaining In FQ + Open + Won as a 3-card
  hero today.
- Stage × motion matrix "Weighted" column: no win-prob-by-stage in model.
- Region split table: needs quota.
- Forecast accuracy + Avg days in commit + WoW delta: ForecastingItem snapshots
  not in ETL.

Run:
    python3 -m scripts.sales.rw_compose_forecast
"""

from __future__ import annotations

from scripts.sales._pbir_helpers import (
    build_card_visual,
    build_matrix_visual,
    build_table_visual,
)
from scripts.sales.rw_add_visual import (
    REPORT_ID,
    WORKSPACE_ID,
    _token,
    get_current_report_json,
    push_report,
)
from scripts.sales.rw_validate import fetch_measures_by_table, validate_visual_dict

PAGE = "Forecast"


def _find_page(rj: dict) -> dict:
    for s in rj["sections"]:
        if s.get("displayName") == PAGE:
            return s
    raise SystemExit(
        f"page {PAGE!r} not found; have: {[s.get('displayName') for s in rj['sections']]}"
        " — run `python3 -m scripts.sales.rw_add_visual --ensure-pages` first"
    )


def _compose(section: dict) -> None:
    """Append all visuals for the Forecast tab.

    Layout grid:
        y=20    Hero — 3 cards × 380×120 (Days Remaining · Open · Closed Won)
        y=160   Stage × motion matrix — 1200×260
        y=440   Forecast discipline — 4 cards × 280×110
        y=570   Commit-risk table — 1200×260
    """
    # ── Hero (3 cards) ─────────────────────────────────────────
    # Spec calls for Quota attainment + Pipeline coverage 3x +
    # Days remaining. Quota dependency unmet — substitute with
    # Open Pipeline Value (cross-motion) + Closed Won ARR.
    hero = [
        ("f_opportunity", "Days Remaining In FQ", "Days Remaining (FQ)", 20),
        ("f_opportunity", "Total Open Pipeline Value", "Open Pipeline (cross-motion)", 420),
        ("f_opportunity", "Total Closed Won ARR", "Closed Won ARR (FY26)", 820),
    ]
    for tbl, msr, title, x in hero:
        section["visualContainers"].append(
            build_card_visual(tbl, msr, title, x=x, y=20, w=380, h=120)
        )

    # ── Stage × motion matrix ──────────────────────────────────
    # Rows = stage_name, columns = motion_type, value = Total Open Pipeline Value
    # (which renders ARR for Land/Expand and ACV for Renewal — see measure
    # description). Filtering to S3+ stages happens via the visual's filter
    # pane manually for now.
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
            x=20,
            y=160,
            w=1200,
            h=260,
        )
    )

    # ── Forecast discipline (4 cards) ──────────────────────────
    discipline = [
        ("f_forecast_transition", "Forecast Slip Pct", "Slip Rate", 20),
        ("f_forecast_transition", "Forecast Slips", "Total Slips (qtr)", 320),
        ("f_forecast_transition", "Forecast Upgrades", "Total Upgrades (qtr)", 620),
        (
            "f_forecast_transition",
            "Avg Days In Forecast Category",
            "Avg Days In Category",
            920,
        ),
    ]
    for tbl, msr, title, x in discipline:
        section["visualContainers"].append(
            build_card_visual(tbl, msr, title, x=x, y=440, w=280, h=110)
        )

    # ── Commit-risk table ──────────────────────────────────────
    # Top late-stage open deals. Owner column deferred (no d_user join in
    # build_table_visual yet); use account_name instead. "Days late"
    # column also deferred (would need a row-context measure).
    section["visualContainers"].append(
        build_table_visual(
            name="forecast_commit_risk",
            columns=[
                {
                    "table": "f_opportunity",
                    "field": "opp_name",
                    "kind": "column",
                    "title": "Opp",
                },
                {
                    "table": "f_opportunity",
                    "field": "account_name",
                    "kind": "column",
                    "title": "Account",
                },
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
                    "title": "Value",
                },
                {
                    "table": "f_opportunity",
                    "field": "close_date",
                    "kind": "column",
                    "title": "Close Date",
                },
                {
                    "table": "f_opportunity",
                    "field": "last_stage_change_date",
                    "kind": "column",
                    "title": "Last Stage Move",
                },
            ],
            x=20,
            y=570,
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
