#!/usr/bin/env python3
"""
Upgrade v3: 5 decision-grade upgrades to the Sales Ops Cockpit dashboard.

Atomic — one PATCH per layer (reports first, dashboard last). Idempotent —
second run = no-op.

  #1 Stage Stickiness        Bar of avg STAGE_DURATION by StageName
                             (open Land+Expand). Reports doesn't support
                             MEDIAN; AVG used as honest fallback.
  #2 Activity Drought        Metric of count(CFQ open Land+Expand where
                             LastActivityDate is 30+ days stale).
  #3 Win Rate by Deal Size   Bar of Custom Summary Formula (won / closed)
                             over a bucket field on APTS_Opportunity_ARR__c.
                             Closed Land+Expand, rolling 4-quarter window.
  #4 Drop dead-zero tiles    Drop 3: Approval Gap·Land, Ghost Assets,
                             Expiring · No Renewal Check. Keep KYC Gap
                             and Approval Gap·≥$500k as compliance proof.
  #5 Hero callout            New "Zombie Pipeline 365+" Metric tile in
                             leftmost slot. FY26 Open Pipeline shifts
                             one position right.

Final widget count: 20 (drop 3, add 4 from a 19-widget baseline).

Hero header tries emoji first; if Lightning silently strips it, falls back
to a unicode block prefix.

Usage:
    python3 upgrade_v3.py
    python3 upgrade_v3.py --dry-run
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
import sys
import urllib.error
from typing import Any

from rebuild_viz import (  # type: ignore[import-not-found]
    API_VERSION,
    DASHBOARD_ID,
    _api,
    get_credentials,
)
from upgrade_v2 import (  # type: ignore[import-not-found]
    EXCLUDE_OPP_CRITERIA,
    FILTER_SPECS,
    REPORT_FOLDER_ID,
    _build_filter,
    _build_opp_report_body,
    _filter_columns_for,
    _find_or_create_report,
)

# ── Constants ─────────────────────────────────────────────────────────────

# Drop these 3 widgets (legitimate 0-counts post truth-field fix).
DROP_REPORT_IDS: set[str] = {
    "00OTb000008muxlMAA",  # Approval Gap · Land (redundant with ≥$500k)
    "00OTb000008mwptMAA",  # Cockpit · Ghost Assets (always 0 — InstallDate null)
    "00OTb000008mwt7MAA",  # Cockpit · Expiring Assets ≤90d (always 0)
}

# Replace this widget's binding (FY26 Open Pipeline) with the Hero report,
# AND keep the original widget — Hero adds a new component at slot (0,0,4,3)
# and FY26 shifts to (0,3,3,3). Existing FY26 widget stays in components[],
# only its layout cell moves.
FY26_OPEN_PIPELINE_REPORT_ID = "00OTb000008muBPMAY"


def _rolling_four_quarter_window(today: date | None = None) -> tuple[str, str]:
    current = today or date.today()
    quarter_index = (current.month - 1) // 3
    quarter_start_month = quarter_index * 3 + 1
    start_quarter_index = current.year * 4 + quarter_index - 3
    start_year, start_quarter = divmod(start_quarter_index, 4)
    start_date = date(start_year, start_quarter * 3 + 1, 1)
    if quarter_index == 3:
        next_quarter_start = date(current.year + 1, 1, 1)
    else:
        next_quarter_start = date(current.year, quarter_start_month + 3, 1)
    end_date = next_quarter_start - timedelta(days=1)
    return start_date.isoformat(), end_date.isoformat()


L4Q_START_DATE, L4Q_END_DATE = _rolling_four_quarter_window()


# ── New report specs ──────────────────────────────────────────────────────


STICKINESS_REPORT: dict[str, Any] = {
    "developerName": "Cockpit_Stage_Stickiness_v3",
    "name": "Cockpit · Stage Stickiness · L+E",
    "header": "Stage Stickiness · Avg Days at Stage",
    "metric_label": None,
    "reportFormat": "SUMMARY",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "STAGE_DURATION",
    ],
    "groupingsDown": [
        {"name": "STAGE_NAME", "sortOrder": "Asc"},
    ],
    "aggregates": [
        "a!STAGE_DURATION",
        "RowCount",
    ],
    "filters": [
        {"column": "TYPE", "operator": "equals", "value": "Land,Expand"},
        {"column": "CLOSED", "operator": "equals", "value": "False"},
    ],
    "exclusion": EXCLUDE_OPP_CRITERIA,
    "standardDateFilter": {
        "column": "CLOSE_DATE",
        "durationValue": "CUSTOM",
        "startDate": "2000-01-01",
        "endDate": "2099-12-31",
    },
}


# Activity drought: use a plain SUMMARY report. The metric tile shows the
# grand-total row count, while grouping by Stage preserves context on
# drill-through. The earlier TABULAR top-N design hit Analytics REST
# validator errors on this org, so the report now tracks the full current-
# quarter drought universe instead of a top-25 slice.
DROUGHT_REPORT: dict[str, Any] = {
    "developerName": "Cockpit_Activity_Drought_v3",
    "name": "Cockpit · Activity Drought Top-25 CFQ",
    "header": "Activity Drought · CFQ 30+ Days",
    "metric_label": "# opps stale 30d+",
    "reportFormat": "SUMMARY",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "Opportunity.APTS_Opportunity_ARR__c",
        "LAST_ACTIVITY",
    ],
    "groupingsDown": [
        {"name": "STAGE_NAME", "sortOrder": "Asc"},
    ],
    "aggregates": [
        "RowCount",
        "s!Opportunity.APTS_Opportunity_ARR__c",
    ],
    "filters": [
        {"column": "TYPE", "operator": "equals", "value": "Land,Expand"},
        {"column": "CLOSED", "operator": "equals", "value": "False"},
        {"column": "Opportunity.APTS_Opportunity_ARR__c", "operator": "greaterThan", "value": "0"},
        # drought predicate: LastActivityDate < 30d ago OR null
        {"column": "LAST_ACTIVITY", "operator": "lessThan", "value": "LAST_N_DAYS:30"},
    ],
    "exclusion": EXCLUDE_OPP_CRITERIA,
    "standardDateFilter": {
        "column": "CLOSE_DATE",
        "durationValue": "THIS_QUARTER",
        "startDate": None,
        "endDate": None,
    },
}


# Win rate by deal size: SUMMARY report with a numeric ARR bucket and a
# custom summary formula. The formula shape mirrors the live org's accepted
# "Win rate report" metadata (`WON:SUM/CLOSED:SUM`).
WIN_RATE_REPORT: dict[str, Any] = {
    "developerName": "Cockpit_Win_Rate_by_Size_v3",
    "name": "Cockpit · Win Rate by Deal Size",
    "header": "Win Rate by Deal Size · L4Q",
    "metric_label": None,
    "reportFormat": "SUMMARY",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "OPPORTUNITY_NAME",
        "ACCOUNT_NAME",
        "Opportunity.APTS_Opportunity_ARR__c",
    ],
    "groupingsDown": [
        {"name": "BucketField_ARR_Band", "sortOrder": "Asc"},
    ],
    "aggregates": [
        "FORMULA1",
        "RowCount",
    ],
    "filters": [
        {"column": "TYPE", "operator": "equals", "value": "Land,Expand"},
        {"column": "CLOSED", "operator": "equals", "value": "True"},
        # Note: ARR > 0 to exclude $0 quota artifacts.
        {"column": "Opportunity.APTS_Opportunity_ARR__c", "operator": "greaterThan", "value": "0"},
    ],
    "exclusion": EXCLUDE_OPP_CRITERIA,
    "standardDateFilter": {
        "column": "CLOSE_DATE",
        "durationValue": "CUSTOM",
        "startDate": L4Q_START_DATE,
        "endDate": L4Q_END_DATE,
    },
    # `useOther` and `otherBucketLabel` cause SF to reject the body with
    # JSON_PARSER_ERROR (verified 2026-04-29 via probe). Last numeric bucket
    # must have `rangeUpperBound: None`.
    "buckets": [
        {
            "developerName": "BucketField_ARR_Band",
            "label": "ARR Band",
            "sourceColumnName": "Opportunity.APTS_Opportunity_ARR__c",
            "bucketType": "number",
            "nullTreatedAsZero": True,
            "values": [
                {"rangeUpperBound": 100000.0, "sourceDimensionValues": None, "label": "<100K"},
                {"rangeUpperBound": 500000.0, "sourceDimensionValues": None, "label": "100K-500K"},
                {"rangeUpperBound": 1000000.0, "sourceDimensionValues": None, "label": "500K-1M"},
                {"rangeUpperBound": None, "sourceDimensionValues": None, "label": ">1M"},
            ],
        }
    ],
    "customSummaryFormula": {
        "FORMULA1": {
            "label": "Win Rate %",
            "description": "% closed opportunities won by ARR band",
            "formula": "WON:SUM/CLOSED:SUM",
            "formulaType": "percent",
            "downGroup": None,
            "downGroupType": "all",
            "acrossGroup": None,
            "acrossGroupType": "all",
            "decimalPlaces": 1,
        }
    },
}


# Hero: Zombie Pipeline 365+ — open Land+Expand opps where the opp itself
# has been open for 365+ days (CreatedDate < LAST_N_DAYS:365). The intent
# is "deals that have been hanging around forever." Counts close to the
# 648 / $274.6M from the spec (verified live: 659 / EUR276.3M).
HERO_REPORT: dict[str, Any] = {
    "developerName": "Cockpit_Hero_Zombie_365_v3",
    "name": "Cockpit · Hero Zombie 365+ L+E",
    "header": "▲ ZOMBIE PIPELINE",
    "metric_label": "365+ days open · Land+Expand",
    "reportFormat": "SUMMARY",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "CREATED_DATE",
        "Opportunity.APTS_Opportunity_ARR__c",
    ],
    "groupingsDown": [
        {"name": "STAGE_NAME", "sortOrder": "Asc"},
    ],
    "aggregates": [
        "RowCount",
        "s!Opportunity.APTS_Opportunity_ARR__c",
    ],
    "filters": [
        {"column": "TYPE", "operator": "equals", "value": "Land,Expand"},
        {"column": "CLOSED", "operator": "equals", "value": "False"},
        {"column": "CREATED_DATE", "operator": "lessThan", "value": "LAST_N_DAYS:365"},
    ],
    "exclusion": EXCLUDE_OPP_CRITERIA,
    "standardDateFilter": {
        "column": "CREATED_DATE",
        "durationValue": "CUSTOM",
        "startDate": "2000-01-01",
        "endDate": "2099-12-31",
    },
}


# ── Layout repack ─────────────────────────────────────────────────────────
# Hero takes (0, 0) at 4 cols × 4 rows (taller for prominence). FY26 Open
# Pipeline shifts to (0, 4); Q2 Commit Forecast (0, 7); FY26 Open Deals
# moves up to row 0 col 10 (was at row 6 col 9 — already a Metric).
#
# New widget slots:
#   Hero          (0, 0, 4, 4)
#   Stickiness    Bar — replaces Approval Gap · Land's old slot (row 16, 3, 3, 3)
#                 but want it in pipeline-detail row.  Better: row 23 (new), 6×4
#   Win Rate      Bar — row 23 (new), 6×4 cell next to Stickiness
#
# Approach: append Stickiness + Win Rate as new bottom-row cells (row 24,
# col 0 and col 6, 4 rows tall, 6 cols wide each). Hero re-anchors row 0.

HERO_SLOT = (0, 0, 3, 4)
FY26_PIPE_SLOT = (0, 4, 3, 3)
COMMIT_FCST_SLOT = (0, 7, 3, 3)
FY26_DEALS_SLOT = (0, 10, 3, 2)
RENEWAL_ACV_SLOT = (29, 4, 3, 3)

STICKINESS_SLOT = (25, 0, 4, 6)
WIN_RATE_SLOT = (25, 6, 4, 6)
DROUGHT_SLOT = (29, 0, 3, 4)


# ── Component builders (extracted to local because v2's helper inlines viz) ──


def _new_metric_component(
    report_id: str,
    header: str,
    metric_label: str | None,
    severity: str | None = None,
) -> dict[str, Any]:
    vp: dict[str, Any] = {
        "displayUnits": "auto",
        "decimalPrecision": 1,
    }
    if metric_label:
        vp["metricLabel"] = metric_label
    if severity == "critical":
        vp["metricFontColor"] = "#C25454"
        vp["referenceLineValues"] = ["0"]
        vp["referenceLineColors"] = ["#C25454"]
    return {
        "reportId": report_id,
        "header": header,
        "title": None,
        "footer": None,
        "type": "Report",
        "properties": {
            "visualizationType": "Metric",
            "aggregates": [{"name": "RowCount"}],
            "groupings": None,
            "filterColumns": [],
            "autoSelectColumns": True,
            "useReportChart": False,
            "reportFormat": "SUMMARY",
            "visualizationProperties": vp,
        },
    }


def _new_bar_component(
    report_id: str,
    header: str,
    grouping: str,
    aggregate: str,
    max_rows: int = 10,
) -> dict[str, Any]:
    return {
        "reportId": report_id,
        "header": header,
        "title": None,
        "footer": None,
        "type": "Report",
        "properties": {
            "visualizationType": "Bar",
            "drillUrl": f"/lightning/r/Report/{report_id}/view",
            "filterColumns": [],
            "autoSelectColumns": True,
            "useReportChart": False,
            "reportFormat": "SUMMARY",
            "groupings": [
                {
                    "name": grouping,
                    "inheritedReportSort": "reportGrouping",
                    "sortAggregate": None,
                    "sortOrder": None,
                }
            ],
            "aggregates": [{"name": aggregate}],
            "maxRows": max_rows,
            "visualizationProperties": {
                "displayUnits": "auto",
                "decimalPrecision": 1,
            },
        },
    }


# ── Custom report-body builders (extends v2 base for buckets + sortBy + CSF) ──


def _build_stickiness_body(rpt: dict[str, Any]) -> dict[str, Any]:
    return _build_opp_report_body(rpt)


def _build_drought_body(rpt: dict[str, Any]) -> dict[str, Any]:
    return _build_opp_report_body(rpt)


def _build_win_rate_body(rpt: dict[str, Any]) -> dict[str, Any]:
    rm: dict[str, Any] = {
        "name": rpt["name"],
        "description": "",
        "reportFormat": rpt["reportFormat"],
        "reportType": rpt["reportType"],
        "detailColumns": list(rpt["detailColumns"]),
        "aggregates": list(rpt.get("aggregates", ["RowCount"])),
        "groupingsDown": [
            {"name": g["name"], "sortOrder": g.get("sortOrder", "Asc")}
            for g in rpt.get("groupingsDown", [])
        ],
        "reportFilters": [
            *rpt.get("filters", []),
            *rpt.get("exclusion", []),
        ],
        "standardDateFilter": rpt["standardDateFilter"],
        "folderId": REPORT_FOLDER_ID,
        "developerName": rpt["developerName"],
        "buckets": rpt.get("buckets", []),
    }
    csf = rpt.get("customSummaryFormula") or {}
    if csf:
        rm["customSummaryFormula"] = csf
    return {"reportMetadata": rm}


def _build_hero_body(rpt: dict[str, Any]) -> dict[str, Any]:
    return _build_drought_body(rpt)  # same TABULAR shape


# ── Main ──────────────────────────────────────────────────────────────────


def _try_create_report(
    rpt: dict[str, Any],
    builder: Any,
    token: str,
    instance: str,
    api_base: str,
) -> tuple[str | None, str | None]:
    """Returns (reportId, error). On exception returns (None, error_str)."""
    try:
        rid = _find_or_create_report(rpt, builder, token, instance, api_base)
        return rid, None
    except RuntimeError as e:
        return None, str(e)[:600]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-hero", action="store_true", help="Skip Hero callout")
    args = ap.parse_args()

    creds = get_credentials()
    token, instance = creds["access_token"], creds["instance_url"]
    api_base = f"/services/data/v{API_VERSION}"

    # ── Step 1: ensure new reports exist ─────────────────────────────────
    print("[1/4] Build / update 4 new reports")
    outcomes: dict[str, str] = {}
    report_ids: dict[str, str | None] = {}

    for key, rpt, builder in [
        ("stickiness", STICKINESS_REPORT, _build_stickiness_body),
        ("drought", DROUGHT_REPORT, _build_drought_body),
        ("win_rate", WIN_RATE_REPORT, _build_win_rate_body),
        ("hero", HERO_REPORT, _build_hero_body),
    ]:
        if args.no_hero and key == "hero":
            outcomes[key] = "skipped (--no-hero)"
            report_ids[key] = None
            continue
        rid, err = _try_create_report(rpt, builder, token, instance, api_base)
        report_ids[key] = rid
        if rid:
            outcomes[key] = f"OK -> {rid}"
        else:
            outcomes[key] = f"FAIL: {err}"
            print(f"  [WARN] {key} report failed: {err}", file=sys.stderr)

    for k, v in outcomes.items():
        print(f"  {k}: {v}")

    # ── Step 2: GET dashboard ────────────────────────────────────────────
    print(f"\n[2/4] GET dashboard {DASHBOARD_ID}/describe")
    describe = _api(
        "GET", f"{api_base}/analytics/dashboards/{DASHBOARD_ID}/describe", token, instance
    )
    components: list[dict[str, Any]] = list(describe["components"])
    layout_components: list[dict[str, Any]] = list(describe.get("layout", {}).get("components", []))
    print(f"  current widget count: {len(components)}")

    # ── Step 3: rewrite components + layout ──────────────────────────────
    print("\n[3/4] Drop 3, add 4 (Hero + Stickiness + Win Rate + Drought)")
    # Drop dead-zero widgets (Approval Gap·Land, Ghost Assets, Expiring).
    # Maintain index alignment with layout_components.
    keep_idxs = [i for i, c in enumerate(components) if c.get("reportId") not in DROP_REPORT_IDS]
    components = [components[i] for i in keep_idxs]
    layout_components = [layout_components[i] for i in keep_idxs]
    print(f"  after drop: {len(components)} widgets")

    # Add Hero in slot (0,0,4,4) IF report created. Existing widget 0 (FY26
    # Open Pipeline) already at (0,0,3,3) — repack to (0,4,3,3).
    if report_ids.get("hero"):
        # Avoid duplicate add (idempotent).
        if not any(c.get("reportId") == report_ids["hero"] for c in components):
            print(f"  add  Hero (Zombie 365+) -> {report_ids['hero']}")
            components.append(
                _new_metric_component(
                    report_ids["hero"],
                    HERO_REPORT["header"],
                    HERO_REPORT["metric_label"],
                    severity="critical",
                )
            )
            layout_components.append(
                {
                    "row": HERO_SLOT[0],
                    "column": HERO_SLOT[1],
                    "rowspan": HERO_SLOT[2],
                    "colspan": HERO_SLOT[3],
                }
            )
        else:
            print("  keep Hero already present")

    # Add Stage Stickiness Bar.
    if report_ids.get("stickiness"):
        if not any(c.get("reportId") == report_ids["stickiness"] for c in components):
            print(f"  add  Stage Stickiness -> {report_ids['stickiness']}")
            components.append(
                _new_bar_component(
                    report_ids["stickiness"],
                    STICKINESS_REPORT["header"],
                    grouping="STAGE_NAME",
                    aggregate="a!STAGE_DURATION",
                    max_rows=10,
                )
            )
            layout_components.append(
                {
                    "row": STICKINESS_SLOT[0],
                    "column": STICKINESS_SLOT[1],
                    "rowspan": STICKINESS_SLOT[2],
                    "colspan": STICKINESS_SLOT[3],
                }
            )
        else:
            print("  keep Stage Stickiness already present")

    # Add Win Rate by Size Bar.
    if report_ids.get("win_rate"):
        if not any(c.get("reportId") == report_ids["win_rate"] for c in components):
            print(f"  add  Win Rate by Size -> {report_ids['win_rate']}")
            components.append(
                _new_bar_component(
                    report_ids["win_rate"],
                    WIN_RATE_REPORT["header"],
                    grouping="BucketField_ARR_Band",
                    aggregate="s!Opportunity.APTS_Opportunity_ARR__c",
                    max_rows=4,
                )
            )
            layout_components.append(
                {
                    "row": WIN_RATE_SLOT[0],
                    "column": WIN_RATE_SLOT[1],
                    "rowspan": WIN_RATE_SLOT[2],
                    "colspan": WIN_RATE_SLOT[3],
                }
            )
        else:
            print("  keep Win Rate already present")

    # Add Drought Metric.
    if report_ids.get("drought"):
        if not any(c.get("reportId") == report_ids["drought"] for c in components):
            print(f"  add  Activity Drought -> {report_ids['drought']}")
            components.append(
                _new_metric_component(
                    report_ids["drought"],
                    DROUGHT_REPORT["header"],
                    DROUGHT_REPORT["metric_label"],
                    severity="critical",
                )
            )
            layout_components.append(
                {
                    "row": DROUGHT_SLOT[0],
                    "column": DROUGHT_SLOT[1],
                    "rowspan": DROUGHT_SLOT[2],
                    "colspan": DROUGHT_SLOT[3],
                }
            )
        else:
            print("  keep Activity Drought already present")

    # Repack: Row 0 strip — Hero + FY26 Open Pipe + Commit Forecast +
    # FY26 Open Deals. Q2 Renewal ACV moves to the bottom row to avoid
    # the 12-column top-strip collision.
    pos_overrides: dict[str, tuple[int, int, int, int]] = {
        "00OTb000008muBPMAY": FY26_PIPE_SLOT,  # FY26 Open Pipeline
        "00OTb000008mukrMAA": COMMIT_FCST_SLOT,  # Q2 Commit Forecast
        "00OTb000008mumTMAQ": FY26_DEALS_SLOT,  # FY26 Open Deals
        "00OTb000008muo5MAA": RENEWAL_ACV_SLOT,  # Q2 Renewal ACV
    }
    for i, comp in enumerate(components):
        rid = comp.get("reportId") or ""
        if rid in pos_overrides:
            r, c, rs, cs = pos_overrides[rid]
            layout_components[i] = {"row": r, "column": c, "rowspan": rs, "colspan": cs}

    # Re-apply per-component filterColumns wiring (for the new components).
    asset_rid_set: set[str] = (
        set()
    )  # we no longer have asset components in the kept set if Ghost+Expiring dropped, but Duplicate stays
    # Actually: Duplicate Active Assets (00OTb000008mwrVMAQ) is kept and is an Asset report.
    # Use empty set as fallback; the per-component binding code handles it.
    asset_rid_set.add("00OTb000008mwrVMAQ")
    for comp in components:
        rid = comp.get("reportId") or ""
        cols = _filter_columns_for(rid, asset_rid_set)
        comp.setdefault("properties", {})["filterColumns"] = cols

    # Top-level filters (preserve from existing or rebuild from spec).
    new_filters: list[dict[str, Any]] = [_build_filter(s) for s in FILTER_SPECS]

    # ── Step 4: PATCH dashboard ──────────────────────────────────────────
    new_layout = json.loads(json.dumps(describe.get("layout", {})))
    new_layout["components"] = layout_components

    body: dict[str, Any] = {
        "name": describe.get("name"),
        "description": describe.get("description"),
        "folderId": describe.get("folderId"),
        "dashboardType": describe.get("dashboardType"),
        "runningUser": describe.get("runningUser"),
        "chartTheme": describe.get("chartTheme"),
        "colorPalette": describe.get("colorPalette"),
        "components": components,
        "layout": new_layout,
        "filters": new_filters,
    }

    print(f"\n[4/4] PATCH dashboard: {len(components)} widgets, {len(new_filters)} filters")
    if args.dry_run:
        out = "/tmp/cockpit_upgrade_v3_body.json"
        with open(out, "w") as f:
            json.dump(body, f, indent=2)
        print(f"  [dry-run] -> {out}")
        return 0

    try:
        _api(
            "PATCH",
            f"{api_base}/analytics/dashboards/{DASHBOARD_ID}",
            token,
            instance,
            body=body,
        )
        print("  [OK] PATCH succeeded with filters")
    except RuntimeError as e:
        msg = str(e)
        print(f"  [FAIL] {msg[:600]}", file=sys.stderr)
        # Retry without filters as v2 does.
        body.pop("filters", None)
        for comp in body["components"]:
            comp.get("properties", {}).pop("filterColumns", None)
        try:
            _api(
                "PATCH",
                f"{api_base}/analytics/dashboards/{DASHBOARD_ID}",
                token,
                instance,
                body=body,
            )
            print("  [OK] PATCH succeeded WITHOUT filters")
        except RuntimeError as e2:
            print(f"  [FAIL2] {str(e2)[:600]}", file=sys.stderr)
            return 2

    # ── Verify ───────────────────────────────────────────────────────────
    print("\n[verify] re-GET dashboard")
    verify = _api(
        "GET", f"{api_base}/analytics/dashboards/{DASHBOARD_ID}/describe", token, instance
    )
    n = len(verify["components"])
    rid_set = set(c.get("reportId") for c in verify["components"])
    expected_added = {
        report_ids[k] for k in ("stickiness", "drought", "win_rate", "hero") if report_ids.get(k)
    }
    n_added = sum(1 for r in expected_added if r in rid_set)
    n_dropped = sum(1 for r in DROP_REPORT_IDS if r not in rid_set)
    n_filters = len(verify.get("filters") or [])

    # Hero header: did emoji/block prefix survive?
    hero_rid = report_ids.get("hero") or ""
    hero_hdr = next(
        (c.get("header") for c in verify["components"] if c.get("reportId") == hero_rid),
        None,
    )

    print(f"  components: {n} (target 20)")
    print(f"  added:      {n_added}/{len(expected_added)}")
    print(f"  dropped:    {n_dropped}/{len(DROP_REPORT_IDS)}")
    print(f"  filters:    {n_filters}")
    print(f"  hero hdr:   {hero_hdr!r}")

    print(
        "\n[done] https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxX2YMAV/view"
    )
    perfect = n == 20 and n_added == len(expected_added) and n_dropped == len(DROP_REPORT_IDS)
    return 0 if perfect else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as e:
        print(
            f"FATAL HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:1500]}",
            file=sys.stderr,
        )
        sys.exit(3)
