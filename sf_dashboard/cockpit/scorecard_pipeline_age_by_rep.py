#!/usr/bin/env python3
"""
Pipeline Age by Rep — Owner × AgeBand matrix.

Companion to `scorecard_pipeline_age.py` (org-level distribution).
This per-rep cut surfaces who owns the zombie book. Live numbers
verified 2026-04-29:
- Adam Hatcliff: EUR 51.3M open, of which EUR 27.9M (54%) is >2yr
- Johanna Hornwall: EUR 25.0M open, of which EUR 16.0M (64%) is >2yr
- Frédéric Jean: EUR 32.9M open, only 28% >2yr (healthier despite the
  EUR 17M deal stuck at Commercial Approval)

Live as widget 9 on the Sales Rep Scorecard dashboard.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
from typing import Any

from rebuild_viz import API_VERSION, _api, get_credentials  # type: ignore[import-not-found]
from upgrade_v2 import (  # type: ignore[import-not-found]
    EXCLUDE_OPP_CRITERIA,
    REPORT_FOLDER_ID,
    _find_or_create_report,
)


REPORT: dict[str, Any] = {
    "developerName": "Scorecard_Pipeline_Age_by_Rep_v1",
    "name": "Scorecard · Pipeline Age by Rep",
    "header": "Open Land+Expand pipeline ARR — Owner × Age band",
    "reportFormat": "MATRIX",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "Opportunity.APTS_Opportunity_ARR__c",
        "AGE",
    ],
    "groupingsDown": [
        {"name": "FULL_NAME", "sortOrder": "Asc"},
    ],
    "groupingsAcross": [
        {"name": "BucketField_AgeBand", "sortOrder": "Asc"},
    ],
    "aggregates": [
        "s!Opportunity.APTS_Opportunity_ARR__c",
        "RowCount",
    ],
    "filters": [
        # Per AGENTS.md SimCorp rules: ARR side only, explicit Type filter.
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
    # Numeric bucket on AGE — same shape as the org-level age widget.
    "buckets": [
        {
            "developerName": "BucketField_AgeBand",
            "label": "Age Band",
            "sourceColumnName": "AGE",
            "bucketType": "number",
            "nullTreatedAsZero": True,
            "values": [
                {"rangeUpperBound": 90, "sourceDimensionValues": None, "label": "0-90d"},
                {"rangeUpperBound": 180, "sourceDimensionValues": None, "label": "91-180d"},
                {"rangeUpperBound": 365, "sourceDimensionValues": None, "label": "181-365d"},
                {"rangeUpperBound": 730, "sourceDimensionValues": None, "label": "1-2yr"},
                {"rangeUpperBound": None, "sourceDimensionValues": None, "label": "2yr+"},
            ],
        }
    ],
}


def _build(rpt: dict[str, Any]) -> dict[str, Any]:
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
        "groupingsAcross": [
            {"name": g["name"], "sortOrder": g.get("sortOrder", "Asc")}
            for g in rpt.get("groupingsAcross", [])
        ],
        "reportFilters": [*rpt.get("filters", []), *rpt.get("exclusion", [])],
        "standardDateFilter": rpt["standardDateFilter"],
        "buckets": rpt.get("buckets", []),
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

    print("[1/2] Build / update Pipeline Age by Rep matrix")
    if args.dry_run:
        import json

        with open("/tmp/pipeline_age_by_rep_body.json", "w") as f:
            json.dump(_build(REPORT), f, indent=2)
        print("  [dry-run] -> /tmp/pipeline_age_by_rep_body.json")
        return 0

    rid = _find_or_create_report(REPORT, _build, token, instance, api_base)
    print(f"  -> {rid}")
    print(f"  view: https://simcorp.lightning.force.com/lightning/r/Report/{rid}/view")

    print("\n[2/2] Top 10 reps by total open ARR — age distribution")
    run = _api(
        "GET",
        f"{api_base}/analytics/reports/{rid}?includeDetails=false",
        token,
        instance,
    )
    fact = run.get("factMap", {})
    gd = run.get("groupingsDown", {}).get("groupings", [])
    ga = run.get("groupingsAcross", {}).get("groupings", [])
    type_labels = [g.get("label") for g in ga]

    rows = []
    for g in gd:
        key = g.get("key")
        rep = g.get("label", "?")
        tot_arr = fact.get(f"{key}!T", {}).get("aggregates", [{}])[0].get("value", 0)
        cells = []
        for ag in ga:
            ak = ag.get("key")
            cell = fact.get(f"{key}!{ak}", {}).get("aggregates", [])
            arr = cell[0].get("value", 0) if len(cell) > 0 else 0
            cells.append(arr)
        rows.append((tot_arr, rep, cells))
    rows.sort(reverse=True)
    print(
        f"  {'Rep':35s}", " | ".join(f"{(t or 'null')[:10]:>10s}" for t in type_labels), " | TOTAL"
    )
    for tot, rep, cells in rows[:10]:
        band_strs = " | ".join(f"{c / 1e6:>10.1f}" if c else "         ·" for c in cells)
        print(f"  {rep[:35]:35s} {band_strs} | {tot / 1e6:>5.1f}M")
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
