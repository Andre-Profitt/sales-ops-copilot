"""Wire the two new cross-filter reports onto the cockpit dashboard:

  1. Swap the existing "▲ ZOMBIE PIPELINE" component (which referenced
     the legacy 365+d open report `00OTb000008nUmjMAE` and used a raw
     non-FX-converted aggregate `s!Opportunity.APTS_Opportunity_ARR__c`)
     to point at `Cockpit_Zombie_v1` (`00OTb000008nijFMAQ`) — the
     cross-filtered, FX-correct (`...CONVERT`), 730+d, no-activity-60d
     report. Also fixes the metric label.

  2. Append a new "▲ COVERAGE GAP" Metric component referencing
     `Cockpit_CoverageGap_v1` (`00OTb000008nirJMAQ`) at the top-right
     of the dashboard (row 0, col 9 — empty space; 3 cols × 4 rows,
     mirrors the Zombie tile size).

Run: `python3 -m sf_dashboard.cockpit.wire_xfilter_widgets` from repo root.
Idempotent: skip-if-already-pointing at the new IDs.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys

import requests

DASHBOARD_ID = "01ZTb00000FxX2YMAV"
ZOMBIE_REPORT_ID = "00OTb000008nijFMAQ"  # Cockpit_Zombie_v1
COVERAGEGAP_REPORT_ID = "00OTb000008nirJMAQ"  # Cockpit_CoverageGap_v1
ARR_AGG = "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT"
API_VERSION = "v66.0"


def _sf_session() -> tuple[str, str]:
    """Get accessToken + instanceUrl from `sf` CLI."""
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

    # 1. GET dashboard describe
    print(f"[1/4] GET dashboard {DASHBOARD_ID}/describe")
    r = requests.get(
        f"{base}/analytics/dashboards/{DASHBOARD_ID}/describe", headers=headers, timeout=30
    )
    r.raise_for_status()
    desc = r.json()
    md = copy.deepcopy(desc)
    # Strip read-only top-level keys per Reports REST API contract
    for ro in ("canChangeRunningUser", "canUseStickyFilter", "id", "lastModifiedDate"):
        md.pop(ro, None)

    comps = md["components"]
    layout = md["layout"]
    print(f"   {len(comps)} components, {layout.get('numColumns')}-col grid")

    # 2. Swap component [0] (ZOMBIE PIPELINE) to new report + fix aggregate
    zombie_idx = next(
        (i for i, c in enumerate(comps) if (c.get("header") or "").strip().startswith("▲ ZOMBIE")),
        None,
    )
    if zombie_idx is None:
        print("   FATAL: no ▲ ZOMBIE PIPELINE component found")
        return 1
    z = comps[zombie_idx]
    if z.get("reportId") == ZOMBIE_REPORT_ID:
        print(f"[2/4] [{zombie_idx}] already points at Cockpit_Zombie_v1 — skipping")
    else:
        print(f"[2/4] swap [{zombie_idx}] reportId {z.get('reportId')} -> {ZOMBIE_REPORT_ID}")
        z["reportId"] = ZOMBIE_REPORT_ID
        # Fix the aggregate to use the FX-converted column
        z["properties"]["aggregates"] = [{"name": ARR_AGG}]
        z["properties"]["visualizationProperties"]["breakPoints"] = [
            {
                "aggregateName": ARR_AGG,
                "breaks": [
                    {"color": None, "lowerBound": None, "upperBound": None},
                    {"color": None, "lowerBound": None, "upperBound": None},
                    {"color": None, "lowerBound": None, "upperBound": None},
                ],
            }
        ]
        # Update the subtitle/label to reflect the new (better) criteria
        z["properties"]["visualizationProperties"]["metricLabel"] = (
            "730+ days · no activity 60d · L+E"
        )
        z["header"] = "▲ ZOMBIE PIPELINE"

    # 3. Append Coverage Gap component (if not already present)
    cg_idx = next(
        (i for i, c in enumerate(comps) if c.get("reportId") == COVERAGEGAP_REPORT_ID),
        None,
    )
    if cg_idx is not None:
        print(f"[3/4] Coverage Gap already at component [{cg_idx}] — skipping append")
    else:
        if len(comps) >= 20:
            print("   FATAL: dashboard at hard 20-component cap, can't append")
            return 1
        print(f"[3/4] append Coverage Gap as component [{len(comps)}]")
        coverage_comp = {
            "componentData": 0,
            "footer": None,
            "header": "▲ COVERAGE GAP",
            "title": None,
            "type": "Report",
            "reportId": COVERAGEGAP_REPORT_ID,
            "chartTheme": None,
            "properties": {
                "aggregates": [{"name": "RowCount"}],
                "autoSelectColumns": True,
                "drillUrl": None,
                "filterColumns": [
                    {"label": "Sales Region", "name": "Account.Region__c"},
                ],
                "groupings": None,
                "maxRows": None,
                "reportFormat": "SUMMARY",
                "sort": None,
                "useReportChart": False,
                "visualizationProperties": {
                    "breakPoints": [
                        {
                            "aggregateName": "RowCount",
                            "breaks": [
                                {"color": None, "lowerBound": None, "upperBound": None},
                                {"color": None, "lowerBound": None, "upperBound": None},
                                {"color": None, "lowerBound": None, "upperBound": None},
                            ],
                        }
                    ],
                    "decimalPrecision": 0,
                    "displayUnits": "auto",
                    "metricLabel": "Tier 1 · no open opp 90d",
                    "showRange": False,
                },
                "visualizationType": "Metric",
            },
        }
        comps.append(coverage_comp)
        # Layout: top-right slot at r=0, c=9, span 3 wide × 4 tall
        layout["components"].append({"row": 0, "column": 9, "rowspan": 4, "colspan": 3})

    # 4. PATCH back
    print(f"[4/4] PATCH /analytics/dashboards/{DASHBOARD_ID}")
    p = requests.patch(
        f"{base}/analytics/dashboards/{DASHBOARD_ID}", headers=headers, json=md, timeout=60
    )
    if p.status_code not in (200, 201):
        print(f"   PATCH FAILED {p.status_code}: {p.text[:1000]}")
        return 1
    print(
        f"   ok — view: {instance.replace('.my.salesforce.com', '.lightning.force.com')}"
        f"/lightning/r/Dashboard/{DASHBOARD_ID}/view"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
