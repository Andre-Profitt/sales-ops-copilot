"""Build "Pipeline Hygiene" dashboard in Andre's folder — focused
collection of the 4 hygiene/anomaly metrics that currently live mixed
into the 20-component Sales Ops Cockpit, plus a wide Zombie-by-Owner
Bar that the cockpit doesn't have room for.

Why a separate dashboard:
  - Sales Ops Cockpit is at 20/20 component cap.
  - Best practice: dashboards >7 widgets degrade visual scan-line.
  - Hygiene signal deserves its own page: a director scanning "what's
    broken in our pipeline?" doesn't want it interleaved with renewal
    health and forecast trend.

Widgets:
  - r0,c0  (3x4 Metric)  ▲ Zombie Pipeline       ─ Cockpit_Zombie_v1 (ARR)
  - r0,c3  (3x4 Metric)  ▲ Coverage Gap          ─ Cockpit_CoverageGap_v1 (count)
  - r0,c6  (3x4 Metric)  ▲ Activity Drought      ─ Cockpit · Activity Drought CFQ
  - r0,c9  (3x4 Metric)  ▲ Approval Gap ≥500k    ─ Stage 3+ no Commercial Approval
  - r4,c0  (12x8 Bar)    Zombie by Owner          ─ same Cockpit_Zombie_v1 report,
                                                   Owner-grouped Bar slicing

Run: python3 -m sf_dashboard.cockpit.build_pipeline_hygiene_dashboard
Idempotent: skip-if-Title-exists in Andre's folder.

Pattern: clone the Sales Ops Cockpit (gridLayout=True, has Metric +
Bar viz types), reuse its component shapes, swap reportIds + headers
+ titles + drillUrls, override layout to a clean 5-widget grid.
Direct dashboard POST hits JSON_PARSER_ERROR — clone-then-PATCH is
the established pattern from build_simcorp_one_dashboard.py.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys

import requests

API_VERSION = "v66.0"
ANDRE_DASHBOARD_FOLDER_ID = "00lTb000006OCRBIA4"
COCKPIT_TEMPLATE_ID = "01ZTb00000FxX2YMAV"

# Reports we'll surface (all live in org)
ZOMBIE_RID = "00OTb000008nijFMAQ"  # Cockpit_Zombie_v1 — cross-filtered
COVERAGE_GAP_RID = "00OTb000008nirJMAQ"  # Cockpit_CoverageGap_v1
ACTIVITY_DROUGHT_RID = "00OTb000008nUl7MAE"  # Cockpit · Activity Drought CFQ 30+ Days
APPROVAL_GAP_RID = "00OTb000008muphMAA"  # Stage 3+ ≥500k no Commercial Approval

# Cockpit component indices (per current 20-component layout, verified 2026-04-29):
# [0] = ▲ ZOMBIE PIPELINE Metric (3x4)
# [16] = ▲ COVERAGE GAP Metric (3x4)
# [18] = Activity Drought Metric (3x4)
# [11] = Approval Gap ≥$500k Metric (3x4)
# [2] = Top 10 Open Accounts Bar (6x8) — known-good Bar shape we'll repurpose

TARGET_SWAPS = [
    # (cloned_idx, reportId, header, subtitle≤40chars, layout)
    (
        0,
        ZOMBIE_RID,
        "▲ Zombie Pipeline",
        "730+d open · no activity 60d · L+E ARR",
        {"row": 0, "column": 0, "rowspan": 4, "colspan": 3},
    ),
    (
        16,
        COVERAGE_GAP_RID,
        "▲ Coverage Gap",
        "Tier-1 accts · no open opp 90d",
        {"row": 0, "column": 3, "rowspan": 4, "colspan": 3},
    ),
    (
        18,
        ACTIVITY_DROUGHT_RID,
        "▲ Activity Drought",
        "CFQ open opps · no activity 30d+",
        {"row": 0, "column": 6, "rowspan": 4, "colspan": 3},
    ),
    (
        11,
        APPROVAL_GAP_RID,
        "▲ Approval Gap ≥500k",
        "Stage 3+ Land · no Commercial Approval",
        {"row": 0, "column": 9, "rowspan": 4, "colspan": 3},
    ),
    (
        2,
        ZOMBIE_RID,
        "Zombie Pipeline · by Owner",
        "Owner ranking of zombie ARR exposure",
        {"row": 4, "column": 0, "rowspan": 8, "colspan": 12},
    ),
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


def main() -> int:
    token, instance = _sf_session()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    base = f"{instance}/services/data/{API_VERSION}"

    # Skip if already built
    soql = (
        "SELECT Id FROM Dashboard WHERE Title = 'Pipeline Hygiene' "
        f"AND FolderId = '{ANDRE_DASHBOARD_FOLDER_ID}' LIMIT 1"
    )
    r = requests.get(f"{base}/query", headers=headers, params={"q": soql}, timeout=30)
    r.raise_for_status()
    existing = r.json().get("records") or []
    if existing:
        did = existing[0]["Id"]
        print(f"already built — {did}")
        view = instance.replace(".my.salesforce.com", ".lightning.force.com")
        print(f"view: {view}/lightning/r/Dashboard/{did}/view")
        return 0

    # Clone cockpit for known-good metadata skeleton
    print(f"[1/3] Clone Sales Ops Cockpit ({COCKPIT_TEMPLATE_ID})")
    c = requests.post(
        f"{base}/analytics/dashboards?cloneId={COCKPIT_TEMPLATE_ID}",
        headers=headers,
        json={"name": "Pipeline Hygiene", "folderId": ANDRE_DASHBOARD_FOLDER_ID},
        timeout=60,
    )
    if c.status_code not in (200, 201):
        raise RuntimeError(f"CLONE -> {c.status_code}: {c.text[:1500]}")
    did = c.json()["id"]
    print(f"      -> {did}")

    # Get describe, swap components in place
    g = requests.get(f"{base}/analytics/dashboards/{did}/describe", headers=headers, timeout=30)
    g.raise_for_status()
    md = copy.deepcopy(g.json())
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
    md["name"] = "Pipeline Hygiene"
    md["description"] = (
        "Focused hygiene page: 4 anomaly metrics (Zombie, Coverage Gap, "
        "Activity Drought, Approval Gap) + rep-level Zombie ranking. "
        "No renewal/forecast noise — see Sales Ops Cockpit for that."
    )
    md["folderId"] = ANDRE_DASHBOARD_FOLDER_ID

    cloned = md["components"]
    new_comps = []
    new_layout = []
    for clone_idx, rid, header, subtitle, layout in TARGET_SWAPS:
        comp = copy.deepcopy(cloned[clone_idx])
        comp["reportId"] = rid
        comp["header"] = header
        comp["title"] = subtitle
        if "drillUrl" in (comp.get("properties") or {}):
            comp["properties"]["drillUrl"] = f"/lightning/r/Report/{rid}/view"
        # Per the chart-labels sweep — turn on labels for any chart we ship
        viz = (comp.get("properties") or {}).get("visualizationType")
        vp = (comp.get("properties") or {}).get("visualizationProperties")
        if isinstance(vp, dict):
            if viz == "Bar":
                vp["showValues"] = True
            elif viz == "Funnel":
                vp["showValues"] = True
                vp["showPercentages"] = True
            elif viz == "Donut":
                vp["showValues"] = True
                vp["showPercentages"] = True
                vp["showTotal"] = True
        new_comps.append(comp)
        new_layout.append(layout)
    md["components"] = new_comps
    md["layout"]["components"] = new_layout
    md["filters"] = []

    print("[2/3] PATCH 5 components")
    p = requests.patch(f"{base}/analytics/dashboards/{did}", headers=headers, json=md, timeout=60)
    if p.status_code not in (200, 201):
        raise RuntimeError(f"PATCH -> {p.status_code}: {p.text[:1500]}")

    view = instance.replace(".my.salesforce.com", ".lightning.force.com")
    print(f"[3/3] Done. View: {view}/lightning/r/Dashboard/{did}/view")
    return 0


if __name__ == "__main__":
    sys.exit(main())
