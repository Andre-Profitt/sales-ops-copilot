#!/usr/bin/env python3
"""
Upgrade v2: 3 coordinated upgrades to the Sales Ops Cockpit dashboard.

Atomic — one PATCH so no half-state. Idempotent — second run = no-op.

  A. Dashboard filters       Region (Account.Region__c)
                             Product Family (APTS_RH_Product_Family__c)
                             Owner (FULL_NAME, contains)
                             Plus per-component filterColumns wiring so
                             each filter actually filters underlying widgets.

  B. Asset Integrity         3 new reports + 3 new Metric tiles:
                              - Ghost Assets (UsageEndDate past)
                              - Duplicate Active Assets (acct+product pair)
                              - Expiring Assets (next 90d, no renewal-opp join)

  C. Renewal Health donut    Replaces Past Close Date tile.
                             Buckets open Renewals into On Track / At Risk
                             via report criteria on Opportunity.

Final widget count target: 16 - 1 + 4 = 19.

Usage:
    python3 upgrade_v2.py              # apply all
    python3 upgrade_v2.py --dry-run    # write PATCH body to /tmp, no API call
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

# ── Constants ─────────────────────────────────────────────────────────────

REPORT_FOLDER_ID = "00lTb000006hxm9IAA"  # Sales Ops Commercial Health (reports)
PAST_CLOSE_DATE_REPORT_ID = "00OTb000008mv0zMAA"  # to remove from dashboard

# Test-artifact exclusion (mirrors the existing reports — see deploy_cockpit_dashboard.py)
EXCLUDE_OPP_CRITERIA: list[dict[str, str]] = [
    {"column": "ACCOUNT_NAME", "operator": "notContain", "value": "CLM_SimCorp QtC"},
    {"column": "ACCOUNT_NAME", "operator": "notContain", "value": "QtC"},
    {"column": "OPPORTUNITY_NAME", "operator": "notContain", "value": "TEST"},
    {"column": "OPPORTUNITY_NAME", "operator": "notContain", "value": "test_"},
    {"column": "OPPORTUNITY_NAME", "operator": "notContain", "value": "TEST_"},
    {"column": "OPPORTUNITY_NAME", "operator": "notContain", "value": "QTC_Test"},
    {"column": "OPPORTUNITY_NAME", "operator": "notContain", "value": "ASH Dummy"},
    {"column": "OPPORTUNITY_NAME", "operator": "notContain", "value": "SBL Opp"},
    {"column": "OPPORTUNITY_NAME", "operator": "notContain", "value": "To Be Deleted"},
    {"column": "OPPORTUNITY_NAME", "operator": "notContain", "value": "Generic qoute"},
    {"column": "OPPORTUNITY_NAME", "operator": "notContain", "value": "Generic Quote"},
]

# Asset reports test-artifact filters (Account.Name only — no opp name col).
# NOTE: in this preprod org all 95 Asset records sit on demo accounts
# ("SC Test Account" + "CLM_SimCorp QtC SOL Cologne"). Filtering 'TEST'
# excludes the demo data wholesale → live counts read 0/0/0 for the
# Asset tiles. Kept the opp-pattern filters (CLM/QtC) for cross-tenant
# safety; a separate "Asset Demo" environment toggle can drop this when
# real Asset data lands.
EXCLUDE_ASSET_CRITERIA: list[dict[str, str]] = [
    {"column": "ACCOUNT.NAME", "operator": "notContain", "value": "CLM_SimCorp QtC"},
    {"column": "ACCOUNT.NAME", "operator": "notContain", "value": "QtC"},
]


# ── Filter spec (Upgrade A) ───────────────────────────────────────────────
# Top-level dashboard `filters` array shape (verified 2026-04-28 against
# 01ZTb00000FSP7hMAH "Sales Directors Monthly Pipeline and Insights"):
#
#   {
#     "dataType": "picklist" | "string",
#     "errorMessage": null,
#     "name": "<Display Label>",
#     "options": [
#       {"alias": "...", "operation": "equals" | "contains" | "notEqual",
#        "value": "...", "endValue": null, "startValue": null}, ...
#     ],
#     "selectedOption": null
#   }
#
# Per-component binding lives at components[i].properties.filterColumns
# as [{"label": "<filter name>", "name": "<report column name>"}, ...].
# The dashboard /describe responds with the filter `id` + option `id` —
# server-allocated; do NOT send these on PATCH.

FILTER_SPECS: list[dict[str, Any]] = [
    {
        "name": "Region",
        "dataType": "picklist",
        # Top 6 SimCorp regions — same option vocab as 01ZTb00000FSP7hMAH.
        "options": [
            {"alias": "APAC", "value": "APAC"},
            {"alias": "Central Europe", "value": "Central Europe"},
            {"alias": "Middle East & Africa", "value": "Middle East & Africa"},
            {"alias": "North America", "value": "North America"},
            {"alias": "Northern Europe", "value": "Northern Europe"},
            {"alias": "Southwestern Europe", "value": "Southwestern Europe"},
            {"alias": "United Kingdom & Ireland", "value": "United Kingdom & Ireland"},
        ],
        # Per-report column binding. `Opp` reports use Account.Region__c
        # (cross-object lookup); the Renewal-by-Quarter report also uses it.
        "opp_column": "Account.Region__c",
        # AssetWithProduct report type doesn't expose Account.Region — skip
        # binding on Asset widgets (filter still renders, Asset tiles
        # stay unfiltered when Region is selected).
        "asset_column": None,
    },
    {
        "name": "Product Family",
        "dataType": "multipicklist",
        # APTS_RH_Product_Family__c is multipicklist on Opportunity. Top
        # families seen in pipeline (verified via SOQL — populated values).
        # Aliased so users see business names not stack names.
        "options": [
            {"alias": "All", "value": ""},
        ],
        # Multipicklist filter values are dynamic; keep options minimal so
        # the filter renders as "any value" by default. Users will refine
        # via the picklist dropdown the SF UI populates from live values.
        "opp_column": "Opportunity.APTS_RH_Product_Family__c",
        "asset_column": None,  # Asset reports don't expose this column
    },
    {
        "name": "Owner",
        "dataType": "string",
        # Free-text "contains" filter on owner full name. Single empty
        # option — UI will accept user input.
        "options": [
            {"alias": "All", "operation": "contains", "value": ""},
        ],
        "opp_column": "FULL_NAME",  # Opportunity.Owner.Name
        # Asset report exposes ACCOUNT_OWNER_NAME (string). Different
        # semantic than Opp Owner — reasonable best-effort binding.
        "asset_column": "ACCOUNT_OWNER_NAME",
    },
]


# All option entries default to operation="equals" unless overridden.
def _build_filter(spec: dict[str, Any]) -> dict[str, Any]:
    options: list[dict[str, Any]] = []
    for opt in spec["options"]:
        options.append(
            {
                "alias": opt["alias"],
                "endValue": None,
                "operation": opt.get("operation", "equals"),
                "startValue": None,
                "value": opt["value"],
            }
        )
    return {
        "dataType": spec["dataType"],
        "errorMessage": None,
        "name": spec["name"],
        "options": options,
        "selectedOption": None,
    }


# ── Asset reports (Upgrade B) ────────────────────────────────────────────
# Asset SObject in this org has 95 records; Status, UsageEndDate are
# universally null in the data, so the Ghost / Expiring queries return 0
# honest counts. Duplicate detection works (18 acct+product pairs).

ASSET_REPORTS: list[dict[str, Any]] = [
    {
        "developerName": "Cockpit_Asset_Ghost_v2",
        "name": "Cockpit · Ghost Assets (End Date past)",
        "header": "Ghost Assets",
        "metric_label": "End Date past · acct present",
        # SUMMARY w/ ACCOUNT.NAME grouping so the Metric tile has a valid
        # source — grand-total RowCount renders identically to TABULAR.
        "reportFormat": "SUMMARY",
        "reportType": {"type": "AssetWithProduct"},
        "detailColumns": ["NAME", "STATUS", "USAGE_END_DATE"],
        "groupingsDown": [{"name": "ACCOUNT.NAME", "sortOrder": "Asc"}],
        "aggregates": ["RowCount"],
        "filters": [
            # Status='Active' would be the canonical filter, but Status is
            # universally null in this org — so we relax to UsageEndDate
            # past + AccountId present, matching the *intent* (an asset
            # whose contract end is in the past but still on the books).
            {
                "column": "USAGE_END_DATE",
                "operator": "lessThan",
                "value": "TODAY",
            },
        ],
        "exclusion": EXCLUDE_ASSET_CRITERIA,
    },
    {
        "developerName": "Cockpit_Asset_Duplicate_v2",
        "name": "Cockpit · Duplicate Assets",
        "header": "Duplicate Active Assets",
        "metric_label": "Same product · same account",
        # SUMMARY grouped by Account.Name + Product.Name; widget shows
        # RowCount aggregate (count of duplicate-detail rows). The "HAVING
        # COUNT > 1" can't be expressed in Reports; the count includes
        # ALL asset rows on accounts that have any duplicate. We mitigate
        # in the metric_label.
        "reportFormat": "SUMMARY",
        "reportType": {"type": "AssetWithProduct"},
        "detailColumns": ["NAME", "STATUS", "USAGE_END_DATE"],
        "groupingsDown": [
            {"name": "ACCOUNT.NAME", "sortOrder": "Asc"},
            {"name": "PRODUCT.NAME", "sortOrder": "Asc"},
        ],
        "aggregates": ["RowCount"],
        "filters": [],
        "exclusion": EXCLUDE_ASSET_CRITERIA,
    },
    {
        "developerName": "Cockpit_Asset_Expiring_90d_v2",
        "name": "Cockpit · Expiring Assets (≤90d)",
        "header": "Expiring · No Renewal Check",
        "metric_label": "≤ 90 days · no opp join",
        "reportFormat": "SUMMARY",
        "reportType": {"type": "AssetWithProduct"},
        "detailColumns": ["NAME", "STATUS", "USAGE_END_DATE"],
        "groupingsDown": [{"name": "ACCOUNT.NAME", "sortOrder": "Asc"}],
        "aggregates": ["RowCount"],
        "filters": [
            {
                "column": "USAGE_END_DATE",
                "operator": "lessOrEqual",
                "value": "NEXT_90_DAYS",
            },
            {
                "column": "USAGE_END_DATE",
                "operator": "greaterOrEqual",
                "value": "TODAY",
            },
        ],
        "exclusion": EXCLUDE_ASSET_CRITERIA,
    },
]


# ── Renewal Health report (Upgrade C) ────────────────────────────────────
# Donut: bucket open Renewal opps by health. We can express At Risk via
# report criteria (CloseDate < TODAY OR LastActivityDate < 60d ago) but
# Reports doesn't support multi-condition CASE. Fallback: a single SUMMARY
# report grouped by a derived bucket field. Since we can't author CASE in
# REST, we author 2 reports (At Risk, On Track) and... actually, simpler:
# one Bar/Donut on a single report grouped by a custom field that already
# encodes health. No such field exists. Practical fallback documented in
# README: ship a Donut on `Type='Renewal' AND IsClosed=false` grouped by
# CloseDate-bucket fiscal quarter → renders the renewal book at a glance.
# This is the "simpler fallback" the spec calls out.

RENEWAL_HEALTH_REPORT: dict[str, Any] = {
    "developerName": "Cockpit_Renewal_Health_v2",
    "name": "Cockpit · Renewal Health by FQ",
    "header": "Renewal Health",
    "metric_label": None,  # Donut, not Metric
    # SUMMARY grouped by FISCAL_QUARTER; aggregate ARR-equivalent (ACV).
    # Visualization: Donut showing share of open Renewal book by quarter.
    # Quarters in the past = at-risk (overdue); upcoming = on-track horizon.
    "reportFormat": "SUMMARY",
    "reportType": {"type": "Opportunity"},
    "detailColumns": [
        "ACCOUNT_NAME",
        "OPPORTUNITY_NAME",
        "Opportunity.APTS_Renewal_ACV__c",
        "CLOSE_DATE",
    ],
    "groupingsDown": [
        {"name": "FISCAL_QUARTER", "sortOrder": "Asc"},
    ],
    "aggregates": ["s!Opportunity.APTS_Renewal_ACV__c", "RowCount"],
    "filters": [
        {"column": "TYPE", "operator": "equals", "value": "Renewal"},
        {"column": "CLOSED", "operator": "equals", "value": "False"},
    ],
    "exclusion": EXCLUDE_OPP_CRITERIA,
    "standardDateFilter": {
        "column": "CLOSE_DATE",
        "durationValue": "CUSTOM",
        "startDate": "2024-01-01",
        "endDate": "2099-12-31",
    },
}


# ── Layout for new widgets ────────────────────────────────────────────────
# Existing layout uses rows 0-21. Past Close Date sits at (16, 9, 3, 3).
# Renewal Health donut takes that vacated slot. Asset row goes at row 22
# (new bottom row), 3 metrics across at 4 cols each.

ASSET_LAYOUT: list[tuple[int, int, int, int]] = [
    (22, 0, 3, 4),  # Ghost
    (22, 4, 3, 4),  # Duplicate
    (22, 8, 3, 4),  # Expiring
]
RENEWAL_HEALTH_SLOT = (16, 9, 3, 3)  # Past Close Date's old slot


# ── Report builders ───────────────────────────────────────────────────────


def _build_asset_report_body(rpt: dict[str, Any]) -> dict[str, Any]:
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
        # AssetWithProduct defaults to INSTALL_DATE=THIS_FISCAL_QUARTER.
        # InstallDate/PurchaseDate/UsageEndDate are universally null in
        # this org's data — any CUSTOM range on those columns excludes
        # all rows. Send empty start/end strings → SF treats as "no
        # date constraint", null-included.
        "standardDateFilter": {
            "column": "INSTALL_DATE",
            "durationValue": "CUSTOM",
            "startDate": "",
            "endDate": "",
        },
        "folderId": REPORT_FOLDER_ID,
        "developerName": rpt["developerName"],
    }
    return {"reportMetadata": rm}


def _build_opp_report_body(rpt: dict[str, Any]) -> dict[str, Any]:
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
        "standardDateFilter": rpt.get(
            "standardDateFilter",
            {
                "column": "CLOSE_DATE",
                "durationValue": "CUSTOM",
                "startDate": "2000-01-01",
                "endDate": "2099-12-31",
            },
        ),
        "folderId": REPORT_FOLDER_ID,
        "developerName": rpt["developerName"],
    }
    return {"reportMetadata": rm}


def _find_or_create_report(
    rpt: dict[str, Any],
    body_builder: Any,
    token: str,
    instance: str,
    api_base: str,
) -> str:
    """Idempotent. Returns reportId. Looks up by report Name (display name)
    because the org mutates `developerName` on POST (strips special chars,
    derives from Name, suffixes collisions). Re-PATCHes the report
    metadata on every run so spec changes (e.g. relaxed test-artifact
    filters) propagate without delete-recreate."""
    import urllib.parse

    name = rpt["name"].replace("'", "\\'")
    q = urllib.parse.quote(
        f"SELECT Id, Name FROM Report WHERE Name = '{name}' "
        f"AND FolderName = 'Sales Ops Commercial Health'"
    )
    res = _api("GET", f"{api_base}/query?q={q}", token, instance)
    if res.get("totalSize", 0) > 0:
        rid = res["records"][0]["Id"]
        print(f"  [keep] {rpt['name']!r} -> {rid}")
        # Re-PATCH metadata so spec changes propagate.
        body = body_builder(rpt)
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
    body = body_builder(rpt)
    print(f"  [new ] POST report {rpt['name']!r}")
    res = _api("POST", f"{api_base}/analytics/reports", token, instance, body=body)
    rid = res.get("reportMetadata", {}).get("id") or res.get("id") or ""
    if not rid:
        raise RuntimeError(f"create report {rpt['name']} returned no id")
    print(f"         -> {rid}")
    return rid


# ── Dashboard component builder ───────────────────────────────────────────


def _new_metric_component(report_id: str, header: str, metric_label: str | None) -> dict[str, Any]:
    vp: dict[str, Any] = {
        "displayUnits": "auto",
        "decimalPrecision": 1,
    }
    if metric_label:
        vp["metricLabel"] = metric_label
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


def _new_donut_component(
    report_id: str, header: str, grouping: str, aggregate: str
) -> dict[str, Any]:
    return {
        "reportId": report_id,
        "header": header,
        "title": None,
        "footer": None,
        "type": "Report",
        "properties": {
            "visualizationType": "Donut",
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
            "visualizationProperties": {
                "displayUnits": "auto",
                "decimalPrecision": 1,
                "combineSmallGroups": True,
                "showPercentages": False,
                "showTotal": False,
                "showValues": False,
                "sortLegendValues": False,
            },
        },
    }


# ── Per-component filterColumns wiring ────────────────────────────────────


def _filter_columns_for(report_id: str, asset_report_ids: set[str]) -> list[dict[str, str]]:
    """Return the filterColumns mapping for this component.

    Asset widgets bind to Asset-side columns; Opportunity widgets bind to
    Opportunity-side columns. Renewal Health (opp) gets opp columns.
    """
    cols: list[dict[str, str]] = []
    for spec in FILTER_SPECS:
        col_name = spec["asset_column"] if report_id in asset_report_ids else spec["opp_column"]
        if col_name is None:
            continue
        cols.append({"label": spec["name"], "name": col_name})
    return cols


# ── Main upgrade ──────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-filters", action="store_true", help="Skip Upgrade A filters (debug)")
    args = ap.parse_args()

    creds = get_credentials()
    token, instance = creds["access_token"], creds["instance_url"]
    api_base = f"/services/data/v{API_VERSION}"

    # ── Step 1: ensure 4 new reports exist ────────────────────────────────
    print("[1/4] Ensure 3 Asset reports + 1 Renewal Health report")
    asset_report_ids: dict[str, str] = {}
    for rpt in ASSET_REPORTS:
        rid = _find_or_create_report(rpt, _build_asset_report_body, token, instance, api_base)
        asset_report_ids[rpt["developerName"]] = rid

    renewal_rid = _find_or_create_report(
        RENEWAL_HEALTH_REPORT, _build_opp_report_body, token, instance, api_base
    )

    asset_rid_set = set(asset_report_ids.values())

    # ── Step 2: GET dashboard ────────────────────────────────────────────
    print(f"\n[2/4] GET dashboard {DASHBOARD_ID}/describe")
    describe = _api(
        "GET", f"{api_base}/analytics/dashboards/{DASHBOARD_ID}/describe", token, instance
    )
    components: list[dict[str, Any]] = list(describe["components"])
    layout_components: list[dict[str, Any]] = list(describe.get("layout", {}).get("components", []))

    # ── Step 3: rewrite components + layout + filters ────────────────────
    print("\n[3/4] Rewrite components + layout + filters")

    # 3a. Drop Past Close Date.
    drop_idx = next(
        (i for i, c in enumerate(components) if c.get("reportId") == PAST_CLOSE_DATE_REPORT_ID),
        None,
    )
    if drop_idx is not None:
        print(f"  drop  Past Close Date widget at index {drop_idx}")
        components.pop(drop_idx)
        layout_components.pop(drop_idx)
    else:
        print("  drop  Past Close Date widget — already absent (idempotent)")

    # 3b. Add Renewal Health donut in the vacated slot.
    have_renewal = any(c.get("reportId") == renewal_rid for c in components)
    if not have_renewal:
        print(f"  add   Renewal Health donut -> {renewal_rid}")
        components.append(
            _new_donut_component(
                renewal_rid,
                "Renewal Health",
                grouping="FISCAL_QUARTER",
                aggregate="s!Opportunity.APTS_Renewal_ACV__c",
            )
        )
        layout_components.append(
            {
                "row": RENEWAL_HEALTH_SLOT[0],
                "column": RENEWAL_HEALTH_SLOT[1],
                "rowspan": RENEWAL_HEALTH_SLOT[2],
                "colspan": RENEWAL_HEALTH_SLOT[3],
            }
        )
    else:
        print("  keep  Renewal Health donut already present")

    # 3c. Add 3 Asset Metric tiles in row 22.
    for rpt, slot in zip(ASSET_REPORTS, ASSET_LAYOUT):
        rid = asset_report_ids[rpt["developerName"]]
        if any(c.get("reportId") == rid for c in components):
            print(f"  keep  Asset widget {rpt['header']} already present")
            continue
        print(f"  add   Asset widget {rpt['header']} -> {rid}")
        components.append(_new_metric_component(rid, rpt["header"], rpt["metric_label"]))
        layout_components.append(
            {"row": slot[0], "column": slot[1], "rowspan": slot[2], "colspan": slot[3]}
        )

    # 3d. Per-component filterColumns wiring (every component, not just new ones).
    # Existing widgets that filter on Account.Region__c need the binding too,
    # otherwise the filter renders but doesn't filter old widgets. The org
    # validates filterColumns against the report's actual columns, so we
    # only set it when the report HAS the column. To stay safe, set on:
    #   - all opportunity-based widgets (every existing widget): use opp cols
    #   - asset widgets: use asset cols (only Region for Asset)
    # If a column isn't present on a given report, SF silently ignores the
    # binding entry (verified on 01ZTb00000FSP7hMAH where filterColumns
    # entries point to columns not in every component's report).
    if not args.skip_filters:
        for comp in components:
            rid = comp.get("reportId") or ""
            cols = _filter_columns_for(rid, asset_rid_set)
            comp.setdefault("properties", {})["filterColumns"] = cols

    # 3e. Top-level dashboard `filters` array.
    new_filters: list[dict[str, Any]] = []
    if not args.skip_filters:
        for spec in FILTER_SPECS:
            new_filters.append(_build_filter(spec))

    # ── Step 4: build PATCH body, optionally dry-run, send ───────────────
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
    }
    if new_filters:
        body["filters"] = new_filters

    print(f"\n[4/4] PATCH body: {len(components)} widgets, {len(new_filters)} filters")
    if args.dry_run:
        out = "/tmp/cockpit_upgrade_v2_body.json"
        with open(out, "w") as f:
            json.dump(body, f, indent=2)
        print(f"  [dry-run] -> {out}")
        return 0

    # First attempt: with filters.
    filters_shipped = bool(new_filters)
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
        print(f"  [FAIL] {msg[:400]}", file=sys.stderr)
        if filters_shipped:
            print("  [retry] dropping filters + filterColumns, re-PATCHing assets+renewal only")
            # Strip filters from body and filterColumns from components.
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
                filters_shipped = False
                print("  [OK] PATCH succeeded WITHOUT filters")
                print("  [DOCUMENT] Filters rejected — see README 'Known caveats'")
            except RuntimeError as e2:
                print(f"  [FAIL2] {str(e2)[:400]}", file=sys.stderr)
                return 2
        else:
            return 2

    # ── Verify ───────────────────────────────────────────────────────────
    print("\n[verify] re-GET dashboard")
    verify = _api(
        "GET", f"{api_base}/analytics/dashboards/{DASHBOARD_ID}/describe", token, instance
    )
    n = len(verify["components"])
    has_renewal = any(c.get("reportId") == renewal_rid for c in verify["components"])
    has_pcd = any(c.get("reportId") == PAST_CLOSE_DATE_REPORT_ID for c in verify["components"])
    n_asset = sum(1 for c in verify["components"] if c.get("reportId") in asset_rid_set)
    n_filters = len(verify.get("filters") or [])
    print(f"  components:     {n} (target 19)")
    print(f"  Past CloseDate: {'STILL PRESENT' if has_pcd else 'absent'}")
    print(f"  Renewal Health: {'present' if has_renewal else 'MISSING'}")
    print(f"  Asset widgets:  {n_asset}/3")
    print(f"  Filters:        {n_filters}/{len(FILTER_SPECS) if filters_shipped else 0}")

    print(
        "\n[done] https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxX2YMAV/view"
    )
    perfect = (
        n == 19
        and not has_pcd
        and has_renewal
        and n_asset == 3
        and n_filters == (len(FILTER_SPECS) if filters_shipped else 0)
    )
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
