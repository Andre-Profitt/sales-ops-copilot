"""Retire the legacy "Stale 60d+" Metric tile (which overlaps with the new
▲ ZOMBIE PIPELINE cross-filter widget) and replace it in the same dashboard
slot with a new Bar widget showing pipeline-ARR share-of-total by Region —
powered by the PARENTGROUPVAL `% of Total ARR` formula we just authored on
`CRO · Open Pipeline by Region` (00OTb000008mvyfMAA).

Result: same 3×4 footprint at row 16 col 0, but instead of "EUR X stuck for
60 days" (one number) the user sees five region bars each labeled with their
percentage share of the total open ARR. That answers the "where is our
pipeline concentrated" question natively, no second click.

Run: `python3 -m sf_dashboard.cockpit.swap_stale_for_region_share` from the
repo root. Idempotent (skip if already swapped).
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys

import requests

DASHBOARD_ID = "01ZTb00000FxX2YMAV"
OLD_REPORT_ID = "00OTb000008mv4DMAQ"  # Stale 60d+
NEW_REPORT_ID = "00OTb000008mvyfMAA"  # CRO · Open Pipeline by Region
ARR_AGG = "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT"
PCT_AGG = "FORMULA1"  # the new PARENTGROUPVAL "% of Total ARR" column
API_VERSION = "v66.0"


def _sf_session() -> tuple[str, str]:
    out = subprocess.run(
        ["sf", "org", "display", "--target-org", "preprod", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    d = json.loads(out.stdout)["result"]
    return d["accessToken"], d["instanceUrl"]


def main() -> int:
    token, instance = _sf_session()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    base = f"{instance}/services/data/{API_VERSION}"

    # GET dashboard
    r = requests.get(
        f"{base}/analytics/dashboards/{DASHBOARD_ID}/describe", headers=headers, timeout=30
    )
    r.raise_for_status()
    md = copy.deepcopy(r.json())
    for ro in ("canChangeRunningUser", "canUseStickyFilter", "id", "lastModifiedDate"):
        md.pop(ro, None)

    comps = md["components"]
    layouts = md["layout"]["components"]

    # Find Stale 60d+ component
    idx = next((i for i, c in enumerate(comps) if c.get("reportId") == OLD_REPORT_ID), None)
    if idx is None:
        # Already swapped? Check if NEW is anywhere
        if any(c.get("reportId") == NEW_REPORT_ID for c in comps):
            print("already swapped — region-share widget present")
            return 0
        print(f"FATAL: no component with reportId={OLD_REPORT_ID} (Stale 60d+) found")
        return 1

    print(f"[1/2] retire [{idx}] Stale 60d+ ({OLD_REPORT_ID})")
    print(f"      lay={layouts[idx]} keep slot")

    # Build the new Bar widget — Region grouping × FORMULA1 (% of Total ARR)
    # plus s!ARR.CONVERT for tooltip / drill richness.
    # Shape mirrors the existing "Owner Concentration" Bar widget
    # (component [7] in the cockpit) — same property keys, just swapped
    # to the Region grouping and the new FORMULA1 (% of Total ARR) aggregate.
    new_comp = {
        "componentData": 0,
        "footer": None,
        "header": "▲ % BY REGION",
        "title": None,
        "type": "Report",
        "reportId": NEW_REPORT_ID,
        "chartTheme": None,
        "properties": {
            "aggregates": [{"name": PCT_AGG}],
            "autoSelectColumns": True,
            "drillUrl": f"/lightning/r/Report/{NEW_REPORT_ID}/view",
            "filterColumns": [
                {"label": "Sales Region", "name": "Account.Region__c"},
            ],
            "groupings": [
                {
                    "inheritedReportSort": "reportGrouping",
                    "name": "Account.Region__c",
                    "sortAggregate": None,
                    "sortOrder": None,
                }
            ],
            "maxRows": None,
            "reportFormat": "SUMMARY",
            "sort": None,
            "useReportChart": False,
            "visualizationProperties": {
                "axisRange": {"max": None, "min": None, "rangeType": "auto"},
                "decimalPrecision": 1,
                "displayUnits": "auto",
                "groupByType": "none",
                "legendPosition": None,
                "referenceLineColors": [],
                "referenceLineValues": [],
                "showChatterPhotos": False,
                "showValues": True,
                "sortLegendValues": False,
            },
            "visualizationType": "Bar",
        },
    }

    # Swap in place: same array index + same layout slot
    comps[idx] = new_comp
    print(f"[2/2] place [{idx}] ▲ % BY REGION (Bar) -> {NEW_REPORT_ID}")

    # PATCH back
    p = requests.patch(
        f"{base}/analytics/dashboards/{DASHBOARD_ID}", headers=headers, json=md, timeout=60
    )
    if p.status_code not in (200, 201):
        print(f"PATCH FAILED {p.status_code}: {p.text[:1000]}")
        return 1
    view = instance.replace(".my.salesforce.com", ".lightning.force.com")
    print(f"ok — view: {view}/lightning/r/Dashboard/{DASHBOARD_ID}/view")
    return 0


if __name__ == "__main__":
    sys.exit(main())
