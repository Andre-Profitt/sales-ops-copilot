"""Phase 6 — rebuild Sales Director Monthly dashboard widget layout.

PATCH `01ZTb00000FSP7hMAH` components:
  - Remove the empty-slot component (reportId=None)
  - Remove the duplicate Close Date Slipped YTD widget
  - Add 5 new components anchored on KPI/Audit reports:
      * Lost ARR This Q (KPI · 00OTb000008msSvMAI)
      * Pipeline ARR by Owner (KPI · 00OTb000008msPhMAI)
      * New Opps Last Month (KPI · 00OTb000008msW9MAI)
      * Stage 3+ This Month (KPI · 00OTb000008msZNMAY)
      * Stuck-Created Contracts (Audit · 00OTb000008ms7xMAA — non-Opp surface)
  - Update layout grid

Per Phase 2.8 memory: dashboard COMPONENT PATCH works via Analytics API.
Dashboard FILTERS and canChangeRunningUser are Lightning-UI-only; this script
does NOT touch them. The 4 existing filters (Industry, Legal Country,
Sales Region, Account Unit Group) survive the components PATCH.

Usage:
  python3 -m scripts.sf_audit.rebuild_sd_dashboard --dry-run
  python3 -m scripts.sf_audit.rebuild_sd_dashboard
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

import requests

from scripts.sf_audit.reports import sf_session

logger = logging.getLogger("sf_audit.rebuild_sd_dashboard")

DASHBOARD_ID = "01ZTb00000FSP7hMAH"

# Standard filterColumns mirroring the existing widgets so dashboard-level
# filters (Industry / Legal Country / Sales Region / Account Unit Group)
# pass through to each new component.
STANDARD_FILTER_COLS = [
    {"label": "Industry", "name": "INDUSTRY"},
    {"label": "Legal Country", "name": "ADDRESS1_COUNTRY_CODE"},
    {"label": "Sales Region", "name": "Account.Region__c"},
    {"label": "Account Unit Group", "name": "Opportunity.Account_Unit_Group__c"},
]


def make_component(
    *,
    title: str,
    header: str,
    report_id: str,
    grouping_name: str,
    visualization: str,
    aggregate: str,
    sort_order: str = "Desc",
) -> dict[str, Any]:
    """Construct a SUMMARY-format dashboard component referencing a report."""
    return {
        "header": header,
        "footer": None,
        "title": title,
        "reportId": report_id,
        "type": "Report",
        "componentData": 0,
        "chartTheme": None,
        "properties": {
            "aggregates": [{"name": aggregate}] if aggregate else [],
            "autoSelectColumns": False,
            "drillUrl": None,
            "filterColumns": list(STANDARD_FILTER_COLS),
            "groupings": [
                {
                    "inheritedReportSort": None,
                    "name": grouping_name,
                    "sortAggregate": None,
                    "sortOrder": sort_order,
                }
            ],
            "maxRows": None,
            "reportFormat": "SUMMARY",
            "sort": None,
            "useReportChart": False,
            "visualizationProperties": {
                "combineSmallGroups": False,
                "decimalPrecision": -1,
                "displayUnits": "auto",
                "legendPosition": "Right",
                "showPercentages": False,
                "showValues": True,
                "sortLegendValues": False,
            },
            "visualizationType": visualization,
        },
    }


# New components to add.
NEW_COMPONENTS = [
    make_component(
        title="Lost ARR This Quarter (L+E)",
        header="Lost ARR by Stage Where Lost",
        report_id="00OTb000008msSvMAI",
        grouping_name="STAGE_NAME",
        visualization="Bar",
        aggregate="s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
    ),
    make_component(
        title="Pipeline ARR by Owner (this-Q L+E)",
        header="Pipeline Concentration by Owner",
        report_id="00OTb000008msPhMAI",
        grouping_name="FULL_NAME",
        visualization="Bar",
        aggregate="s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
    ),
    make_component(
        title="New Opps Created Last Month",
        header="Pipeline Velocity by Type",
        report_id="00OTb000008msW9MAI",
        grouping_name="TYPE",
        visualization="Pie",
        aggregate="RowCount",
    ),
    make_component(
        title="Stage 3+ Opps Created This Month",
        header="Governance Volume: Stage 3+ entry",
        report_id="00OTb000008msZNMAY",
        grouping_name="STAGE_NAME",
        visualization="Bar",
        aggregate="s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
    ),
]


def rebuild(instance: str, token: str, dry_run: bool = False) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{instance}/services/data/v65.0/analytics/dashboards/{DASHBOARD_ID}"

    # GET current dashboard metadata (response structure differs from reports —
    # dashboard describe returns the metadata at the TOP level, not under
    # a `dashboardMetadata` key).
    r = requests.get(url + "/describe", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"GET failed: {r.status_code}", file=sys.stderr)
        return 2
    md = r.json()
    components = list(md.get("components") or [])
    layout = md.get("layout") or {}
    layout_components = list(layout.get("components") or [])

    print(f"Current dashboard: {md.get('name')}")
    print(f"  components: {len(components)}, filters: {len(md.get('filters') or [])}")

    # ── Step 1: identify removals ──────────────────────────────────
    seen_dup_keys: set[str] = set()
    new_components: list[dict[str, Any]] = []
    new_layout: list[dict[str, Any]] = []
    removals: list[str] = []

    for i, c in enumerate(components):
        rid = c.get("reportId")
        if not rid:
            removals.append(f"  [{i}] empty slot (reportId=None) — REMOVED")
            continue
        # Dedupe by reportId — keep first occurrence
        if rid in seen_dup_keys:
            removals.append(f"  [{i}] duplicate of report {rid} — REMOVED ({c.get('title', '')})")
            continue
        seen_dup_keys.add(rid)
        new_components.append(c)
        if i < len(layout_components):
            new_layout.append(layout_components[i])

    # ── Step 2: append new components + layout positions ──────────
    # Layout grid: append below the existing widgets at row=max(row+rowspan)
    max_row = max((lc.get("row", 0) + lc.get("rowspan", 0) for lc in new_layout), default=0)
    for offset, nc in enumerate(NEW_COMPONENTS):
        new_components.append(nc)
        # 6-col-wide widgets, 2 per row
        col = (offset % 2) * 6
        row = max_row + (offset // 2) * 8
        new_layout.append({"colspan": 6, "column": col, "row": row, "rowspan": 8})

    print(f"\nRemovals: {len(removals)}")
    for r in removals:
        print(r)
    print(f"\nAdditions: {len(NEW_COMPONENTS)}")
    for nc in NEW_COMPONENTS:
        print(f"  + {nc['title']:<50s} → report {nc['reportId']}")
    print(f"\nFinal component count: {len(new_components)} (was {len(components)})")

    if dry_run:
        return 0

    # ── Step 3: PATCH ─────────────────────────────────────────────
    # Per Phase 2.8 memory: strip read-only fields before PATCH.
    # Dashboard PATCH request body has the metadata at TOP level (matching
    # the shape of the describe response), NOT wrapped under
    # `dashboardMetadata` (which is the convention for reports).
    md["components"] = new_components
    md["layout"] = {"components": new_layout, "gridLayout": layout.get("gridLayout")}
    for ro in (
        "id",
        "createdById",
        "createdDate",
        "lastModifiedDate",
        "namespace",
        "type",
        "developerName",
        "folderId",
        "folderName",
        "url",
        "labels",
        "ownerId",
    ):
        md.pop(ro, None)

    r2 = requests.patch(
        url,
        headers={**headers, "Content-Type": "application/json"},
        json=md,
        timeout=60,
    )
    if r2.status_code in (200, 201):
        print(f"\n✓ Dashboard rebuilt: {DASHBOARD_ID}")
        print(f"  {instance}/lightning/r/Dashboard/{DASHBOARD_ID}/view")
        return 0
    print(f"\n✗ PATCH failed: {r2.status_code}")
    print(r2.text[:600])
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild SD Monthly dashboard")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    instance, token, _ = sf_session()
    return rebuild(instance, token, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
