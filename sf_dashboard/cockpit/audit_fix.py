#!/usr/bin/env python3
"""
Audit + fix 4 specific issues on the Sales Ops Cockpit dashboard.

Issues:
  1. drillUrl null on 6 chart widgets -> set to /lightning/r/Report/<id>/view
  2. maxRows null on 3 Bar widgets    -> set to 10/10/15
  3. sortBy empty on 3 ranking reports -> sort grouping descending by ARR
  4. Account Concentration too short  -> rowspan 3 -> 6

Idempotent. PATCHes existing reports + dashboard via Analytics REST.

Usage:
    python3 audit_fix.py                # apply all 4 fixes
    python3 audit_fix.py --dry-run      # print what would change, no PATCH
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# Reuse helpers (same auth/api pattern as rebuild_viz.py).
from rebuild_viz import (  # type: ignore[import-not-found]
    API_VERSION,
    DASHBOARD_ID,
    _api,
    get_credentials,
)

# ── Fix specs ──────────────────────────────────────────────────────────────

# Widgets that need drillUrl (6 chart widgets — Funnel, Column, Donut, 3 Bars).
# Reportd via reportId.
DRILL_REPORT_IDS: set[str] = {
    "00OTb000008musvMAA",  # Funnel — Pipeline by Stage
    "00OTb000008muuXMAQ",  # Column — Renewal ACV by Fiscal Quarter
    "00OTb000008muw9MAA",  # Donut  — Open ARR by Type
    "00OTb000008murJMAQ",  # Bar    — Top Open Accounts
    "00OTb000008mv5pMAA",  # Bar    — Owner Concentration
    "00OTb000008mv7RMAQ",  # Bar    — Account Concentration
}

# Widgets that need a row cap.
MAX_ROWS_BY_REPORT_ID: dict[str, int] = {
    "00OTb000008murJMAQ": 10,  # Top Open Accounts
    "00OTb000008mv5pMAA": 10,  # Owner Concentration
    "00OTb000008mv7RMAQ": 15,  # Account Concentration
}

# Reports that need descending-sort on their first grouping by ARR aggregate.
SORT_REPORT_IDS: set[str] = {
    "00OTb000008murJMAQ",  # Top Open Accounts
    "00OTb000008mv5pMAA",  # Owner Concentration
    "00OTb000008mv7RMAQ",  # Account Concentration
}
SORT_AGGREGATE = "s!Opportunity.APTS_Opportunity_ARR__c"

# Layout fix — Account Concentration: rowspan 3 -> 6 (cols 6-11, rows 19-24).
# Adjacent cells: nothing else lives in cols 6-11 below row 19, so this is safe.
ACCOUNT_CONC_REPORT_ID = "00OTb000008mv7RMAQ"
ACCOUNT_CONC_NEW_ROWSPAN = 6


# ── drillUrl format selection ──────────────────────────────────────────────


# Try modern Lightning URL first; fall back to one.app form if validator rejects.
def lightning_drill_url(report_id: str) -> str:
    return f"/lightning/r/Report/{report_id}/view"


def classic_drill_url(report_id: str) -> str:
    return f"/one/one.app#/sObject/{report_id}/view"


# ── Report sort patcher ────────────────────────────────────────────────────


def patch_report_sort(
    report_id: str, token: str, instance: str, api_base: str, dry_run: bool
) -> tuple[bool, str]:
    """PATCH /analytics/reports/<id> to sort first grouping desc by ARR.

    Returns (changed, msg).
    """
    describe = _api("GET", f"{api_base}/analytics/reports/{report_id}/describe", token, instance)
    rm = describe["reportMetadata"]
    groupings = rm.get("groupingsDown") or []
    if not groupings:
        return False, f"  [SKIP] {report_id}: no groupingsDown — cannot sort by aggregate"

    g0 = groupings[0]
    current_agg = g0.get("sortAggregate")
    current_order = g0.get("sortOrder")
    if current_agg == SORT_AGGREGATE and current_order == "Desc":
        return False, f"  [OK]   {report_id}: already sorted desc by ARR"

    g0["sortAggregate"] = SORT_AGGREGATE
    g0["sortOrder"] = "Desc"
    # Do NOT set top-level reportMetadata.sortBy with the aggregate value.
    # This org's validator rejects with errorCode 113 ("sort column must be
    # from a selected column") because sortBy is for TABULAR detail-column
    # sort. For SUMMARY reports with grouping-by-aggregate, the canonical
    # location is groupingsDown[i].sortAggregate (set above).

    body = {"reportMetadata": rm}
    if dry_run:
        return True, (
            f"  [DRY]  {report_id}: would set groupingsDown[0].sortAggregate={SORT_AGGREGATE} Desc"
        )
    try:
        _api(
            "PATCH",
            f"{api_base}/analytics/reports/{report_id}",
            token,
            instance,
            body=body,
        )
    except RuntimeError as e:
        return False, f"  [FAIL] {report_id}: {e}"
    return True, f"  [DONE] {report_id}: sortAggregate=ARR Desc applied"


# ── Dashboard patcher ──────────────────────────────────────────────────────


def build_dashboard_patch(
    describe: dict[str, Any], drill_url_fn: Any
) -> tuple[dict[str, Any], list[str]]:
    """Mutate components + layout for fixes 1, 2, 4. Returns (body, log_lines)."""
    log: list[str] = []
    new_components: list[dict[str, Any]] = []

    for comp in describe["components"]:
        c = json.loads(json.dumps(comp))
        rid = c.get("reportId") or ""
        props = c.setdefault("properties", {})

        # Fix 1: drillUrl on chart widgets.
        if rid in DRILL_REPORT_IDS:
            want = drill_url_fn(rid)
            cur = props.get("drillUrl")
            if cur != want:
                props["drillUrl"] = want
                log.append(f"  drill   {rid}: {cur!r} -> {want!r}")

        # Fix 2: maxRows on Bar widgets.
        if rid in MAX_ROWS_BY_REPORT_ID:
            want_max = MAX_ROWS_BY_REPORT_ID[rid]
            cur_max = props.get("maxRows")
            if cur_max != want_max:
                props["maxRows"] = want_max
                log.append(f"  maxRows {rid}: {cur_max!r} -> {want_max}")

        new_components.append(c)

    # Fix 4: layout — Account Concentration rowspan 3 -> 6.
    new_layout = json.loads(json.dumps(describe.get("layout", {})))
    positions = new_layout.get("components", [])
    for i, comp in enumerate(describe["components"]):
        if comp.get("reportId") == ACCOUNT_CONC_REPORT_ID:
            pos = positions[i]
            cur_rs = pos.get("rowspan")
            if cur_rs != ACCOUNT_CONC_NEW_ROWSPAN:
                pos["rowspan"] = ACCOUNT_CONC_NEW_ROWSPAN
                log.append(
                    f"  resize  Account Concentration: rowspan {cur_rs} -> {ACCOUNT_CONC_NEW_ROWSPAN}"
                )
            break

    body = {
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
    return body, log


def check_layout_overlap(layout: dict[str, Any]) -> list[str]:
    """Return list of overlap descriptions (empty if grid is non-overlapping)."""
    cells: dict[tuple[int, int], int] = {}
    overlaps: list[str] = []
    for idx, p in enumerate(layout.get("components", [])):
        for r in range(p["row"], p["row"] + p["rowspan"]):
            for c in range(p["column"], p["column"] + p["colspan"]):
                if (r, c) in cells:
                    overlaps.append(f"cell ({r},{c}) used by widget {cells[(r, c)]} and {idx}")
                cells[(r, c)] = idx
    return overlaps


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--drill-url-style",
        choices=["lightning", "classic"],
        default="lightning",
        help="lightning -> /lightning/r/Report/<id>/view (default); classic -> /one/one.app#/...",
    )
    args = ap.parse_args()

    creds = get_credentials()
    token, instance = creds["access_token"], creds["instance_url"]
    api_base = f"/services/data/v{API_VERSION}"
    drill_fn = lightning_drill_url if args.drill_url_style == "lightning" else classic_drill_url

    # ── Step A: report sort ───────────────────────────────────────────────
    print(f"[A] Sort {len(SORT_REPORT_IDS)} ranking reports by ARR Desc")
    sort_changed = 0
    for rid in sorted(SORT_REPORT_IDS):
        changed, msg = patch_report_sort(rid, token, instance, api_base, args.dry_run)
        print(msg)
        if changed:
            sort_changed += 1

    # ── Step B: dashboard fixes ───────────────────────────────────────────
    print(f"\n[B] GET dashboard {DASHBOARD_ID}/describe")
    describe = _api(
        "GET", f"{api_base}/analytics/dashboards/{DASHBOARD_ID}/describe", token, instance
    )
    body, change_log = build_dashboard_patch(describe, drill_fn)

    print(f"[B] {len(change_log)} dashboard changes:")
    for line in change_log:
        print(line)

    overlaps = check_layout_overlap(body["layout"])
    if overlaps:
        print("[B] [FAIL] layout overlap detected after resize:")
        for o in overlaps:
            print(f"   {o}")
        return 3

    if args.dry_run:
        out = "/tmp/cockpit_audit_fix_body.json"
        with open(out, "w") as f:
            json.dump(body, f, indent=2)
        print(f"\n[dry-run] dashboard PATCH body -> {out}")
        return 0

    if not change_log:
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
            # If lightning style failed validation, retry with classic.
            if args.drill_url_style == "lightning":
                print("  [RETRY] re-attempting with classic /one/one.app drill style")
                body2, _ = build_dashboard_patch(describe, classic_drill_url)
                try:
                    _api(
                        "PATCH",
                        f"{api_base}/analytics/dashboards/{DASHBOARD_ID}",
                        token,
                        instance,
                        body=body2,
                    )
                    print("  [OK] classic drill URL accepted")
                except RuntimeError as e2:
                    print(f"  [FAIL2] {e2}", file=sys.stderr)
                    return 2
            else:
                return 2

    # ── Step D: verify ────────────────────────────────────────────────────
    print("\n[D] verify dashboard re-GET")
    verify = _api(
        "GET", f"{api_base}/analytics/dashboards/{DASHBOARD_ID}/describe", token, instance
    )
    drill_ok = sum(
        1
        for c in verify["components"]
        if c.get("reportId") in DRILL_REPORT_IDS and c.get("properties", {}).get("drillUrl")
    )
    max_ok = sum(
        1
        for c in verify["components"]
        if c.get("reportId") in MAX_ROWS_BY_REPORT_ID
        and c.get("properties", {}).get("maxRows") == MAX_ROWS_BY_REPORT_ID[c["reportId"]]
    )
    rowspan_ok = False
    for i, c in enumerate(verify["components"]):
        if c.get("reportId") == ACCOUNT_CONC_REPORT_ID:
            rowspan_ok = (
                verify["layout"]["components"][i].get("rowspan") == ACCOUNT_CONC_NEW_ROWSPAN
            )
            break
    print(f"  drillUrl set:    {drill_ok}/{len(DRILL_REPORT_IDS)}")
    print(f"  maxRows set:     {max_ok}/{len(MAX_ROWS_BY_REPORT_ID)}")
    print(f"  Account Conc rowspan={ACCOUNT_CONC_NEW_ROWSPAN}: {rowspan_ok}")

    print("\n[D] verify report sort")
    sort_verified = 0
    for rid in sorted(SORT_REPORT_IDS):
        d = _api("GET", f"{api_base}/analytics/reports/{rid}/describe", token, instance)
        g0 = (d["reportMetadata"].get("groupingsDown") or [{}])[0]
        ok = g0.get("sortAggregate") == SORT_AGGREGATE and g0.get("sortOrder") == "Desc"
        print(
            f"  {rid}: sortAggregate={g0.get('sortAggregate')!r} sortOrder={g0.get('sortOrder')!r} {'OK' if ok else 'MISS'}"
        )
        if ok:
            sort_verified += 1
    print(f"  sort verified:   {sort_verified}/{len(SORT_REPORT_IDS)}")

    print(
        "\n[done] Open: https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxX2YMAV/view"
    )
    return 0 if (drill_ok == 6 and max_ok == 3 and rowspan_ok and sort_verified == 3) else 1


if __name__ == "__main__":
    sys.exit(main())
