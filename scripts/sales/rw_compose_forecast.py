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
    build_matrix_visual,
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
        y=42    Hero - 3 cards x 380x96 (Days Remaining, Open, Closed Won)
        y=154   Stage x motion header
        y=182   Stage x motion matrix - 1200x210
        y=408   Forecast discipline header
        y=436   Forecast discipline - 4 cards x 280x80
        y=532   Commit-risk header
        y=560   Commit-risk table - 1200x145
    """
    # ── Hero (3 cards) ─────────────────────────────────────────
    section["visualContainers"].append(
        build_textbox_visual(
            "Quarter Outlook", x=20, y=12, w=1200, h=28, font_size_pt=18, color="#1A1D31"
        )
    )
    # Spec calls for Quota attainment + Pipeline coverage 3x +
    # Days remaining. Quota dependency unmet — substitute with
    # Open Pipeline Value (cross-motion) + Closed Won ARR.
    hero = [
        ("f_opportunity", "Days Remaining In FQ", "Days Remaining (FQ)", 20, None),
        (
            "f_opportunity",
            "Total Open Pipeline Value",
            "Open Value (ARR+ACV)",
            420,
            1000000,
        ),
        ("f_opportunity", "Total Closed Won ARR", "Closed won ARR (Land + Expand)", 820, 1000000),
    ]
    for tbl, msr, title, x, display_units in hero:
        section["visualContainers"].append(
            _kpi_card(tbl, msr, title, x=x, y=42, w=380, h=96, display_units=display_units)
        )

    # ── Stage × motion matrix ──────────────────────────────────
    section["visualContainers"].append(
        build_textbox_visual("Stage x Motion Open Value (ARR+ACV)", x=20, y=154, w=1200, h=24, font_size_pt=12, color="#1A1D31")
    )
    # Rows = stage_name, columns = motion_type, value = Total Open Pipeline Value
    # (which renders ARR for Land + Expand and ACV for Renewal — see measure
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
                    "title": "Open value (ARR+ACV)",
                }
            ],
            x=20,
            y=182,
            w=1200,
            h=210,
            objects=zebra_stage_hygiene_table_objects(
                max_field="f_opportunity.Total Open Pipeline Value",
                databar_column="f_opportunity.Total Open Pipeline Value",
                accent="#2B5C8A",
            ),
        )
    )

    # ── Forecast discipline (4 cards) ──────────────────────────
    section["visualContainers"].append(
        build_textbox_visual("Forecast Discipline", x=20, y=408, w=1200, h=24, font_size_pt=12, color="#1A1D31")
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
                y=436,
                w=280,
                h=80,
                tint=tint,
                accent=accent,
                value_color=value_color,
            )
        )

    # ── Commit-risk table ──────────────────────────────────────
    section["visualContainers"].append(
        build_textbox_visual("Late-Stage Commit Risk", x=20, y=532, w=1200, h=24, font_size_pt=12, color="#1A1D31")
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
                    "field": "Total Open Pipeline Value",
                    "kind": "measure",
                    "title": "Value (ARR+ACV)",
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
            y=560,
            w=1200,
            h=145,
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
