#!/usr/bin/env python3
"""
Add Churn Risk Metric widget to the Sales Ops Cockpit dashboard.

Atomic, idempotent:
  1. Build/update the `Cockpit · Churn Risk · Renewals` SUMMARY report
     (Opportunity, Type=Renewal, IsClosed=false, Account risk High|Medium,
     summed by APTS_Renewal_ACV__c grouped by risk tier).
  2. Drop `Duplicate Active Assets` widget from the dashboard (asset data
     in this preprod is demo-only — returns 0 in real terms; per-memory
     `feedback_cli_only_agents` and the v2 dashboard design doc).
  3. Add a new Metric tile bound to the Churn Risk report into the
     freed slot (row 22, col 4, 3x4) using severity=critical formatting.

Usage:
    python3 add_churn_widget.py --dry-run
    python3 add_churn_widget.py
"""

from __future__ import annotations

import argparse
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
    REPORT_FOLDER_ID,
    _filter_columns_for,
    _find_or_create_report,
)
from upgrade_v3 import _new_metric_component  # type: ignore[import-not-found]

# Widget to drop — asset data is demo-only in this preprod (per memory
# `feedback_no_python_builders`/`feedback_cli_only_agents` and the v2
# dashboard design doc — Duplicate Active Assets renders 0 in real terms).
DROP_REPORT_ID = "00OTb000008mwrVMAQ"

CHURN_REPORT: dict[str, Any] = {
    "developerName": "Cockpit_Churn_Risk_Renewals_v3",
    "name": "Cockpit · Churn Risk · Renewals",
    "header": "Churn Risk · Open Renewal ACV",
    "metric_label": "High+Med · open Renewal ACV",
    "reportFormat": "SUMMARY",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "Opportunity.APTS_Renewal_ACV__c",
        "CLOSE_DATE",
    ],
    "groupingsDown": [
        # Group by risk tier so the drill view buckets High vs Medium.
        {"name": "Account.Risk_of_Potential_Termination__c", "sortOrder": "Desc"},
    ],
    "aggregates": [
        "s!Opportunity.APTS_Renewal_ACV__c",
        "RowCount",
    ],
    "filters": [
        {"column": "TYPE", "operator": "equals", "value": "Renewal"},
        {"column": "CLOSED", "operator": "equals", "value": "False"},
        # SF report multi-value filter: comma-separated value with `equals`
        # operator behaves as IN. Verified pattern from existing cockpit
        # reports (e.g., `TYPE = "Land,Expand"`).
        {
            "column": "Account.Risk_of_Potential_Termination__c",
            "operator": "equals",
            "value": "High,Medium",
        },
    ],
    "exclusion": EXCLUDE_OPP_CRITERIA,
    "standardDateFilter": {
        "column": "CLOSE_DATE",
        "durationValue": "CUSTOM",
        "startDate": "2000-01-01",
        "endDate": "2099-12-31",
    },
}

CHURN_SLOT = (22, 4, 3, 4)  # Duplicate Active Assets's old position


def _build_churn_body(rpt: dict[str, Any]) -> dict[str, Any]:
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
        "reportFilters": [
            *rpt.get("filters", []),
            *rpt.get("exclusion", []),
        ],
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

    # 1. Build / update report
    print("[1/4] Build / update Churn Risk report")
    report_id = _find_or_create_report(CHURN_REPORT, _build_churn_body, token, instance, api_base)
    print(f"  -> {report_id}")

    # 2. GET current dashboard state
    print(f"\n[2/4] GET dashboard {DASHBOARD_ID}/describe")
    describe = _api(
        "GET",
        f"{api_base}/analytics/dashboards/{DASHBOARD_ID}/describe",
        token,
        instance,
    )
    components: list[dict[str, Any]] = list(describe["components"])
    layout_components: list[dict[str, Any]] = list(describe.get("layout", {}).get("components", []))
    print(f"  current widget count: {len(components)}")

    # 3. Drop Duplicate Active Assets, add Churn Risk Metric
    print("\n[3/4] Drop Duplicate Active Assets, add Churn Risk Metric")
    keep_idxs = [i for i, c in enumerate(components) if c.get("reportId") != DROP_REPORT_ID]
    components = [components[i] for i in keep_idxs]
    layout_components = [layout_components[i] for i in keep_idxs]
    print(f"  after drop: {len(components)} widgets")

    # Idempotent: skip add if Churn Risk widget already on the dashboard
    if any(c.get("reportId") == report_id for c in components):
        print("  keep Churn Risk Metric already present")
    else:
        print(f"  add  Churn Risk Metric -> {report_id}")
        components.append(
            _new_metric_component(
                report_id,
                CHURN_REPORT["header"],
                CHURN_REPORT["metric_label"],
                severity="critical",
            )
        )
        layout_components.append(
            {
                "row": CHURN_SLOT[0],
                "column": CHURN_SLOT[1],
                "rowspan": CHURN_SLOT[2],
                "colspan": CHURN_SLOT[3],
            }
        )

    # Re-apply per-component filterColumns (the new component needs Region
    # + Product Family bindings if available; Account.Region__c reaches via
    # the Account cross-object lookup which SF supports for Opportunity).
    asset_rid_set: set[str] = set()  # no asset components remain after drop
    for comp in components:
        rid = comp.get("reportId") or ""
        cols = _filter_columns_for(rid, asset_rid_set)
        comp.setdefault("properties", {})["filterColumns"] = cols

    # 4. PATCH dashboard
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
        "filters": list(describe.get("filters") or []),
    }

    print(f"\n[4/4] PATCH dashboard: {len(components)} widgets")
    if args.dry_run:
        out = "/tmp/cockpit_churn_widget_body.json"
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
        print("  [OK] PATCH succeeded")
    except RuntimeError as e:
        msg = str(e)
        print(f"  [FAIL] {msg[:600]}", file=sys.stderr)
        # Strip top-level filters (don't have a stable id) and per-component
        # filterColumns and retry — same fallback pattern as upgrade_v3.
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

    # Verify
    print("\n[verify] re-GET dashboard")
    verify = _api(
        "GET",
        f"{api_base}/analytics/dashboards/{DASHBOARD_ID}/describe",
        token,
        instance,
    )
    n = len(verify["components"])
    rid_set = {c.get("reportId") for c in verify["components"]}
    churn_present = report_id in rid_set
    drop_gone = DROP_REPORT_ID not in rid_set

    print(f"  components:        {n}")
    print(f"  churn present:     {churn_present}")
    print(f"  duplicate dropped: {drop_gone}")

    print(
        "\n[done] https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxX2YMAV/view"
    )
    return 0 if churn_present and drop_gone else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as e:
        print(
            f"FATAL HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:1500]}",
            file=sys.stderr,
        )
        sys.exit(3)
