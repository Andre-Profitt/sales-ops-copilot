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
    build_card_visual_with_objects,
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
    zebra_detail_table_objects,
    zebra_native_card_objects,
    zebra_stage_hygiene_table_objects,
)

PAGE = "Forecast"


def _kpi_card(
    table: str,
    measure: str,
    title: str,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    tint: str = "#F4F7FB",
    accent: str = "#2B5C8A",
    value_color: str = "#1A1D31",
    display_units: int | None = None,
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
            pattern="forecast-kpi-card",
            visual_intent="forecast operating KPI",
            tint=tint,
            accent=accent,
            value_color=value_color,
            label_color=accent,
            value_font_size=24 if h >= 90 else 20,
            label_font_size=9,
            display_units=display_units,
        ),
    )


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
        y=12    Hero header
        y=92    Hero - 4 cards x 285x78
        y=184   Stage x motion header
        y=212   Stage x motion split-basis table - 1200x172
        y=398   Forecast discipline header
        y=426   Forecast discipline - 4 cards x 280x72
        y=512   Commit-risk header
        y=540   Commit-risk table - 1200x150
    """
    # ── Hero (3 cards) ─────────────────────────────────────────
    section["visualContainers"].append(
        build_textbox_visual(
            "Quarter Outlook", x=20, y=12, w=1200, h=28, font_size_pt=18, color="#1A1D31"
        )
    )
    # Spec calls for Quota attainment + Pipeline coverage 3x. Quota dependency
    # is still unmet, so keep the basis split explicit: open ARR and open
    # renewal ACV are separate hero cards, never one blended open-value card.
    hero = [
        ("f_opportunity", "Days Remaining In FQ", "Days Remaining (FQ)", 20, None),
        (
            "f_opportunity",
            "Total Open Pipeline ARR",
            "Open ARR (Land + Expand)",
            325,
            1000000,
        ),
        (
            "f_opportunity",
            "Total Open Renewal ACV",
            "Open renewal ACV",
            630,
            1000000,
        ),
        ("f_opportunity", "Total Closed Won ARR", "Closed won ARR (Land + Expand)", 935, 1000000),
    ]
    for tbl, msr, title, x, display_units in hero:
        section["visualContainers"].append(
            _kpi_card(tbl, msr, title, x=x, y=92, w=285, h=78, display_units=display_units)
        )

    # ── Stage × motion matrix ──────────────────────────────────
    section["visualContainers"].append(
        build_textbox_visual("Stage x Motion Open Pipeline by Basis", x=20, y=184, w=1200, h=24, font_size_pt=12, color="#1A1D31")
    )
    # The table shows ARR and Renewal ACV as separate columns. Do not use
    # Total Open Pipeline Value here; matrix totals would blend ARR and ACV.
    section["visualContainers"].append(
        build_table_visual(
            name="forecast_stage_motion_split_basis",
            columns=[
                {
                    "table": "f_opportunity",
                    "field": "stage_name",
                    "kind": "column",
                    "title": "Stage",
                },
                {
                    "table": "f_opportunity",
                    "field": "motion_type",
                    "kind": "column",
                    "title": "Motion",
                },
                {
                    "table": "f_opportunity",
                    "field": "Total Open Pipeline ARR",
                    "kind": "measure",
                    "title": "Open ARR (Land + Expand)",
                },
                {
                    "table": "f_opportunity",
                    "field": "Total Open Renewal ACV",
                    "kind": "measure",
                    "title": "Open renewal ACV",
                },
            ],
            x=20,
            y=212,
            w=1200,
            h=172,
            objects=zebra_stage_hygiene_table_objects(
                max_field="f_opportunity.Total Open Pipeline ARR",
                databar_column="f_opportunity.Total Open Pipeline ARR",
                accent="#2B5C8A",
            ),
        )
    )

    # ── Forecast discipline (4 cards) ──────────────────────────
    section["visualContainers"].append(
        build_textbox_visual("Forecast Discipline", x=20, y=398, w=1200, h=24, font_size_pt=12, color="#1A1D31")
    )
    discipline = [
        (
            "f_forecast_transition",
            "Forecast Slip Pct",
            "Slip % (count proxy)",
            20,
            "#FFEEEE",
            "#C33A32",
            "#B3261E",
        ),
        (
            "f_forecast_transition",
            "Forecast Slips",
            "Slip count (proxy)",
            320,
            "#FFF8E6",
            "#D98A00",
            "#1A1D31",
        ),
        (
            "f_forecast_transition",
            "Forecast Upgrades",
            "Upgrade count (qtr)",
            620,
            "#EEF9EE",
            "#3B8A3E",
            "#1F6F3B",
        ),
        (
            "f_forecast_transition",
            "Avg Days In Forecast Category",
            "Avg days/category",
            920,
            "#F4F7FB",
            "#2B5C8A",
            "#1A1D31",
        ),
    ]
    for tbl, msr, title, x, tint, accent, value_color in discipline:
        section["visualContainers"].append(
            _kpi_card(
                tbl,
                msr,
                title,
                x=x,
                y=426,
                w=280,
                h=72,
                tint=tint,
                accent=accent,
                value_color=value_color,
            )
        )

    # ── Commit-risk table ──────────────────────────────────────
    section["visualContainers"].append(
        build_textbox_visual("Late-Stage Commit Risk", x=20, y=512, w=1200, h=24, font_size_pt=12, color="#1A1D31")
    )
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
                    "field": "motion_type",
                    "kind": "column",
                    "title": "Motion",
                },
                {
                    "table": "f_opportunity",
                    "field": "Total Open Pipeline ARR",
                    "kind": "measure",
                    "title": "Open ARR (Land + Expand)",
                },
                {
                    "table": "f_opportunity",
                    "field": "Total Open Renewal ACV",
                    "kind": "measure",
                    "title": "Open renewal ACV",
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
            y=540,
            w=1200,
            h=150,
            objects=zebra_detail_table_objects(),
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
