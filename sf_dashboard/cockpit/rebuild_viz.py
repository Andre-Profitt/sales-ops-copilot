#!/usr/bin/env python3
"""
Rebuild widget viz types on the Sales Ops Cockpit dashboard.

Same dashboard, same 16 reports — only `componentType`/`visualizationType`
and grid layout change. Bar-everywhere → mixed exec cockpit (Metric KPIs,
Funnel pipeline, Column time-series, Donut split, Bar top-N).

Idempotent. PATCHes the existing dashboard via Analytics REST.

Usage:
    python3 rebuild_viz.py                  # do it
    python3 rebuild_viz.py --dry-run        # print modified JSON, no PATCH
    python3 rebuild_viz.py --diff           # show before/after viz mix only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from typing import Any

# ── Config ─────────────────────────────────────────────────────────────────

TARGET_ORG = "apro@simcorp.com"
API_VERSION = "66.0"
DASHBOARD_ID = "01ZTb00000FxX2YMAV"

# Severity colors
RED = "#C25454"  # critical alerts
AMBER = "#F4B400"  # important alerts
NAVY = "#1E3A8A"  # SimCorp navy (KPI neutral)


# ── Per-widget viz spec ────────────────────────────────────────────────────
# Keyed by reportId (verified via GET /describe on dashboard 01ZTb00000FxX2YMAV).
# Each entry: (viz, severity, role) where:
#   viz       - Analytics componentType: Metric | Bar | Column | Funnel | Donut
#   severity  - "kpi" | "critical" | "important" | None
#   role      - debug label
WIDGET_SPEC: dict[str, dict[str, Any]] = {
    # KPI Metrics (5)
    "00OTb000008muBPMAY": {"viz": "Metric", "severity": "kpi", "role": "Open Pipeline ARR FY"},
    "00OTb000008mukrMAA": {"viz": "Metric", "severity": "kpi", "role": "Commit Forecast CFQ"},
    "00OTb000008mumTMAQ": {"viz": "Metric", "severity": "kpi", "role": "Open Opps Count"},
    "00OTb000008muo5MAA": {"viz": "Metric", "severity": "kpi", "role": "Renewal ACV CFQ"},
    "00OTb000008mv5pMAA": {"viz": "Bar", "severity": None, "role": "Owner Concentration top-N"},
    # Pipeline detail visuals (3)
    "00OTb000008musvMAA": {"viz": "Funnel", "severity": None, "role": "Pipeline by Stage"},
    "00OTb000008muuXMAQ": {
        "viz": "Column",
        "severity": None,
        "role": "Renewal ACV by Fiscal Quarter",
    },
    "00OTb000008muw9MAA": {"viz": "Donut", "severity": None, "role": "Open ARR by Type"},
    # Top-N rankings (2)
    "00OTb000008murJMAQ": {"viz": "Bar", "severity": None, "role": "Top Open Accounts ARR"},
    "00OTb000008mv7RMAQ": {"viz": "Bar", "severity": None, "role": "Account Concentration"},
    # Critical alerts as Metric tiles (4)
    "00OTb000008muphMAA": {
        "viz": "Metric",
        "severity": "critical",
        "role": "Stage 3+ >=500k no CA",
    },
    "00OTb000008muxlMAA": {"viz": "Metric", "severity": "critical", "role": "Land Stage 3+ no CA"},
    "00OTb000008muzNMAQ": {"viz": "Metric", "severity": "critical", "role": "Stage 5+ no KYC"},
    "00OTb000008mv0zMAA": {"viz": "Metric", "severity": "critical", "role": "Past CloseDate"},
    # Important alerts as Metric tiles (2)
    "00OTb000008mv2bMAA": {"viz": "Metric", "severity": "important", "role": "Dec31 Placeholder"},
    "00OTb000008mv4DMAQ": {"viz": "Metric", "severity": "important", "role": "Stale Activity 60d"},
}


# ── Layout (12-col grid) ────────────────────────────────────────────────────
# Row 1: 5 KPI Metrics (each 2 cols wide... but 12/5 awkward; use 12/4 = 3 cols
#        and stack 4 per row + 1 wraps). Cleaner: 4 KPI metrics row 1
#        (3 cols each) + 1 KPI in row 2 alongside other tiles.
#
# We pack like the spec suggests:
#   Row 1 (rows 0-2): 4 KPI Metrics, cols [0,3,6,9], colspan=3, rowspan=3
#   Row 2 (rows 3-9): Funnel(0,3,7) + Column(7,3,5) + Donut(... wait check)
#                     12-wide: Funnel cols 0-4 (5w), Column 5-8 (4w), Donut 9-11 (3w)
#                     rowspan=7
#   Row 3 (rows 10-15): Top Accounts cols 0-5 (6w), Owner Concentration 6-11 (6w)
#                     rowspan=6.  Account Concentration squeezed in row 4 next to alerts.
# Simpler — re-pack all 16 cleanly.
#
# Final layout (pos = (row, col, rowspan, colspan)):
LAYOUT_BY_REPORT_ID: dict[str, tuple[int, int, int, int]] = {
    # Row band 1: KPI strip — 4 metrics @ 3 cols each, rows 0-2
    "00OTb000008muBPMAY": (0, 0, 3, 3),  # Open Pipeline ARR
    "00OTb000008mukrMAA": (0, 3, 3, 3),  # Commit Forecast
    "00OTb000008mumTMAQ": (0, 6, 3, 3),  # Open Opps Count
    "00OTb000008muo5MAA": (0, 9, 3, 3),  # Renewal ACV CFQ
    # Row band 2: Pipeline detail — Funnel + Column + Donut, rows 3-9
    "00OTb000008musvMAA": (3, 0, 7, 5),  # Funnel
    "00OTb000008muuXMAQ": (3, 5, 7, 4),  # Renewal by Quarter (Column)
    "00OTb000008muw9MAA": (3, 9, 7, 3),  # Open ARR by Type (Donut)
    # Row band 3: Top-N rankings, rows 10-15
    "00OTb000008murJMAQ": (10, 0, 6, 6),  # Top Open Accounts
    "00OTb000008mv5pMAA": (10, 6, 6, 6),  # Owner Concentration
    # Row band 4: Critical alert strip (red), rows 16-18, 4 metrics @ 3 cols
    "00OTb000008muphMAA": (16, 0, 3, 3),  # >=500k no CA
    "00OTb000008muxlMAA": (16, 3, 3, 3),  # Land no CA
    "00OTb000008muzNMAQ": (16, 6, 3, 3),  # Stage 5+ no KYC
    "00OTb000008mv0zMAA": (16, 9, 3, 3),  # Past CloseDate
    # Row band 5: Important alerts (amber) + Account Concentration, rows 19-21
    "00OTb000008mv2bMAA": (19, 0, 3, 3),  # Dec31 Placeholder
    "00OTb000008mv4DMAQ": (19, 3, 3, 3),  # Stale 60d
    "00OTb000008mv7RMAQ": (19, 6, 3, 6),  # Account Concentration (wider)
}


# ── Salesforce auth ────────────────────────────────────────────────────────


def get_credentials() -> dict[str, str]:
    p = subprocess.run(
        ["sf", "org", "display", "--json", "--target-org", TARGET_ORG],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        raise RuntimeError(f"sf org display failed:\n{p.stderr}")
    data = json.loads(p.stdout)["result"]
    return {"access_token": data["accessToken"], "instance_url": data["instanceUrl"].rstrip("/")}


def _api(method: str, path: str, token: str, instance: str, body: dict | None = None) -> dict:
    url = f"{instance}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            txt = resp.read().decode()
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {e.reason} {method} {path}\n{err[:1500]}") from e


# ── Transform ──────────────────────────────────────────────────────────────


def _strip_label_prefix(header: str) -> str:
    """Drop legacy '[Section] ' prefixes (KPI Strip / Pipeline Detail / etc.)."""
    if header.startswith("[") and "] " in header:
        return header.split("] ", 1)[1]
    return header


def _apply_severity_color(props: dict[str, Any], severity: str | None) -> None:
    """Inject visual severity hints. Conditional formatting (thresholds) on
    Metrics in Analytics REST is supported via `visualizationProperties`
    color fields when present; we set them best-effort. If the org rejects
    them silently, the metric still renders (just without color)."""
    if severity == "critical":
        color = RED
    elif severity == "important":
        color = AMBER
    elif severity == "kpi":
        color = NAVY
    else:
        return
    vp = props.setdefault("visualizationProperties", {})
    # These keys mirror what the SF dashboard editor writes for Metric
    # widgets. If the API ignores any, behavior degrades gracefully to
    # neutral text, which is still better than 16 identical bars.
    vp["metricFontColor"] = color
    vp["referenceLineColors"] = vp.get("referenceLineColors", [])
    # Conditional thresholds (count > 0 → colored).
    if severity in ("critical", "important"):
        vp["referenceLineValues"] = ["0"]
        vp["referenceLineColors"] = [color]


def transform_components(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mutate componentType + properties per WIDGET_SPEC. Returns a new list."""
    out: list[dict[str, Any]] = []
    for comp in components:
        rid = comp.get("reportId") or ""
        spec = WIDGET_SPEC.get(rid)
        new_comp = json.loads(json.dumps(comp))  # deep copy
        new_comp["header"] = _strip_label_prefix(new_comp.get("header") or "")
        if not spec:
            print(f"  [WARN] no spec for reportId {rid}; leaving as-is", file=sys.stderr)
            out.append(new_comp)
            continue
        viz = spec["viz"]
        props = new_comp.setdefault("properties", {})
        props["visualizationType"] = viz
        # Donut/Funnel/Column don't make sense with current grouping for some
        # reports, but the underlying report has the right shape (single
        # grouping, single sum). Salesforce will fall back to Bar at render
        # time if it disagrees — we accept that as graceful degradation.
        if viz == "Metric":
            # For Metric, the value is the grand-total aggregate. SF ignores
            # `groupings` for Metric viz. Strip them to avoid validator noise.
            props.pop("groupings", None)
            _apply_severity_color(props, spec["severity"])
        elif viz in ("Donut", "Funnel"):
            # Donut + Funnel need exactly one grouping; report already has one.
            pass
        elif viz == "Column":
            # Column is vertical bar; same data shape as Bar.
            pass
        out.append(new_comp)
    return out


def transform_layout(
    layout: dict[str, Any],
    components: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replace layout.components with re-packed positions per LAYOUT_BY_REPORT_ID.
    Indexes match `components` positionally (Analytics REST contract)."""
    new_layout = json.loads(json.dumps(layout))
    new_layout["gridLayout"] = True
    new_layout["numColumns"] = 12
    new_layout["rowHeight"] = layout.get("rowHeight", 36)
    positions: list[dict[str, int]] = []
    for comp in components:
        rid = comp.get("reportId") or ""
        pos = LAYOUT_BY_REPORT_ID.get(rid)
        if pos is None:
            # Fallback: tiny tile bottom-right corner
            positions.append({"row": 22, "column": 0, "rowspan": 2, "colspan": 3})
            continue
        row, col, rowspan, colspan = pos
        positions.append({"row": row, "column": col, "rowspan": rowspan, "colspan": colspan})
    new_layout["components"] = positions
    return new_layout


def build_patch_body(describe: dict[str, Any]) -> dict[str, Any]:
    new_components = transform_components(describe["components"])
    new_layout = transform_layout(describe.get("layout", {}), new_components)
    # PATCH body shape: same as POST (Analytics REST treats PATCH as a
    # full-resource replace for dashboards; partial bodies are rejected
    # with JSON_PARSER_ERROR in this org).
    return {
        "name": describe.get("name"),
        "description": describe.get("description"),
        "folderId": describe.get("folderId"),
        "dashboardType": describe.get("dashboardType"),
        "runningUser": describe.get("runningUser"),
        "chartTheme": describe.get("chartTheme"),
        "colorPalette": describe.get("colorPalette"),
        "components": new_components,
        "layout": new_layout,
    }


def viz_distribution(components: list[dict[str, Any]]) -> Counter:
    return Counter(c.get("properties", {}).get("visualizationType") or "?" for c in components)


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print PATCH body, do not send")
    ap.add_argument("--diff", action="store_true", help="show before/after viz mix only")
    args = ap.parse_args()

    creds = get_credentials()
    token, instance = creds["access_token"], creds["instance_url"]
    api_base = f"/services/data/v{API_VERSION}"

    print(f"[1/3] GET dashboard {DASHBOARD_ID}/describe")
    describe = _api(
        "GET", f"{api_base}/analytics/dashboards/{DASHBOARD_ID}/describe", token, instance
    )
    before = viz_distribution(describe["components"])
    print(f"  before: {dict(before)} ({sum(before.values())} widgets)")

    print("[2/3] Building patch body")
    body = build_patch_body(describe)
    after = viz_distribution(body["components"])
    print(f"  after:  {dict(after)} ({sum(after.values())} widgets)")

    if args.diff:
        return 0

    if args.dry_run:
        out_path = "/tmp/cockpit_patch_body.json"
        with open(out_path, "w") as f:
            json.dump(body, f, indent=2)
        print(f"[dry-run] PATCH body written to {out_path}")
        return 0

    print(f"[3/3] PATCH dashboard {DASHBOARD_ID}")
    try:
        _api("PATCH", f"{api_base}/analytics/dashboards/{DASHBOARD_ID}", token, instance, body=body)
    except RuntimeError as e:
        print(f"  [FAIL] {e}", file=sys.stderr)
        return 2

    # Verify
    verify = _api(
        "GET", f"{api_base}/analytics/dashboards/{DASHBOARD_ID}/describe", token, instance
    )
    actual = viz_distribution(verify["components"])
    print(f"  verified: {dict(actual)}")
    if actual != after:
        print(
            "  [WARN] org-side viz != requested. Likely silent fallback to Bar for unsupported pairings."
        )
    print(
        "  [OK] done. Open: https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxX2YMAV/view"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
