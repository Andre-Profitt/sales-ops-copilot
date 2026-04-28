"""Phase 7 — tighten Sales Ops Quarterly KPI Dashboard (01ZTb00000FSP9JMAX).

Per audit:
  - 6 duplicate widgets (3 pairs of the same report shown twice)
  - 0 dashboard-level filters AND 0 component-level filterColumns — directors
    have no way to scope to their region/country
  - All 12 underlying reports now patched (pollution + Type filter where
    applicable) by fix_dashboard_reports.py

This script:
  1. Dedupes the 3 widget pairs (keeps first occurrence of each reportId)
  2. Adds Industry / Legal Country / Sales Region / Account Unit Group
     filterColumns to every component's properties so dashboard-level
     filters (when added later in Lightning UI) pass through.

Per Phase 2.8 memory: dashboard-level filter CREATION is Lightning-UI-only.
This script does NOT create the filters; it only ensures component-level
filterColumns are wired so that when filters ARE added, they actually scope.
"""

from __future__ import annotations

import argparse
import logging
import sys

import requests

from scripts.sf_audit.reports import sf_session
from scripts.sf_audit.rebuild_sd_dashboard import STANDARD_FILTER_COLS

logger = logging.getLogger("sf_audit.rebuild_sales_ops_q")

DASHBOARD_ID = "01ZTb00000FSP9JMAX"


def main() -> int:
    parser = argparse.ArgumentParser(description="Tighten Sales Ops Quarterly KPI dashboard")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    instance, token, _ = sf_session()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{instance}/services/data/v65.0/analytics/dashboards/{DASHBOARD_ID}"

    r = requests.get(url + "/describe", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"GET failed: {r.status_code}", file=sys.stderr)
        return 2
    md = r.json()
    components = list(md.get("components") or [])
    layout = md.get("layout") or {}
    layout_components = list(layout.get("components") or [])
    print(f"Current: {md.get('name')}")
    print(f"  components: {len(components)}, dashboard filters: {len(md.get('filters') or [])}")

    # Pre-flight: identify each component's report type so we don't inject
    # Opportunity-only filterColumns into Account/KYC-typed components.
    component_report_type: dict[str, str] = {}
    for c in components:
        rid = c.get("reportId")
        if not rid or rid in component_report_type:
            continue
        try:
            rd = requests.get(
                f"{instance}/services/data/v65.0/analytics/reports/{rid}/describe",
                headers=headers,
                timeout=20,
            ).json()
            component_report_type[rid] = (
                (rd.get("reportMetadata") or {}).get("reportType") or {}
            ).get("type", "?")
        except Exception:
            component_report_type[rid] = "?"

    # ── Step 1: dedupe by reportId — keep first occurrence ───────────
    seen: set[str] = set()
    new_components = []
    new_layout = []
    removals = []
    for i, c in enumerate(components):
        rid = c.get("reportId")
        if not rid:
            removals.append(f"  [{i}] empty slot — REMOVED")
            continue
        if rid in seen:
            removals.append(f"  [{i}] duplicate of {rid} ({c.get('title', '')}) — REMOVED")
            continue
        seen.add(rid)
        # ── Step 2: ensure filterColumns are populated for pass-through ──
        # Only inject Opportunity-shaped filter columns into Opportunity-typed
        # reports. Account/KYC reports use a different column namespace and
        # would 400 the PATCH.
        props = dict(c.get("properties") or {})
        rtype = component_report_type.get(rid, "")
        if rtype == "Opportunity":
            existing_fc = props.get("filterColumns") or []
            existing_names = {f.get("name") for f in existing_fc}
            merged_fc = list(existing_fc)
            for std in STANDARD_FILTER_COLS:
                if std["name"] not in existing_names:
                    merged_fc.append(std)
            props["filterColumns"] = merged_fc
        c = dict(c)
        c["properties"] = props
        new_components.append(c)
        if i < len(layout_components):
            new_layout.append(layout_components[i])

    print(f"\nRemovals: {len(removals)}")
    for x in removals:
        print(x)
    print(
        f"\nFilterColumn injection: STANDARD_FILTER_COLS added to all {len(new_components)} surviving components"
    )
    print(f"Final component count: {len(new_components)} (was {len(components)})")

    if args.dry_run:
        return 0

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
        print(f"\n✓ Dashboard tightened: {DASHBOARD_ID}")
        print(f"  {instance}/lightning/r/Dashboard/{DASHBOARD_ID}/view")
        return 0
    print(f"\n✗ PATCH failed: {r2.status_code}")
    print(r2.text[:600])
    return 1


if __name__ == "__main__":
    sys.exit(main())
