#!/usr/bin/env python3
"""
Add Approval SLA Breach Metric widget to Sales Ops Cockpit.

Tracks open opportunities submitted for Commercial Approval (Stage 20)
that have been waiting >5 days. Live as of 2026-04-29: 7 opps, EUR 60.3M
ARR frozen at the gate (87% of all currently-pending Stage-20 reviews
are >10 days old). This is the single most actionable Deal-Desk signal
on the cockpit.

Drops the `Dec 31 Placeholders` widget — the daily brief alerts on
those, so the dashboard tile is redundant.

Atomic, idempotent. Mirrors the patterns from `add_churn_widget.py`.
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

# Drop "Dec 31 Placeholders" — daily brief covers it, dashboard is redundant.
DROP_REPORT_ID = "00OTb000008mv2bMAA"

SLA_REPORT: dict[str, Any] = {
    "developerName": "Cockpit_Approval_SLA_Breach_v3",
    "name": "Cockpit · Approval SLA Breach",
    "header": "Approval SLA Breach (>5d)",
    "metric_label": "ARR stuck at Commercial Approval",
    "reportFormat": "SUMMARY",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "Opportunity.APTS_Opportunity_ARR__c",
        "Opportunity.Submit_for_Stage_20_Review_Date__c",
    ],
    "groupingsDown": [
        # Group by owner so the drill view shows who's blocked.
        {"name": "FULL_NAME", "sortOrder": "Asc"},
    ],
    "aggregates": [
        "s!Opportunity.APTS_Opportunity_ARR__c",
        "RowCount",
    ],
    "filters": [
        {"column": "CLOSED", "operator": "equals", "value": "False"},
        {
            "column": "Opportunity.Submit_for_Stage_20_Review__c",
            "operator": "equals",
            "value": "1",
        },
        {
            "column": "Opportunity.Stage_20_Approval__c",
            "operator": "equals",
            "value": "0",
        },
        # Submitted >5 days ago = SLA breach. SF Reports interprets
        # `LAST_N_DAYS:5` with `lessThan` as "before 5 days ago",
        # i.e. older than the SLA window.
        {
            "column": "Opportunity.Submit_for_Stage_20_Review_Date__c",
            "operator": "lessThan",
            "value": "LAST_N_DAYS:5",
        },
    ],
    "exclusion": EXCLUDE_OPP_CRITERIA,
    "standardDateFilter": {
        "column": "Opportunity.Submit_for_Stage_20_Review_Date__c",
        "durationValue": "CUSTOM",
        "startDate": "2000-01-01",
        "endDate": "2099-12-31",
    },
}

SLA_SLOT = (19, 0, 3, 3)  # Dec 31 Placeholders' old position


def _build_sla_body(rpt: dict[str, Any]) -> dict[str, Any]:
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

    print("[1/4] Build / update Approval SLA Breach report")
    report_id = _find_or_create_report(SLA_REPORT, _build_sla_body, token, instance, api_base)
    print(f"  -> {report_id}")

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

    print("\n[3/4] Drop Dec 31 Placeholders, add Approval SLA Breach Metric")
    keep_idxs = [i for i, c in enumerate(components) if c.get("reportId") != DROP_REPORT_ID]
    components = [components[i] for i in keep_idxs]
    layout_components = [layout_components[i] for i in keep_idxs]
    print(f"  after drop: {len(components)} widgets")

    if any(c.get("reportId") == report_id for c in components):
        print("  keep Approval SLA Breach Metric already present")
    else:
        print(f"  add  Approval SLA Breach Metric -> {report_id}")
        components.append(
            _new_metric_component(
                report_id,
                SLA_REPORT["header"],
                SLA_REPORT["metric_label"],
                severity="critical",
            )
        )
        layout_components.append(
            {
                "row": SLA_SLOT[0],
                "column": SLA_SLOT[1],
                "rowspan": SLA_SLOT[2],
                "colspan": SLA_SLOT[3],
            }
        )

    asset_rid_set: set[str] = set()
    for comp in components:
        rid = comp.get("reportId") or ""
        cols = _filter_columns_for(rid, asset_rid_set)
        comp.setdefault("properties", {})["filterColumns"] = cols

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
        out = "/tmp/cockpit_sla_widget_body.json"
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

    print("\n[verify] re-GET dashboard")
    verify = _api(
        "GET",
        f"{api_base}/analytics/dashboards/{DASHBOARD_ID}/describe",
        token,
        instance,
    )
    n = len(verify["components"])
    rid_set = {c.get("reportId") for c in verify["components"]}
    sla_present = report_id in rid_set
    drop_gone = DROP_REPORT_ID not in rid_set
    print(f"  components:    {n}")
    print(f"  SLA present:   {sla_present}")
    print(f"  Dec31 dropped: {drop_gone}")

    print(
        "\n[done] https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxX2YMAV/view"
    )
    return 0 if sla_present and drop_gone else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as e:
        print(
            f"FATAL HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:1500]}",
            file=sys.stderr,
        )
        sys.exit(3)
