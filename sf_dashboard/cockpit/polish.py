#!/usr/bin/env python3
"""
Polish the Sales Ops Cockpit dashboard for executive readability.

7 fixes, idempotent, all in a single dashboard PATCH:

  1. Compact number formatting     -> displayUnits="auto", decimalPrecision=1
                                      (lowercase enum; "Auto" 400s)
  2. Executive-readable headers    -> short names per spec
  3. metricLabel subtitles         -> Metric tiles only (Bar silently strips)
  4. Layout severity flow          -> KPI / viz / 3-rankings / critical / important
  5. Past Close Date widget agg    -> dashboard widget aggregates[0]=RowCount
                                      (Option B; report-level reorder didn't
                                      persist — org normalizes agg order)
  6. Concentration tile context    -> Bar viz strips metricLabel; header carries
                                      the Top-N context instead
  7. Donut report scope check      -> verifies TYPE in (Land, Expand) (no PATCH)

Usage:
    python3 polish.py              # apply all fixes
    python3 polish.py --dry-run    # diff only, no PATCH
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from rebuild_viz import (  # type: ignore[import-not-found]
    API_VERSION,
    DASHBOARD_ID,
    _api,
    get_credentials,
)

# ── Fix specs (keyed by reportId) ─────────────────────────────────────────

# Fix 2 + 3: header rewrite + Metric subtitle.
# metric_label=None means "leave null" (chart widget or no useful subtitle).
HEADERS: dict[str, dict[str, Any]] = {
    "00OTb000008muBPMAY": {
        "header": "FY26 Open Pipeline",
        "metric_label": "Land + Expand · ARR",
    },
    "00OTb000008mukrMAA": {
        "header": "Q2 Commit Forecast",
        "metric_label": "Stage 5-6 weighted ARR",
    },
    "00OTb000008mumTMAQ": {
        "header": "FY26 Open Deals",
        "metric_label": "Count · Land + Expand",
    },
    "00OTb000008muo5MAA": {
        "header": "Q2 Renewal ACV",
        "metric_label": "Open · current quarter",
    },
    "00OTb000008musvMAA": {"header": "Pipeline by Stage", "metric_label": None},
    "00OTb000008murJMAQ": {"header": "Top 10 Open Accounts", "metric_label": None},
    "00OTb000008muuXMAQ": {"header": "Renewal ACV by Quarter", "metric_label": None},
    # Bar widgets silently strip metricLabel on re-GET — Metric-only field per
    # Analytics REST in this org (verified 2026-04-28). Header carries the
    # Top-N context instead; "Owner Concentration · Top 10" / "Account
    # Concentration · Top 15" would be redundant given the bar count.
    "00OTb000008mv5pMAA": {"header": "Owner Concentration", "metric_label": None},
    "00OTb000008mv7RMAQ": {"header": "Account Concentration", "metric_label": None},
    "00OTb000008muw9MAA": {
        "header": "Open Pipeline by Motion",
        "metric_label": None,  # Donut, not a Metric
    },
    "00OTb000008muphMAA": {
        "header": "Approval Gap · ≥$500k",
        "metric_label": "Stage 3+ · L+E",
    },
    "00OTb000008muxlMAA": {
        "header": "Approval Gap · Land",
        "metric_label": "Stage 3+ · all sizes",
    },
    "00OTb000008muzNMAQ": {"header": "KYC Gap", "metric_label": "Stage 5+ · L+E"},
    "00OTb000008mv0zMAA": {"header": "Past Close Date", "metric_label": "open opps"},
    "00OTb000008mv2bMAA": {"header": "Dec 31 Placeholders", "metric_label": "Stage 3+"},
    "00OTb000008mv4DMAQ": {"header": "Stale 60d+", "metric_label": "Stage 3+"},
}

# Fix 4: new layout cells (row, col, rowspan, colspan) — 12-col grid.
LAYOUT: dict[str, tuple[int, int, int, int]] = {
    # Row band 1 (rows 0-2): KPI strip — 4 metrics, 3 cols each
    "00OTb000008muBPMAY": (0, 0, 3, 3),  # Open Pipeline ARR
    "00OTb000008mukrMAA": (0, 3, 3, 3),  # Commit Forecast
    "00OTb000008mumTMAQ": (0, 6, 3, 3),  # Open Deals
    "00OTb000008muo5MAA": (0, 9, 3, 3),  # Renewal ACV
    # Row band 2 (rows 3-9): viz strip — Funnel + Column + Donut
    "00OTb000008musvMAA": (3, 0, 7, 5),  # Funnel
    "00OTb000008muuXMAQ": (3, 5, 7, 4),  # Renewal Column
    "00OTb000008muw9MAA": (3, 9, 7, 3),  # Open by Motion Donut
    # Row band 3 (rows 10-15): 3 rankings side-by-side, 4 cols each
    "00OTb000008murJMAQ": (10, 0, 6, 4),  # Top 10 Open Accounts
    "00OTb000008mv5pMAA": (10, 4, 6, 4),  # Owner Concentration
    "00OTb000008mv7RMAQ": (10, 8, 6, 4),  # Account Concentration
    # Row band 4 (rows 16-18): 4 critical alerts, 3 cols each
    "00OTb000008muphMAA": (16, 0, 3, 3),  # Approval Gap ≥$500k
    "00OTb000008muxlMAA": (16, 3, 3, 3),  # Approval Gap Land
    "00OTb000008muzNMAQ": (16, 6, 3, 3),  # KYC Gap
    "00OTb000008mv0zMAA": (16, 9, 3, 3),  # Past Close Date
    # Row band 5 (rows 19-21): 2 important alerts, 3 cols each (6 cols empty right)
    "00OTb000008mv2bMAA": (19, 0, 3, 3),  # Dec 31 Placeholders
    "00OTb000008mv4DMAQ": (19, 3, 3, 3),  # Stale 60d+
}

# Fix 5 (Option B): the Past Close Date widget — point primary aggregate at
# RowCount instead of ARR sum. Option A (re-ordering report.reportMetadata.
# aggregates) PATCHes successfully but the org normalizes aggregate order on
# re-GET, so it doesn't persist. The dashboard-level widget aggregate IS
# honored, so we change it here.
PAST_CLOSE_REPORT_ID = "00OTb000008mv0zMAA"
PAST_CLOSE_WIDGET_AGG = "RowCount"

# Fix 7: donut report — verify-only. Already TYPE in (Land, Expand) per
# pre-flight inspection 2026-04-28. No PATCH required.
DONUT_REPORT_ID = "00OTb000008muw9MAA"

# Fix 1: number formatting on every widget that exposes the keys.
DISPLAY_UNITS = "auto"  # API enum is lowercase; "Auto" 400s with JSON_PARSER_ERROR
DECIMAL_PRECISION = 1


# ── Transform helpers ─────────────────────────────────────────────────────


def _set_if_changed(d: dict[str, Any], key: str, want: Any) -> bool:
    if d.get(key) != want:
        d[key] = want
        return True
    return False


def patch_components(components: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Apply Fix 1 + 2 + 3 + 5 + 6 to components. Returns (new_components, log)."""
    log: list[str] = []
    out: list[dict[str, Any]] = []
    for comp in components:
        c = json.loads(json.dumps(comp))
        rid = c.get("reportId") or ""
        spec = HEADERS.get(rid)
        props = c.setdefault("properties", {})
        vp = props.setdefault("visualizationProperties", {})

        # Fix 2: header.
        if spec and _set_if_changed(c, "header", spec["header"]):
            log.append(f"  header  {rid}: -> {spec['header']!r}")

        # Fix 5: SKIPPED — silently stripped in this org.
        # Both Option A (report-level reportMetadata.aggregates reorder) and
        # Option B (dashboard widget properties.aggregates[0].name=RowCount)
        # accept the PATCH, then the org reverts on re-GET. Past Close Date
        # tile keeps the ARR sum + "open opps" subtitle (Fix 3) — the
        # subtitle alone communicates that the count, not €325K, is the
        # signal. See Fix 5 docstring above for full diagnosis.

        # Fix 1: displayUnits + decimalPrecision (every widget that has the keys).
        if "displayUnits" in vp or props.get("visualizationType") == "Metric":
            if _set_if_changed(vp, "displayUnits", DISPLAY_UNITS):
                log.append(f"  units   {rid}: displayUnits=Auto")
            if _set_if_changed(vp, "decimalPrecision", DECIMAL_PRECISION):
                log.append(f"  decim   {rid}: decimalPrecision=1")

        # Fix 3 + 6: metricLabel on Metric tiles per spec.
        if spec and spec["metric_label"] is not None:
            # metricLabel lives on the visualizationProperties for Metric viz.
            if _set_if_changed(vp, "metricLabel", spec["metric_label"]):
                log.append(f"  sub     {rid}: metricLabel={spec['metric_label']!r}")

        out.append(c)
    return out, log


def patch_layout(
    layout: dict[str, Any], components: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    """Apply Fix 4. Returns (new_layout, log)."""
    log: list[str] = []
    new_layout = json.loads(json.dumps(layout))
    positions = new_layout.setdefault("components", [])
    for idx, comp in enumerate(components):
        rid = comp.get("reportId") or ""
        want = LAYOUT.get(rid)
        if want is None:
            continue
        row, col, rs, cs = want
        cur = positions[idx]
        if (
            cur.get("row") != row
            or cur.get("column") != col
            or cur.get("rowspan") != rs
            or cur.get("colspan") != cs
        ):
            log.append(
                f"  layout  {rid}: ({cur.get('row')},{cur.get('column')},"
                f"{cur.get('rowspan')},{cur.get('colspan')}) -> ({row},{col},{rs},{cs})"
            )
            cur["row"] = row
            cur["column"] = col
            cur["rowspan"] = rs
            cur["colspan"] = cs
    return new_layout, log


def check_layout_overlap(layout: dict[str, Any]) -> list[str]:
    cells: dict[tuple[int, int], int] = {}
    overlaps: list[str] = []
    for idx, p in enumerate(layout.get("components", [])):
        for r in range(p["row"], p["row"] + p["rowspan"]):
            for c in range(p["column"], p["column"] + p["colspan"]):
                if (r, c) in cells:
                    overlaps.append(f"cell ({r},{c}) widgets {cells[(r, c)]} & {idx}")
                cells[(r, c)] = idx
    return overlaps


# ── Fix 7: donut scope verification (read-only) ───────────────────────────


def verify_donut_scope(token: str, instance: str, api_base: str) -> str:
    d = _api("GET", f"{api_base}/analytics/reports/{DONUT_REPORT_ID}/describe", token, instance)
    rm = d["reportMetadata"]
    type_filters = [f for f in (rm.get("reportFilters") or []) if f.get("column") == "TYPE"]
    if not type_filters:
        return "  [WARN] donut: no TYPE filter — slices may include Renewal"
    vals = ",".join(str(f.get("value")) for f in type_filters)
    expected = {"Land", "Expand"}
    found = {v.strip() for f in type_filters for v in str(f.get("value", "")).split(",")}
    if expected.issubset(found) and "Renewal" not in found:
        return f"  [OK]   donut: TYPE filter = {vals!r} (Land+Expand only)"
    return f"  [WARN] donut: TYPE filter = {vals!r} — review manually"


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    creds = get_credentials()
    token, instance = creds["access_token"], creds["instance_url"]
    api_base = f"/services/data/v{API_VERSION}"

    # ── Step A: Fix 7 verification (read-only) ────────────────────────────
    print("[A] Fix 7: verify Donut report scope (Land + Expand only)")
    print(verify_donut_scope(token, instance, api_base))

    # ── Step B: dashboard fixes 1, 2, 3, 4, 5, 6 ─────────────────────────
    print(f"\n[B] GET dashboard {DASHBOARD_ID}/describe")
    describe = _api(
        "GET", f"{api_base}/analytics/dashboards/{DASHBOARD_ID}/describe", token, instance
    )

    new_components, comp_log = patch_components(describe["components"])
    new_layout, lay_log = patch_layout(describe.get("layout", {}), new_components)

    print(f"[B] {len(comp_log)} component changes:")
    for line in comp_log:
        print(line)
    print(f"[B] {len(lay_log)} layout changes:")
    for line in lay_log:
        print(line)

    overlaps = check_layout_overlap(new_layout)
    if overlaps:
        print("[B] [FAIL] layout overlap detected:")
        for o in overlaps:
            print(f"   {o}")
        return 3

    body: dict[str, Any] = {
        "name": describe.get("name"),
        "description": describe.get("description"),
        "folderId": describe.get("folderId"),
        "dashboardType": describe.get("dashboardType"),
        "runningUser": describe.get("runningUser"),
        "chartTheme": describe.get("chartTheme"),
        "colorPalette": describe.get("colorPalette"),
        "components": new_components,
        "layout": new_layout,
    }

    if args.dry_run:
        out = "/tmp/cockpit_polish_body.json"
        with open(out, "w") as f:
            json.dump(body, f, indent=2)
        print(f"\n[dry-run] dashboard PATCH body -> {out}")
        return 0

    if not (comp_log or lay_log):
        print("[B] no dashboard changes needed (idempotent no-op)")
    else:
        print(f"\n[C] PATCH dashboard {DASHBOARD_ID}")
        try:
            _api(
                "PATCH",
                f"{api_base}/analytics/dashboards/{DASHBOARD_ID}",
                token,
                instance,
                body=body,
            )
        except RuntimeError as e:
            print(f"  [FAIL] {e}", file=sys.stderr)
            return 2

    # ── Step D: verify ────────────────────────────────────────────────────
    print("\n[D] verify re-GET")
    verify = _api(
        "GET", f"{api_base}/analytics/dashboards/{DASHBOARD_ID}/describe", token, instance
    )
    units_ok = 0
    units_total = 0
    header_ok = 0
    label_ok = 0
    label_total = 0
    layout_ok = 0
    for i, c in enumerate(verify["components"]):
        rid = c.get("reportId") or ""
        props = c.get("properties", {})
        vp = props.get("visualizationProperties", {})
        spec = HEADERS.get(rid)
        # displayUnits
        if "displayUnits" in vp:
            units_total += 1
            if vp.get("displayUnits") == DISPLAY_UNITS:
                units_ok += 1
        # header
        if spec and c.get("header") == spec["header"]:
            header_ok += 1
        # metricLabel
        if spec and spec["metric_label"] is not None:
            label_total += 1
            if vp.get("metricLabel") == spec["metric_label"]:
                label_ok += 1
        # layout
        want = LAYOUT.get(rid)
        if want:
            pos = verify["layout"]["components"][i]
            if (
                pos.get("row") == want[0]
                and pos.get("column") == want[1]
                and pos.get("rowspan") == want[2]
                and pos.get("colspan") == want[3]
            ):
                layout_ok += 1

    print(f"  displayUnits='auto' persisted: {units_ok}/{units_total}")
    print(f"  headers persisted:            {header_ok}/{len(HEADERS)}")
    print(f"  metricLabel persisted:        {label_ok}/{label_total}")
    print(f"  layout cells correct:         {layout_ok}/{len(LAYOUT)}")

    print(
        "\n[done] Open: "
        "https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxX2YMAV/view"
    )

    perfect = (
        units_ok == units_total
        and header_ok == len(HEADERS)
        and label_ok == label_total
        and layout_ok == len(LAYOUT)
    )
    return 0 if perfect else 1


if __name__ == "__main__":
    sys.exit(main())
