"""Phase 12 — wire the 3 v2 KPI reports as new components on SD Monthly.

Adds:
  - Bookings by Fiscal Quarter (Bar viz, half width)
  - Top 20 At-Risk Open Opportunities (Table, full width — drill list)
  - Forecast Category Split (Pie, third width)

After the components are added, run improve_dashboard_layout.py to reflow
the grid (the auto-packer handles the new sizing).
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

import requests

from scripts.sf_audit.improve_dashboard_layout import pack_layout, widget_size
from scripts.sf_audit.rebuild_sd_dashboard import STANDARD_FILTER_COLS
from scripts.sf_audit.reports import sf_session

logger = logging.getLogger("sf_audit.wire_kpi_v2")

DASHBOARD_ID = "01ZTb00000FSP7hMAH"

NEW_WIDGETS = [
    {
        "header": "Bookings Trend by Fiscal Quarter",
        "title": "Won L+E ARR, last fiscal year",
        "report_id": "00OTb000008mvIjMAI",
        "viz": "Bar",
        "grouping": "CLOSE_DATE",
        "groupingDateGranularity": "fiscalQuarter",
        "aggregate": "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
    },
    {
        "header": "Top 20 At-Risk Open Opps",
        "title": "Slipped or 60d+ stale, by ARR",
        "report_id": "00OTb000008mvH7MAI",
        "viz": "FlexTable",
        "format": "TABULAR",
    },
    {
        "header": "Forecast Category Split",
        "title": "This-Q L+E by category",
        "report_id": "00OTb000008mvFVMAY",
        "viz": "Pie",
        "grouping": "FORECAST_CATEGORY",
        "aggregate": "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
    },
]


def make_component(spec: dict[str, Any]) -> dict[str, Any]:
    """Build a SF Analytics dashboard component from a NEW_WIDGETS spec."""
    fmt = spec.get("format", "SUMMARY")
    properties: dict[str, Any] = {
        "aggregates": [{"name": spec["aggregate"]}] if spec.get("aggregate") else [],
        "autoSelectColumns": False,
        "drillUrl": None,
        "filterColumns": list(STANDARD_FILTER_COLS),
        "groupings": [],
        "maxRows": 20 if spec["viz"] == "FlexTable" else None,
        "reportFormat": fmt,
        "sort": None,
        "useReportChart": False,
        "visualizationProperties": {
            "decimalPrecision": -1,
            "displayUnits": "auto",
            "legendPosition": "Right",
            "showPercentages": spec["viz"] == "Pie",
            "showValues": True,
        },
        "visualizationType": spec["viz"],
    }
    if spec.get("grouping"):
        properties["groupings"] = [
            {
                "inheritedReportSort": None,
                "name": spec["grouping"],
                "sortAggregate": None,
                "sortOrder": "Asc" if spec.get("groupingDateGranularity") else "Desc",
                "dateGranularity": spec.get("groupingDateGranularity", "None"),
            }
        ]
    return {
        "header": spec["header"],
        "footer": None,
        "title": spec["title"],
        "reportId": spec["report_id"],
        "type": "Report",
        "componentData": 0,
        "chartTheme": None,
        "properties": properties,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Wire v2 KPI widgets onto SD Monthly")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", type=str, help="comma-sep report IDs")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    instance, token, _ = sf_session()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{instance}/services/data/v65.0/analytics/dashboards/{DASHBOARD_ID}"

    r = requests.get(url + "/describe", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"GET failed: {r.status_code}")
        return 2
    md = r.json()
    components = list(md.get("components") or [])
    print(f"Dashboard {DASHBOARD_ID}: {len(components)} components")

    existing_rids = {c.get("reportId") for c in components}
    only_rids = {s.strip() for s in (args.only or "").split(",")} if args.only else None
    new_components = []
    for spec in NEW_WIDGETS:
        if only_rids and spec["report_id"] not in only_rids:
            continue
        if spec["report_id"] in existing_rids:
            print(f"  ⚪ already on dashboard: {spec['header']}")
            continue
        new_components.append(make_component(spec))
        print(f"  + {spec['header']}")

    if not new_components:
        print("Nothing to add.")
        return 0

    all_components = components + new_components
    # Re-pack the entire layout grid
    sizes = []
    for c in all_components:
        props = c.get("properties") or {}
        viz = props.get("visualizationType") or ""
        rf = props.get("reportFormat") or ""
        if viz == "Metric":
            sizes.append((3, 4))
        else:
            sizes.append(widget_size(viz, rf))
    new_layout = pack_layout(sizes)

    if args.dry_run:
        print(f"\nWould add {len(new_components)} widgets, total {len(all_components)}")
        return 0

    md["components"] = all_components
    md["layout"] = {
        "components": new_layout,
        "gridLayout": (md.get("layout") or {}).get("gridLayout"),
    }
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

    pr = requests.patch(
        url,
        headers={**headers, "Content-Type": "application/json"},
        json=md,
        timeout=60,
    )
    if pr.status_code in (200, 201):
        print(f"\n✓ {len(new_components)} v2 KPI widgets added to {DASHBOARD_ID}")
        print(f"  {instance}/lightning/r/Dashboard/{DASHBOARD_ID}/view")
        return 0
    print(f"\n✗ PATCH failed {pr.status_code}: {pr.text[:300]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
