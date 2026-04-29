#!/usr/bin/env python3
"""
Sales Rep Scorecard widget: Stale Deals by Rep.

Shows count + ARR of open Land+Expand opps with no activity in 14+ days,
grouped by Opportunity Owner. Live numbers (verified 2026-04-29):
1,631 stale opps representing EUR 417.6M ARR. Adam Hatcliff (the
concentration-alert target) has 26 stale opps = EUR 30.5M.

Single-purpose, ships report only (no dashboard wrap — REST dashboard
CREATE returns 403 in this org). User can run the report directly in
Lightning, or admin can wrap it in a dashboard later.

Mirrors the cockpit-style report-creation pattern from upgrade_v2.py.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
from typing import Any

from rebuild_viz import (  # type: ignore[import-not-found]
    API_VERSION,
    _api,
    get_credentials,
)
from upgrade_v2 import (  # type: ignore[import-not-found]
    EXCLUDE_OPP_CRITERIA,
    REPORT_FOLDER_ID,
    _find_or_create_report,
)


STALE_REPORT: dict[str, Any] = {
    "developerName": "Scorecard_Stale_Deals_by_Rep_v1",
    "name": "Scorecard · Stale Deals by Rep",
    "header": "Stale Land+Expand Open Pipeline by Owner (no activity 14d+)",
    "reportFormat": "SUMMARY",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "STAGE_NAME",
        "Opportunity.APTS_Opportunity_ARR__c",
        "LAST_ACTIVITY",
    ],
    "groupingsDown": [
        # Group by Opportunity Owner — gives one summary row per rep.
        {"name": "FULL_NAME", "sortOrder": "Asc"},
    ],
    "aggregates": [
        "s!Opportunity.APTS_Opportunity_ARR__c",
        "RowCount",
    ],
    "filters": [
        {"column": "TYPE", "operator": "equals", "value": "Land,Expand"},
        {"column": "CLOSED", "operator": "equals", "value": "False"},
        # Two stale predicates ORed via reportBooleanFilter below:
        #   filter 3: LastActivityDate < 14 days ago (truly stale)
        #   filter 4: LastActivityDate equals "" (never touched)
        # SF Reports `lessThan LAST_N_DAYS:14` does NOT include null
        # opps — verified 2026-04-29: 384 opps without null vs 1,631
        # with null. The null bucket is EUR 200M of never-touched
        # pipeline (1,247 opps), THE most stale subset, and missing it
        # would understate the coaching signal by 60%.
        {
            "column": "LAST_ACTIVITY",
            "operator": "lessThan",
            "value": "LAST_N_DAYS:14",
        },
        {
            "column": "LAST_ACTIVITY",
            "operator": "equals",
            "value": "",
        },
    ],
    "exclusion": EXCLUDE_OPP_CRITERIA,
    # Filter logic: TYPE AND CLOSED AND (stale OR never-touched) AND
    # all 11 test-artifact exclusions. Hard-coded boolean string is
    # brittle vs. EXCLUDE_OPP_CRITERIA changes; computed in builder.
    "_use_boolean_filter": True,
    "standardDateFilter": {
        "column": "CLOSE_DATE",
        "durationValue": "CUSTOM",
        "startDate": "2000-01-01",
        "endDate": "2099-12-31",
    },
}


def _build_stale_body(rpt: dict[str, Any]) -> dict[str, Any]:
    base_filters = list(rpt.get("filters", []))
    exclusions = list(rpt.get("exclusion", []))
    n_base = len(base_filters)  # expected: 4 (TYPE, CLOSED, stale, null)
    n_excl = len(exclusions)
    # Boolean: filters 1+2 AND (3 OR 4) AND all exclusion filters
    boolean_parts = ["1", "2", "(3 OR 4)"]
    boolean_parts.extend(str(i) for i in range(n_base + 1, n_base + n_excl + 1))
    boolean_filter = " AND ".join(boolean_parts)

    rm: dict[str, Any] = {
        "name": rpt["name"],
        "description": "",
        "reportFormat": rpt["reportFormat"],
        "reportType": rpt["reportType"],
        "detailColumns": list(rpt["detailColumns"]),
        "aggregates": list(rpt["aggregates"]),
        "groupingsDown": [
            {"name": g["name"], "sortOrder": g.get("sortOrder", "Asc")}
            for g in rpt.get("groupingsDown", [])
        ],
        "reportFilters": [*base_filters, *exclusions],
        "reportBooleanFilter": boolean_filter,
        "standardDateFilter": rpt["standardDateFilter"],
        "folderId": REPORT_FOLDER_ID,
        "developerName": rpt["developerName"],
    }
    return {"reportMetadata": rm}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    creds = get_credentials()
    token, instance = creds["access_token"], creds["instance_url"]
    api_base = f"/services/data/v{API_VERSION}"

    print("[1/2] Build / update Stale Deals by Rep report")
    if args.dry_run:
        # Dry-run mode: build the body, validate via JSON dump, don't POST.
        body = _build_stale_body(STALE_REPORT)
        import json

        out = "/tmp/scorecard_stale_body.json"
        with open(out, "w") as f:
            json.dump(body, f, indent=2)
        print(f"  [dry-run] body -> {out}")
        return 0

    rid = _find_or_create_report(STALE_REPORT, _build_stale_body, token, instance, api_base)
    print(f"  -> {rid}")
    print(f"  view: https://simcorp.lightning.force.com/lightning/r/Report/{rid}/view")

    # 2. Run + summarize for stdout
    print("\n[2/2] Top 10 reps by stale ARR exposure")
    run = _api(
        "GET",
        f"{api_base}/analytics/reports/{rid}?includeDetails=false",
        token,
        instance,
    )
    fact = run.get("factMap", {})
    gd = run.get("groupingsDown", {}).get("groupings", [])
    # aggregates[0] = sum ARR, aggregates[1] = RowCount (matches the
    # `aggregates` order in the report spec).
    grand_arr = fact.get("T!T", {}).get("aggregates", [{}])[0].get("value", 0)
    grand_count = fact.get("T!T", {}).get("aggregates", [{}])[1].get("value", 0)

    rows = []
    for g in gd:
        key = g.get("key")
        rep = g.get("label", "?")
        cell = fact.get(f"{key}!T", {}).get("aggregates", [])
        arr = cell[0].get("value", 0) if len(cell) > 0 else 0
        cnt = cell[1].get("value", 0) if len(cell) > 1 else 0
        rows.append((arr, cnt, rep))

    rows.sort(reverse=True)
    print(f"  {'Owner':35s} {'Opps':>5s}  {'Stale ARR':>16s}")
    for arr, cnt, rep in rows[:10]:
        print(f"  {rep[:35]:35s} {cnt:>5d}  EUR {arr:>12,.0f}")
    print(f"\n  GRAND: {grand_count} stale opps, EUR {grand_arr:,.0f} ARR (across {len(gd)} reps)")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as e:
        print(
            f"FATAL HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:1500]}",
            file=sys.stderr,
        )
        sys.exit(3)
