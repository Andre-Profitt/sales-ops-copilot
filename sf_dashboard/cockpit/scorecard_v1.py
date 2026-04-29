#!/usr/bin/env python3
"""
Build v1 of the Sales Rep Scorecard dashboard.

Ships the first scorecard widget: Task Volume by Owner × Type, last 30
days, filterable by Region. Lays the foundation; v2 adds Opportunity-side
scorecard columns (slipped, stale, approvals stuck, win rate).

Atomic, idempotent. Creates the report + dashboard on first run; second
run no-ops (re-PATCHes report metadata, re-uses dashboard id).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from rebuild_viz import (  # type: ignore[import-not-found]
    API_VERSION,
    _api,
    get_credentials,
)
from upgrade_v2 import REPORT_FOLDER_ID  # type: ignore[import-not-found]

# Service / integration accounts to exclude from rep volumes (bulk
# email automation, system users — not coachable individuals).
EXCLUDE_SERVICE_USERS = [
    "Salesforce Integrator",
]

# A separate dashboard folder for the Scorecard track. Reuse the
# Commercial Health folder for now; a `Sales Rep Scorecards` folder
# can be added later when the scorecard track ships v2 with more
# widgets.
DASHBOARD_FOLDER_ID = REPORT_FOLDER_ID

# Template Activity report to clone — direct POST of `Activity` reportType
# is rejected ("picklist not allowed") in this org but cloning an existing
# report bypasses validation. Picked an old throwaway report whose own
# data isn't important; we override every relevant field via PATCH.
ACTIVITY_TEMPLATE_REPORT_ID = "00O2o000007y6q7EAA"  # 2019 Open Tasks report

TASK_VOLUME_REPORT: dict[str, Any] = {
    # SF reserves deleted developerNames; bumping suffix to skip past
    # the prior orphans (Scorecard_Task_Volume_v1 was used by deleted
    # probe reports).
    "developerName": "Scorecard_Task_Volume_v1c",
    "name": "Scorecard · Task Volume by Type · 30d",
    "header": "Activity Volume by Owner × Type · last 30d",
    "reportFormat": "MATRIX",
    # NOTE: reportType is preserved from the cloned template. Sending it
    # in a PATCH body re-triggers the "picklist not allowed" error.
    "detailColumns": [
        "SUBJECT",
        "DUE_DATE",
        "ACCOUNT",
    ],
    "groupingsDown": [
        {"name": "ASSIGNED", "sortOrder": "Asc"},
    ],
    "groupingsAcross": [
        {"name": "TASK_TYPE", "sortOrder": "Asc"},
    ],
    "aggregates": ["RowCount"],
    "filters": [
        *[
            {"column": "ASSIGNED", "operator": "notEqual", "value": name}
            for name in EXCLUDE_SERVICE_USERS
        ],
    ],
    "exclusion": [],
    "standardDateFilter": {
        "column": "CREATED_DATE",
        "durationValue": "LAST_N_DAYS:30",
        "startDate": None,
        "endDate": None,
    },
    # CRITICAL: 2019 template has standardFilters [{closed:open}] which
    # excludes completed activities — that's why earlier probes saw only
    # ~2,200 of ~10,000 activities. Override to `closed: all` to capture
    # the full coaching surface (Outbound Emails, completed Calls, etc.).
    "standardFilters": [
        {"name": "closed", "value": "all"},
        {"name": "type", "value": "te"},
    ],
    "scope": "organization",
}

DASHBOARD_NAME = "Sales Rep Scorecard"
DASHBOARD_DEV_NAME = "Sales_Rep_Scorecard"


def _build_task_report_body(rpt: dict[str, Any]) -> dict[str, Any]:
    """PATCH body. Deliberately omits `reportType` — re-sending it in a
    PATCH triggers SF's picklist validator which rejects `Activity` for
    this org's REST surface (the value is preserved from the clone)."""
    rm: dict[str, Any] = {
        "name": rpt["name"],
        "description": "",
        "reportFormat": rpt["reportFormat"],
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
        "reportFilters": [
            *rpt.get("filters", []),
            *rpt.get("exclusion", []),
        ],
        "standardDateFilter": rpt["standardDateFilter"],
        "standardFilters": rpt.get("standardFilters", []),
        "scope": rpt.get("scope", "organization"),
        "folderId": REPORT_FOLDER_ID,
        "developerName": rpt["developerName"],
    }
    return {"reportMetadata": rm}


def _find_or_clone_and_patch_report(rpt, builder, token, instance, api_base, clone_template_id):
    """Idempotent: re-PATCH if name exists, else CLONE the template + PATCH.

    Direct POST of `Activity` reportType is rejected with a misleading
    picklist error in this org. CLONE bypasses that validator. The clone
    inherits the template's reportType, then PATCH (without reportType)
    overrides everything else.
    """
    name = rpt["name"].replace("'", "\\'")
    q = urllib.parse.quote(
        f"SELECT Id, Name FROM Report WHERE Name = '{name}' "
        f"AND FolderName = 'Sales Ops Commercial Health'"
    )
    res = _api("GET", f"{api_base}/query?q={q}", token, instance)
    if res.get("totalSize", 0) > 0:
        rid = res["records"][0]["Id"]
        print(f"  [keep] {rpt['name']!r} -> {rid}")
        body = builder(rpt)
        try:
            _api(
                "PATCH",
                f"{api_base}/analytics/reports/{rid}",
                token,
                instance,
                body=body,
            )
            print("         re-PATCHed metadata")
        except RuntimeError as e:
            print(f"         [WARN] re-PATCH failed: {str(e)[:200]}")
        return rid

    # Clone the template — gives us a fresh report with `Activity`
    # reportType already set, which we cannot otherwise create via REST.
    print(f"  [clone] template {clone_template_id} -> {rpt['name']!r}")
    clone_url = f"{instance}{api_base}/analytics/reports?cloneId={clone_template_id}"
    init_body = {
        "reportMetadata": {
            "name": rpt["name"],
            "developerName": rpt["developerName"],
        }
    }
    req = urllib.request.Request(
        clone_url,
        data=json.dumps(init_body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        cloned = json.loads(resp.read().decode())
    rid = cloned.get("reportMetadata", {}).get("id") or cloned.get("id") or ""
    if not rid:
        raise RuntimeError(f"clone of template {clone_template_id} returned no id")
    print(f"         cloned -> {rid}")

    # Now PATCH to apply our spec.
    body = builder(rpt)
    _api(
        "PATCH",
        f"{api_base}/analytics/reports/{rid}",
        token,
        instance,
        body=body,
    )
    print("         PATCHed to scorecard spec")
    return rid


def _find_or_create_dashboard(name, dev_name, folder_id, token, instance, api_base):
    """Look up dashboard by Name + Folder. Create stub if missing."""
    safe = name.replace("'", "\\'")
    q = urllib.parse.quote(
        f"SELECT Id FROM Dashboard WHERE Title = '{safe}' AND FolderId = '{folder_id}'"
    )
    res = _api("GET", f"{api_base}/query?q={q}", token, instance)
    if res.get("totalSize", 0) > 0:
        did = res["records"][0]["Id"]
        print(f"  [keep] dashboard {name!r} -> {did}")
        return did
    # Stub-create. No widgets — we PATCH below. Lightning grid layout
    # requires `numColumns` (12 = standard).
    body = {
        "name": name,
        "developerName": dev_name,
        "folderId": folder_id,
        "dashboardType": "SpecifiedUser",
        "components": [],
        "layout": {
            "components": [],
            "gridLayout": True,
            "numColumns": 12,
            "rowHeight": 36,
        },
    }
    print(f"  [new ] POST dashboard {name!r}")
    res = _api("POST", f"{api_base}/analytics/dashboards", token, instance, body=body)
    did = res.get("id") or ""
    if not did:
        raise RuntimeError(f"dashboard {name} create returned no id: {res}")
    print(f"         -> {did}")
    return did


def _new_matrix_component(report_id: str, header: str) -> dict[str, Any]:
    """Lightning Table component bound to the matrix report — shows
    Owner × Type heat-map. Lightning Tables degrade gracefully; if Bar
    is preferred, change visualizationType to 'StackedBar'."""
    return {
        "reportId": report_id,
        "header": header,
        "title": None,
        "footer": None,
        "type": "Report",
        "properties": {
            "visualizationType": "LightningTable",
            "drillUrl": f"/lightning/r/Report/{report_id}/view",
            "filterColumns": [],
            "autoSelectColumns": True,
            "useReportChart": False,
            "reportFormat": "MATRIX",
            "groupings": [
                {
                    "name": "Activity.Owner.Name",
                    "sortAggregate": None,
                    "sortOrder": None,
                },
                {
                    "name": "Activity.Activity_Type__c",
                    "sortAggregate": None,
                    "sortOrder": None,
                },
            ],
            "aggregates": [{"name": "RowCount"}],
            "maxRows": 50,
            "visualizationProperties": {
                "displayUnits": "auto",
                "decimalPrecision": 0,
            },
        },
    }


def _build_region_filter() -> dict[str, Any]:
    """Top-level dashboard filter on Account.Region__c. Reachable via
    Task.AccountId → Account.Region__c (verified 2026-04-29)."""
    return {
        "name": "Region",
        "dataType": "picklist",
        "errorMessage": None,
        "options": [
            {"alias": v, "operation": "equals", "value": v, "endValue": None, "startValue": None}
            for v in [
                "APAC",
                "Central Europe",
                "Middle East & Africa",
                "North America",
                "Northern Europe",
                "Southwestern Europe",
                "United Kingdom & Ireland",
            ]
        ],
        "selectedOption": None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--dashboard-id",
        default=None,
        help="Existing dashboard ID to wrap the report into. If omitted, "
        "report-only mode (the dashboard create endpoint returns 403 for "
        "this org's user — admin must create the stub dashboard "
        "manually then pass its ID here).",
    )
    args = ap.parse_args()

    creds = get_credentials()
    token, instance = creds["access_token"], creds["instance_url"]
    api_base = f"/services/data/v{API_VERSION}"

    print("[1/N] Build / update Task Volume report (clone-and-patch pattern)")
    report_id = _find_or_clone_and_patch_report(
        TASK_VOLUME_REPORT,
        _build_task_report_body,
        token,
        instance,
        api_base,
        ACTIVITY_TEMPLATE_REPORT_ID,
    )
    print(f"  -> {report_id}")
    print(f"  view: https://simcorp.lightning.force.com/lightning/r/Report/{report_id}/view")

    if not args.dashboard_id:
        print(
            "\n[done] Report-only mode (no --dashboard-id provided). The "
            "dashboard stub must be created manually in Lightning UI, then "
            "re-run with --dashboard-id <id> to wire the widget into it."
        )
        return 0

    dashboard_id = args.dashboard_id
    print(f"\n[2/N] Wiring widget into existing dashboard {dashboard_id}")

    print("\n[3/4] GET dashboard describe")
    describe = _api(
        "GET",
        f"{api_base}/analytics/dashboards/{dashboard_id}/describe",
        token,
        instance,
    )
    components: list[dict[str, Any]] = list(describe.get("components") or [])
    layout_components: list[dict[str, Any]] = list(
        (describe.get("layout") or {}).get("components") or []
    )
    print(f"  current widget count: {len(components)}")

    if any(c.get("reportId") == report_id for c in components):
        print("  keep Task Volume widget already present")
    else:
        print(f"  add  Task Volume Matrix -> {report_id}")
        components.append(
            _new_matrix_component(
                report_id,
                TASK_VOLUME_REPORT["header"],
            )
        )
        layout_components.append({"row": 0, "column": 0, "rowspan": 8, "colspan": 12})

    new_layout = json.loads(json.dumps(describe.get("layout") or {}))
    new_layout["components"] = layout_components
    new_layout.setdefault("gridLayout", True)

    body: dict[str, Any] = {
        "name": describe.get("name") or DASHBOARD_NAME,
        "description": describe.get("description") or "",
        "folderId": describe.get("folderId") or DASHBOARD_FOLDER_ID,
        "dashboardType": describe.get("dashboardType") or "SpecifiedUser",
        "runningUser": describe.get("runningUser"),
        "chartTheme": describe.get("chartTheme"),
        "colorPalette": describe.get("colorPalette"),
        "components": components,
        "layout": new_layout,
        "filters": [_build_region_filter()],
    }

    print(f"\n[4/4] PATCH dashboard: {len(components)} widgets, 1 filter")
    if args.dry_run:
        out = "/tmp/scorecard_v1_body.json"
        with open(out, "w") as f:
            json.dump(body, f, indent=2)
        print(f"  [dry-run] -> {out}")
        return 0

    try:
        _api(
            "PATCH",
            f"{api_base}/analytics/dashboards/{dashboard_id}",
            token,
            instance,
            body=body,
        )
        print("  [OK] PATCH succeeded")
    except RuntimeError as e:
        msg = str(e)
        print(f"  [FAIL] {msg[:600]}", file=sys.stderr)
        body.pop("filters", None)
        try:
            _api(
                "PATCH",
                f"{api_base}/analytics/dashboards/{dashboard_id}",
                token,
                instance,
                body=body,
            )
            print("  [OK] PATCH succeeded WITHOUT filters")
        except RuntimeError as e2:
            print(f"  [FAIL2] {str(e2)[:600]}", file=sys.stderr)
            return 2

    print(f"\n[done] https://simcorp.lightning.force.com/lightning/r/Dashboard/{dashboard_id}/view")
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
