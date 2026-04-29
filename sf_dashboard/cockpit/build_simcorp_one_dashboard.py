"""Build a "SimCorp One — Product Pipeline" dashboard in Andre's folder.

Greenfield: no SimCorp-One-themed reports or dashboards live in Andre's
folder today. This script creates 4 reports on the standard
`OpportunityProduct` report type, then assembles a dashboard around them.

Widgets (12-col grid):
  - r0,c0 (6x8) Funnel: Standard Platform pipeline by Stage
  - r0,c6 (6x8) Tabular: Top SimCorp One deals
  - r8,c0 (8x8) Bar:     Top products in open Land+Expand pipe (module mix)
  - r8,c8 (4x8) Donut:   Standard Platform Land vs Expand mix

Run: `python3 -m sf_dashboard.cockpit.build_simcorp_one_dashboard`.
Idempotent — skips creation if reports/dashboard with the canonical
DeveloperName already exist.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from typing import Any

import requests

API_VERSION = "v66.0"

# Folder layout (verified 2026-04-29 via Folder SOQL):
#   - Dashboard folder "Andre"                 -> 00lTb000006OCRBIA4
#   - Report folder    "Sales Ops Commercial Health" -> 00lTb000006hxm9IAA
# apro@simcorp.com can write to both. The "Andre" folder is dashboards-only.
ANDRE_DASHBOARD_FOLDER_ID = "00lTb000006OCRBIA4"
SALES_OPS_REPORT_FOLDER_ID = "00lTb000006hxm9IAA"

# Standard SF reportType for opportunity-line-item analysis
RT_OPP_PRODUCT = {"label": "Opportunities with Products", "type": "OpportunityProduct"}

# Standard filters — open opps only. Removed `terr=all` because the cloned
# template carried a TerritoryGroup reference (00ND...) tied to its original
# owner that apro can't resolve, surfacing as
# "Invalid value specified: 00ND0000004B3l6.". Probability removed too.
STANDARD_FILTERS_OPEN = [
    {"name": "open", "value": "open"},
]

ARR = "Opportunity.APTS_Opportunity_ARR__c.CONVERT"
S_ARR = f"s!{ARR}"

# Reports to ensure
REPORTS = [
    {
        "key": "sp_pipeline",
        "developerName": "SC1_Standard_Platform_Pipeline_v1",
        "name": "SC1 · Standard Platform by Stage",
        "format": "SUMMARY",
        "groupingsDown": [
            {
                "name": "STAGE_NAME",
                "sortOrder": "Asc",
                "sortAggregate": None,
            }
        ],
        "groupingsAcross": [],
        "aggregates": [S_ARR, "RowCount"],
        "detailColumns": [
            "ACCOUNT_NAME",
            "OPPORTUNITY_NAME",
            "FULL_NAME",
            "CLOSE_DATE",
            ARR,
        ],
        "reportFilters": [
            {
                "column": "PRODUCT_NAME",
                "operator": "equals",
                "value": "Standard Platform",
                "filterType": "fieldValue",
                "isRunPageEditable": True,
            },
        ],
    },
    {
        "key": "sp_top_deals",
        "developerName": "SC1_Top_Standard_Platform_Deals_v1",
        "name": "SC1 · Top Standard Platform Deals",
        "format": "TABULAR",
        "groupingsDown": [],
        "groupingsAcross": [],
        "aggregates": [S_ARR, "RowCount"],
        "detailColumns": [
            "ACCOUNT_NAME",
            "OPPORTUNITY_NAME",
            "FULL_NAME",
            "CLOSE_DATE",
            ARR,
        ],
        "sortBy": [{"sortColumn": ARR, "sortOrder": "Desc"}],
        "reportFilters": [
            {
                "column": "PRODUCT_NAME",
                "operator": "equals",
                "value": "Standard Platform",
                "filterType": "fieldValue",
                "isRunPageEditable": True,
            },
        ],
    },
    {
        "key": "module_mix",
        "developerName": "SC1_Module_Mix_Open_LE_v1",
        "name": "SC1 · Module Mix Open L+E",
        "format": "SUMMARY",
        "groupingsDown": [
            {
                "name": "PRODUCT_NAME",
                "sortOrder": "Asc",
                "sortAggregate": None,
            }
        ],
        "groupingsAcross": [],
        "aggregates": [S_ARR, "RowCount"],
        "detailColumns": ["ACCOUNT_NAME", "OPPORTUNITY_NAME", "STAGE_NAME", ARR],
        # No filter — show all products in open pipe. Dashboard widget
        # maxRows=15 surfaces top by occurrence. If "Standard Support" or
        # "Users - Full Access" top the chart that's its own signal
        # (services + license attach rate). Multi-value `notEqual` was
        # rejected as JSON_PARSER_ERROR.
        "reportFilters": [],
    },
    {
        "key": "sp_by_unit",
        "developerName": "SC1_SP_By_Account_Unit_v1",
        "name": "SC1 · SP by Account Unit Group",
        "format": "SUMMARY",
        "groupingsDown": [
            {
                "name": "Opportunity.Account_Unit_Group__c",
                "sortOrder": "Asc",
                "sortAggregate": None,
            }
        ],
        "groupingsAcross": [],
        "aggregates": [S_ARR, "RowCount"],
        "detailColumns": [
            "ACCOUNT_NAME",
            "OPPORTUNITY_NAME",
            "FULL_NAME",
            "CLOSE_DATE",
            ARR,
        ],
        "reportFilters": [
            {
                "column": "PRODUCT_NAME",
                "operator": "equals",
                "value": "Standard Platform",
                "filterType": "fieldValue",
                "isRunPageEditable": True,
            },
        ],
    },
]


def _sf_session() -> tuple[str, str]:
    out = subprocess.run(
        ["sf", "org", "display", "--target-org", "preprod", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    d = json.loads(out.stdout)["result"]
    return d["accessToken"], d["instanceUrl"]


def _find_report_by_devname(instance: str, headers: dict, dev_name: str) -> str | None:
    soql = f"SELECT Id FROM Report WHERE DeveloperName = '{dev_name}' LIMIT 1"
    r = requests.get(
        f"{instance}/services/data/{API_VERSION}/query",
        headers=headers,
        params={"q": soql},
        timeout=30,
    )
    r.raise_for_status()
    recs = r.json().get("records") or []
    return recs[0]["Id"] if recs else None


def _create_report(instance: str, headers: dict, spec: dict[str, Any]) -> str:
    """Direct POST — armed with the schema knowledge we earned from a
    failed clone-and-PATCH attempt. The cloned template carries an
    inaccessible TerritoryGroup ID (00ND...) that PATCH preserves
    server-side regardless of how we null it client-side, so we sidestep
    the clone path entirely. Build the body from scratch with only
    fields we know are valid.
    """
    body = {
        "reportMetadata": {
            "name": spec["name"],
            "reportType": RT_OPP_PRODUCT,
            "reportFormat": spec["format"],
            "folderId": SALES_OPS_REPORT_FOLDER_ID,
            "groupingsDown": spec.get("groupingsDown") or [],
            "groupingsAcross": [],
            "aggregates": spec.get("aggregates") or [],
            "detailColumns": spec.get("detailColumns") or [],
            "reportFilters": spec.get("reportFilters") or [],
            "standardFilters": STANDARD_FILTERS_OPEN,
            "scope": "organization",
            "showGrandTotal": True,
            "showSubtotals": True,
        }
    }
    if spec.get("sortBy"):
        body["reportMetadata"]["sortBy"] = spec["sortBy"]
    r = requests.post(
        f"{instance}/services/data/{API_VERSION}/analytics/reports",
        headers=headers,
        json=body,
        timeout=60,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"POST {spec['name']} -> {r.status_code}: {r.text[:1500]}")
    rid = r.json()["reportMetadata"]["id"]
    # PATCH developerName (POST doesn't accept it)
    p = requests.patch(
        f"{instance}/services/data/{API_VERSION}/analytics/reports/{rid}",
        headers=headers,
        json={"reportMetadata": {"developerName": spec["developerName"]}},
        timeout=30,
    )
    if p.status_code not in (200, 201):
        print(f"  WARN: PATCH developerName for {spec['name']} -> {p.status_code}: {p.text[:300]}")
    return rid


def _ensure_reports(instance: str, headers: dict) -> dict[str, str]:
    out = {}
    for spec in REPORTS:
        existing = _find_report_by_devname(instance, headers, spec["developerName"])
        if existing:
            print(f"  [skip] {spec['developerName']} -> {existing}")
            out[spec["key"]] = existing
            continue
        print(f"  [create] {spec['name']!r}")
        rid = _create_report(instance, headers, spec)
        print(f"           -> {rid}")
        out[spec["key"]] = rid
    return out


def _build_dashboard(instance: str, headers: dict, ids: dict[str, str]) -> str:
    # Skip if dashboard with our title already exists in Andre's folder.
    # SF Dashboard PATCH does not honor `developerName` overrides — the
    # value gets auto-generated on clone and is read-only thereafter —
    # so we de-dup by Title + FolderId.
    soql = (
        "SELECT Id FROM Dashboard WHERE Title = 'SimCorp One - Product Pipeline' "
        f"AND FolderId = '{ANDRE_DASHBOARD_FOLDER_ID}' LIMIT 1"
    )
    r = requests.get(
        f"{instance}/services/data/{API_VERSION}/query",
        headers=headers,
        params={"q": soql},
        timeout=30,
    )
    r.raise_for_status()
    existing = r.json().get("records") or []
    if existing:
        return existing[0]["Id"]

    # Clone a known-good dashboard for the metadata skeleton, then swap
    # reportIds in place. Direct POST + hand-built components hit
    # JSON_PARSER_ERROR. Template: "Sales Ops — Commercial Health &
    # Governance" — gridLayout=True, has Funnel + Bar + Donut + Metric +
    # FlexTable so any of our 4 SC1 reports map onto a known-good slot.
    clone_template = "01ZTb00000FxX2YMAV"
    c = requests.post(
        f"{instance}/services/data/{API_VERSION}/analytics/dashboards?cloneId={clone_template}",
        headers=headers,
        json={
            "name": "SimCorp One - Product Pipeline",
            "folderId": ANDRE_DASHBOARD_FOLDER_ID,
        },
        timeout=60,
    )
    if c.status_code not in (200, 201):
        raise RuntimeError(f"CLONE dashboard -> {c.status_code}: {c.text[:1500]}")
    did = c.json()["id"]

    # GET cloned describe, replace components + layout, PATCH back
    g = requests.get(
        f"{instance}/services/data/{API_VERSION}/analytics/dashboards/{did}/describe",
        headers=headers,
        timeout=30,
    )
    g.raise_for_status()
    md = copy.deepcopy(g.json())
    for ro in (
        "id",
        "lastModifiedDate",
        "canChangeRunningUser",
        "canUseStickyFilter",
        "owner",
        "folderName",  # read-only, derived from folderId
        "flexTableImplementation",
        "maxFilterOptions",
        "chartTheme",
        "colorPalette",
    ):
        md.pop(ro, None)

    md["name"] = "SimCorp One - Product Pipeline"
    md["developerName"] = "SC1_Product_Pipeline_v1"
    md["description"] = (
        "SimCorp One product-mix analysis. Standard Platform pipeline by stage, "
        "top SP-attached deals, module mix in open pipeline, and SP by Account "
        "Unit Group. Built on OpportunityProduct reportType."
    )
    md["folderId"] = ANDRE_DASHBOARD_FOLDER_ID

    # Clone-and-swap-reportId pattern: hand-built component shapes hit
    # JSON_PARSER_ERROR on PATCH (Funnel/Donut/FlexTable visualizationProperties
    # don't match SF's expected schema). Take the cloned dashboard's existing
    # components, swap reportIds to our SC1 reports, override headers/titles,
    # truncate to 4. The cloned shapes are known-good so PATCH accepts them.
    cloned_components = md["components"]

    # Map our 4 reports onto the first 4 components of the cloned dash. We
    # pick component indices that already use viz types compatible with our
    # data: index 0 (Bar/Column for stage breakdown), 2 (Bar for top deals
    # — flex), 3 (Bar for product mix), 11 (Metric for split — closest to
    # donut). Override header/title/reportId, leave shapes alone.
    # Cockpit component types (clone source 01ZTb00000FxX2YMAV):
    #   [1] Pipeline by Stage = Funnel (6x8)
    #   [5] FY26 Open Pipeline = Metric (3x4)
    #   [4] Stage Stickiness   = Bar (6x8)
    #   [9] Open Pipeline by Motion = Donut (4x8)
    # Subtitle cap is 40 chars per SF schema. Drop sp_top_deals widget —
    # its TABULAR report needs Dashboard Settings (row-limit) that we can
    # only set via UI, not REST. Use the sp_pipeline report twice: once
    # as Funnel (by stage), once as Metric (grand total ARR). Same drill,
    # different lens.
    target_swaps = [
        # (cloned_idx, our_report_key, header, subtitle (<=40 chars), layout)
        (
            1,  # cockpit "Pipeline by Stage" Funnel
            "sp_pipeline",
            "Standard Platform · Pipeline by Stage",
            "Open SP-attached opp ARR by stage",
            {"row": 0, "column": 0, "rowspan": 8, "colspan": 6},
        ),
        (
            5,  # cockpit "FY26 Open Pipeline" Metric
            "sp_pipeline",
            "SimCorp One · Total Open ARR",
            "Sum of SP-attached open pipe",
            {"row": 0, "column": 6, "rowspan": 4, "colspan": 6},
        ),
        (
            4,  # cockpit "Stage Stickiness" Bar
            "module_mix",
            "Module Mix · Open Pipe",
            "Top product line items in open pipe",
            {"row": 4, "column": 6, "rowspan": 4, "colspan": 6},
        ),
        (
            9,  # cockpit "Open Pipeline by Motion" Donut
            "sp_by_unit",
            "SimCorp One · by Account Unit",
            "Geographic split of SP open pipeline",
            {"row": 8, "column": 0, "rowspan": 8, "colspan": 12},
        ),
    ]
    new_components = []
    new_layout = []
    for clone_idx, key, header, subtitle, layout in target_swaps:
        comp = copy.deepcopy(cloned_components[clone_idx])
        comp["reportId"] = ids[key]
        comp["header"] = header
        comp["title"] = subtitle
        if "drillUrl" in comp.get("properties", {}):
            comp["properties"]["drillUrl"] = f"/lightning/r/Report/{ids[key]}/view"
        new_components.append(comp)
        new_layout.append(layout)

    md["components"] = new_components
    md["layout"]["components"] = new_layout
    md["filters"] = []
    # runningUser came back as a {displayName, id} dict from describe; PATCH
    # rejects that shape. Either send None for "current viewing user" semantics
    # or just the ID string. None is safer.
    md["runningUser"] = None

    p = requests.patch(
        f"{instance}/services/data/{API_VERSION}/analytics/dashboards/{did}",
        headers=headers,
        json=md,
        timeout=60,
    )
    if p.status_code not in (200, 201):
        import os
        import tempfile

        dump = os.path.join(tempfile.gettempdir(), "sc1_dash_body.json")
        with open(dump, "w") as f:
            json.dump(md, f, indent=2)
        print(f"  DEBUG: dashboard PATCH body keys -> {sorted(md.keys())}")
        print(f"  DEBUG: body dumped to {dump}")
        raise RuntimeError(f"PATCH dashboard {did} -> {p.status_code}: {p.text[:1500]}")
    return did


def main() -> int:
    token, instance = _sf_session()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print("[1/3] Ensure 4 reports exist:")
    ids = _ensure_reports(instance, headers)

    print("\n[2/3] Build dashboard:")
    did = _build_dashboard(instance, headers, ids)

    view = instance.replace(".my.salesforce.com", ".lightning.force.com")
    print(f"\n[3/3] Done. View: {view}/lightning/r/Dashboard/{did}/view")
    return 0


if __name__ == "__main__":
    sys.exit(main())
