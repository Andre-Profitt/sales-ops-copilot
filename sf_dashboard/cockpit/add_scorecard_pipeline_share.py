"""Add a Bar widget to the Sales Rep Scorecard surfacing "Pipeline
Coverage by Rep" — uses the existing CRO · Coverage x by Rep report
(00OTb000008nePVMAY) which already carries the PARENTGROUPVAL "% of
Total ARR" formula we authored via Playwright earlier this session.

Why: the Scorecard has 12 widgets covering activity, age, approvals,
win-rate, and quota attainment — but no widget exposing how each rep's
open ARR compares to their quota (the "coverage ratio" question every
director asks before the QBR). The supporting report has been live
since 2026-04-29 15:50 but isn't surfaced anywhere yet.

PATCH (not clone) — modifies the existing Sales Rep Scorecard dashboard
in place. Idempotent skip-if-already-present by reportId.

Run: python3 -m sf_dashboard.cockpit.add_scorecard_pipeline_share
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys

import requests

API_VERSION = "v66.0"
SCORECARD_ID = "01ZTb00000FyJSAMA3"
COVERAGE_REPORT_ID = "00OTb000008nePVMAY"  # CRO · Coverage x by Rep
ARR = "Opportunity.APTS_Opportunity_ARR__c.CONVERT"
S_ARR = f"s!{ARR}"


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

    g = requests.get(
        f"{base}/analytics/dashboards/{SCORECARD_ID}/describe",
        headers=headers,
        timeout=30,
    )
    g.raise_for_status()
    md = copy.deepcopy(g.json())

    # Skip if already added
    for c in md.get("components", []):
        if c.get("reportId") == COVERAGE_REPORT_ID:
            print("already wired — Coverage x by Rep is component already")
            return 0

    if len(md["components"]) >= 20:
        print("FATAL: Scorecard at 20-component cap — would need to retire one")
        return 1

    # Strip read-only / problematic fields
    for ro in (
        "id",
        "lastModifiedDate",
        "canChangeRunningUser",
        "canUseStickyFilter",
        "owner",
        "folderName",
        "flexTableImplementation",
        "maxFilterOptions",
        "chartTheme",
        "colorPalette",
    ):
        md.pop(ro, None)
    md["runningUser"] = None

    # Build the new Bar component by cloning component [0] (Open Pipeline by Rep
    # — known-good Bar shape on this dashboard) and swapping reportId / aggregate.
    # Strip the cloned component's id + lastModifiedDate — SF rejects PATCH if a
    # new component carries an existing component id.
    template = copy.deepcopy(md["components"][0])
    for ro in ("id", "lastModifiedDate"):
        template.pop(ro, None)
    template["reportId"] = COVERAGE_REPORT_ID
    template["header"] = "Pipeline Coverage by Rep"
    template["title"] = "Coverage ratio · open ARR vs quota"
    if "drillUrl" in (template.get("properties") or {}):
        template["properties"]["drillUrl"] = f"/lightning/r/Report/{COVERAGE_REPORT_ID}/view"
    # Ensure labels visible
    vp = (template.get("properties") or {}).get("visualizationProperties")
    if isinstance(vp, dict):
        vp["showValues"] = True
    md["components"].append(template)

    # Place at the bottom of the existing grid. Find the max row used.
    layouts = md["layout"]["components"]
    max_bottom = 0
    for lc in layouts:
        bottom = (lc.get("row") or 0) + (lc.get("rowspan") or 0)
        max_bottom = max(max_bottom, bottom)
    layouts.append({"row": max_bottom, "column": 0, "rowspan": 8, "colspan": 12})

    p = requests.patch(
        f"{base}/analytics/dashboards/{SCORECARD_ID}",
        headers=headers,
        json=md,
        timeout=60,
    )
    if p.status_code not in (200, 201):
        raise RuntimeError(f"PATCH -> {p.status_code}: {p.text[:1500]}")

    view = instance.replace(".my.salesforce.com", ".lightning.force.com")
    print(
        f"Added 'Pipeline Coverage by Rep' widget at the bottom of Sales Rep "
        f"Scorecard. View: {view}/lightning/r/Dashboard/{SCORECARD_ID}/view"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
