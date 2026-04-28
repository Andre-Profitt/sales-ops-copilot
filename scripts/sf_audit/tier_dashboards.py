"""Phase 9 — tier the SD Monthly + Sales Ops Quarterly dashboards
between **Sales Director attention** (performance / KPIs) and **Sales Ops
attention** (governance / hygiene).

What moves where:

  SD Monthly (exec/director attention) — keeps:
    Pipeline by Stage, Renewals By Stage CFQ, Churn Risk, What was Won,
    Wins vs Losses, Renewal Pipeline This Q, Pipeline Stage Age, Lost ARR
    This Q, Pipeline by Owner, New Opps Last Month, Stage 3+ This Month
  + ADD 4 KPI Metric tiles:
    Open Pipeline ARR, Q-to-date Won ARR, Renewal Pipeline ACV, Lost ARR

  SD Monthly REMOVES (move to Sales Ops):
    Commercial Approval Queue, Commercial Approval Current State,
    Approved Deals YTD, Close Date Slipped YTD

  Sales Ops Quarterly KPI (Sales Ops attention) — keeps everything it has
  + ADDS the 4 governance widgets above.

Per phase 2.8 memory: dashboard COMPONENT PATCH works.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

import requests

from scripts.sf_audit.reports import sf_session
from scripts.sf_audit.rebuild_sd_dashboard import STANDARD_FILTER_COLS

logger = logging.getLogger("sf_audit.tier_dashboards")

SD_MONTHLY = "01ZTb00000FSP7hMAH"
SALES_OPS_Q = "01ZTb00000FSP9JMAX"

# Reports referenced by widgets we move FROM SD Monthly TO Sales Ops Q.
GOVERNANCE_REPORTS = {
    "00OTb000008ekp7MAA": "Commercial Approval Queue",
    "00OTb000008fBEDMA2": "Commercial Approval Current State",
    "00OTb000008aTtJMAU": "Approved Deals YTD",
    "00OTb000008eknVMAQ": "Close Date Slipped YTD",
}

# KPI reports we use as Metric-viz tile sources on SD Monthly.
KPI_TILES = [
    {
        "report_id": "00OTb000008msO5MAI",
        "header": "Open Pipeline ARR",
        "title": "This-Q Pipeline ARR (L+E)",
        "aggregate": "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
    },
    {
        "report_id": "00OTb000008msRJMAY",
        "header": "Q-to-Date Won ARR",
        "title": "Bookings This-Q (L+E)",
        "aggregate": "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
    },
    {
        "report_id": "00OTb000008msUXMAY",
        "header": "Renewal Pipeline ACV",
        "title": "This-Q Renewal ACV",
        "aggregate": "s!Opportunity.APTS_Renewal_ACV__c.CONVERT",
    },
    {
        "report_id": "00OTb000008msSvMAI",
        "header": "Lost ARR This-Q",
        "title": "Lost L+E This-Q",
        "aggregate": "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
    },
]


def metric_tile_component(
    *, header: str, title: str, report_id: str, aggregate: str
) -> dict[str, Any]:
    """Single-number Metric-viz widget."""
    return {
        "header": header,
        "footer": None,
        "title": title,
        "reportId": report_id,
        "type": "Report",
        "componentData": 0,
        "chartTheme": None,
        "properties": {
            "aggregates": [{"name": aggregate}],
            "autoSelectColumns": False,
            "drillUrl": None,
            "filterColumns": list(STANDARD_FILTER_COLS),
            "groupings": [],
            "maxRows": None,
            "reportFormat": "SUMMARY",
            "sort": None,
            "useReportChart": False,
            "visualizationProperties": {
                "decimalPrecision": 0,
                "displayUnits": "auto",
                "metric": aggregate,
                "showPercentages": False,
                "showValues": True,
            },
            "visualizationType": "Metric",
        },
    }


def get_dashboard(instance: str, token: str, did: str) -> dict[str, Any]:
    r = requests.get(
        f"{instance}/services/data/v65.0/analytics/dashboards/{did}/describe",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def patch_dashboard(instance: str, token: str, did: str, md: dict[str, Any]) -> None:
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
    r = requests.patch(
        f"{instance}/services/data/v65.0/analytics/dashboards/{did}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=md,
        timeout=60,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"PATCH {did} failed {r.status_code}: {r.text[:300]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Tier SD Monthly vs Sales Ops dashboards")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    instance, token, _ = sf_session()

    # ── SD Monthly: remove governance, add 4 Metric tiles ──────────
    sd_md = get_dashboard(instance, token, SD_MONTHLY)
    sd_components = list(sd_md.get("components") or [])
    print(f"\n=== SD Monthly ({SD_MONTHLY})")
    print(f"  before: {len(sd_components)} components")

    # Capture the governance components (full metadata) before removing —
    # we'll re-add them to Sales Ops Q with their exact properties.
    governance_components_to_move: list[dict[str, Any]] = []
    sd_kept = []
    for c in sd_components:
        rid = c.get("reportId")
        if rid in GOVERNANCE_REPORTS:
            governance_components_to_move.append(c)
            print(f"  REMOVE: {GOVERNANCE_REPORTS[rid]} (rid {rid})")
        else:
            sd_kept.append(c)
    # Add 4 Metric tiles at the BEGINNING of the components list so they
    # render at the top of the dashboard.
    new_metric_tiles = [metric_tile_component(**t) for t in KPI_TILES]
    sd_new_components = new_metric_tiles + sd_kept

    print(f"  ADD (Metric tiles): {len(new_metric_tiles)}")
    print(f"  after: {len(sd_new_components)} components")

    # ── Sales Ops Q: add the governance widgets ─────────────────────
    so_md = get_dashboard(instance, token, SALES_OPS_Q)
    so_components = list(so_md.get("components") or [])
    print(f"\n=== Sales Ops Quarterly KPI ({SALES_OPS_Q})")
    print(f"  before: {len(so_components)} components")

    # De-dup: only add a governance widget if Sales Ops Q doesn't already
    # have a component for that reportId.
    so_existing_rids = {c.get("reportId") for c in so_components}
    to_add = [c for c in governance_components_to_move if c.get("reportId") not in so_existing_rids]
    so_new_components = list(so_components) + to_add

    for c in to_add:
        print(f"  ADD: {GOVERNANCE_REPORTS.get(c.get('reportId'), '?')} (rid {c.get('reportId')})")
    skipped = len(governance_components_to_move) - len(to_add)
    if skipped:
        print(f"  (skipped {skipped} already present in Sales Ops Q)")
    print(f"  after: {len(so_new_components)} components")

    if args.dry_run:
        return 0

    # Build layouts via the auto-packer so we don't get overlap errors.
    # Inline imports to dodge the auto-formatter stripping them as "unused".
    from scripts.sf_audit.improve_dashboard_layout import (
        pack_layout as _pack,
        widget_size as _ws,
    )

    def autopack(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sizes = []
        for c in components:
            props = c.get("properties") or {}
            viz = props.get("visualizationType") or ""
            rf = props.get("reportFormat") or ""
            if viz == "Metric":
                sizes.append((3, 4))  # compact KPI tile
            else:
                sizes.append(_ws(viz, rf))
        return _pack(sizes)

    if to_add:
        so_md["components"] = so_new_components
        so_md["layout"] = {
            "components": autopack(so_new_components),
            "gridLayout": (so_md.get("layout") or {}).get("gridLayout"),
        }
        patch_dashboard(instance, token, SALES_OPS_Q, so_md)
        print(f"\n✓ Sales Ops Q: {len(to_add)} governance widgets added")

    sd_md["components"] = sd_new_components
    sd_md["layout"] = {
        "components": autopack(sd_new_components),
        "gridLayout": (sd_md.get("layout") or {}).get("gridLayout"),
    }
    patch_dashboard(instance, token, SD_MONTHLY, sd_md)
    print(f"✓ SD Monthly tiered: {SD_MONTHLY}")

    print("\nNext: run improve_dashboard_layout.py on both to reflow the grid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
