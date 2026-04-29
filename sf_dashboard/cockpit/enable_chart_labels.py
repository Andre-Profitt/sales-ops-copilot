"""Enable numeric / percentage labels on chart widgets across the
dashboards we own.

Audit (2026-04-29) showed nearly every Bar/Funnel/Donut/Column widget
on the SimCorp One — Product Pipeline dashboard and the Sales Ops —
Commercial Health & Governance cockpit was created with `showValues:
False`, `showPercentages: False`, and `showTotal: False`. Bars without
data labels force the eye to estimate against the axis; donuts without
percentages defeat the whole point. This script flips those flags on.

Per viz type:
  - Bar     -> showValues: True
  - Column  -> showValues: True
  - Funnel  -> showValues: True, showPercentages: True
  - Donut   -> showValues: True, showPercentages: True, showTotal: True
  - Metric  -> untouched (the number IS the widget)
  - Other   -> untouched

Run: python3 -m sf_dashboard.cockpit.enable_chart_labels
Idempotent — only PATCHes if a flag changes.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys

import requests

API_VERSION = "v66.0"

TARGET_DASHBOARDS = [
    # Andre-owned (private folder)
    ("01ZTb00000FyrbtMAB", "SimCorp One — Product Pipeline"),
    ("01ZTb00000FxYhlMAF", "Quarter Close Pacing"),
    ("01ZTb00000FxYg9MAF", "Activity Health"),
    ("01ZTb00000FxYeXMAV", "Account Health Watch"),
    ("01ZTb00000FxYcvMAF", "Forecast Accuracy & Pacing"),
    ("01ZTb00000FxYbJMAV", "Marketing & Lead Funnel"),
    ("01ZTb00000FxYZhMAN", "CRO Cockpit"),
    ("01ZTb00000FxYY5MAN", "Deal Desk Operations"),
    ("01ZTb00000FxYUrMAN", "Win/Loss Analysis"),
    ("01ZTb00000FxYTFMA3", "Renewals Dashboard"),
    ("01ZTb00000FyJSAMA3", "Sales Rep Scorecard"),
    # Shared / public folders
    ("01ZTb00000FxX2YMAV", "Sales Ops — Commercial Health & Governance"),
    ("01ZTb00000FSP7hMAH", "Sales Directors Monthly Pipeline and Insights"),
]

DESIRED = {
    "Bar": {"showValues": True},
    "Column": {"showValues": True},
    "Funnel": {"showValues": True, "showPercentages": True},
    "Donut": {"showValues": True, "showPercentages": True, "showTotal": True},
}


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

    total_changed = 0
    for did, name in TARGET_DASHBOARDS:
        print(f"\n[*] {name} ({did})")
        r = requests.get(f"{base}/analytics/dashboards/{did}/describe", headers=headers, timeout=30)
        r.raise_for_status()
        md = copy.deepcopy(r.json())
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
        # runningUser comes back as {displayName, id} — PATCH rejects that shape
        md["runningUser"] = None

        changed = 0
        for i, c in enumerate(md.get("components") or []):
            props = c.get("properties") or {}
            viz = props.get("visualizationType") or ""
            desired = DESIRED.get(viz)
            if not desired:
                continue
            vp = props.get("visualizationProperties")
            if not isinstance(vp, dict):
                vp = {}
                props["visualizationProperties"] = vp
            for k, v in desired.items():
                if vp.get(k) != v:
                    vp[k] = v
                    changed += 1
            h = c.get("header")
            title = h if isinstance(h, str) else (h.get("title") if isinstance(h, dict) else "?")
            print(f"    [{i:2d}] {viz:8s} {(title or '')[:50]}  -> {desired}")

        if changed == 0:
            print("    (no changes — already on)")
            continue

        p = requests.patch(
            f"{base}/analytics/dashboards/{did}", headers=headers, json=md, timeout=60
        )
        if p.status_code not in (200, 201):
            print(f"    PATCH FAILED {p.status_code}: {p.text[:600]}")
            return 1
        print(f"    flipped {changed} flags  ok")
        total_changed += changed

    print(
        f"\nDone. {total_changed} viz-property flags flipped across {len(TARGET_DASHBOARDS)} dashboards."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
