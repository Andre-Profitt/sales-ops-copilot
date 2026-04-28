"""Phase 5 — fix the underlying reports of the Sales Director Monthly dashboard.

Per the deep audit (state/sf_audit/dashboards/sd_monthly_reports_audit.json) +
SimCorp Commercial Handbook + ARR/ACV separation memory + _filters.py mirror:

CRITICAL FIXES:
  - 00OTb000008fBfdMAE (Pipeline Global CFQ — the hero widget): missing Type
    filter. Currently sums APTS_Opportunity_ARR__c across Land/Expand/Renewal,
    blending ARR+ACV. Add Type IN (Land, Expand).
  - 00OTb000008ektxMAA (Renewal Pipeline This Q): missing the ACV aggregate
    (only RowCount). Add s!Opportunity.APTS_Renewal_ACV__c.CONVERT.
  - 00OTb000008gUrVMAU (SD Win Rate by Stage): filters on "7 - Opt Out" which
    doesn't exist in this org's picklist. Drop that value.

POLLUTION FIXES (add owner-based test-bot exclusion to all reports lacking it):
  - 00OTb000008Ta9xMAC, 00OTb000008aTtJMAU, 00OTb000008ekp7MAA,
    00OTb000008ektxMAA, 00OTb000008fBEDMA2, 00OTb000008fBULMA2,
    00OTb000008fBfdMAE, 00OTb000008gUt7MAE — append FULL_NAME notContain
    Sabiniewicz filter.

NAME FIXES:
  - Renewals By Stager CFQ → Renewals By Stage CFQ (typo)

Usage:
  python3 -m scripts.sf_audit.fix_dashboard_reports             # apply all
  python3 -m scripts.sf_audit.fix_dashboard_reports --dry-run   # show patches only
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

import requests

from scripts.sf_audit.reports import _filter, sf_session

logger = logging.getLogger("sf_audit.fix_dashboard_reports")


def patch_report(
    instance: str, token: str, report_id: str, patch: dict[str, Any]
) -> dict[str, Any]:
    """PATCH a report's reportMetadata. Per Phase 2.8 memory, this works for
    aggregate / filter / column updates but not for filter-creation on
    dashboard-level filters (different code path)."""
    url = f"{instance}/services/data/v65.0/analytics/reports/{report_id}"
    # First GET the current state, then merge our patches and PATCH back.
    r = requests.get(url + "/describe", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code != 200:
        return {"ok": False, "error": f"GET failed: {r.status_code} {r.text[:200]}"}
    current = r.json().get("reportMetadata") or {}
    # Apply each patch field
    for k, v in patch.items():
        current[k] = v
    # Strip read-only fields that PATCH rejects
    for ro in (
        "id",
        "type",
        "currency",
        "buckets",
        "crossFilters",
        "customSummaryFormula",
        "scope",
    ):
        current.pop(ro, None)
    body = {"reportMetadata": current}
    r2 = requests.patch(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    if r2.status_code in (200, 201):
        return {"ok": True}
    return {"ok": False, "error": f"PATCH failed: {r2.status_code} {r2.text[:300]}"}


# Test-pollution filter — at least exclude the dominant test-bot owner.
# Other Sabiniewicz-style owners can be added if discovered later.
POLLUTION_FILTER = _filter("FULL_NAME", "notContain", "Sabiniewicz")


# Map report-id → list of patches to apply (each is a partial reportMetadata).
# Patches are applied in declaration order.
FIXES: list[dict[str, Any]] = [
    # ── Hero widget: Pipeline by Stage ────────────────────────────────
    {
        "id": "00OTb000008fBfdMAE",
        "label": "Pipeline Global CFQ — add Type IN (Land,Expand) and pollution filter",
        "patch_fn": "patch_pipeline_global",
    },
    # ── Renewal Pipeline This Quarter — add ACV aggregate + pollution ─
    {
        "id": "00OTb000008ektxMAA",
        "label": "Renewal Pipeline This Q — add ACV aggregate + pollution",
        "patch_fn": "patch_renewal_pipeline_q",
    },
    # ── Win Rate by Stage — drop non-existent "7 - Opt Out" ───────────
    {
        "id": "00OTb000008gUrVMAU",
        "label": "SD Win Rate by Stage — drop nonexistent '7 - Opt Out'",
        "patch_fn": "patch_win_rate_stage",
    },
    # ── Renewals By Stager CFQ — fix typo + add pollution ─────────────
    {
        "id": "00OTb000008fBULMA2",
        "label": "Renewals By Stage CFQ — fix typo, add pollution",
        "patch_fn": "patch_renewals_by_stage",
    },
    # ── Pollution-only patches (lighter-touch) ────────────────────────
    {
        "id": "00OTb000008Ta9xMAC",  # Churn Risk
        "label": "Churn Risk — add pollution filter",
        "patch_fn": "patch_pollution_only",
    },
    {
        "id": "00OTb000008aTtJMAU",  # Approved deals YTD
        "label": "Approved deals YTD — add pollution filter",
        "patch_fn": "patch_pollution_only",
    },
    {
        "id": "00OTb000008ekp7MAA",  # Commercial Approval Queue
        "label": "Commercial Approval Queue — add pollution filter",
        "patch_fn": "patch_pollution_only",
    },
    {
        "id": "00OTb000008fBEDMA2",  # Commercial Approval Current State
        "label": "Commercial Approval Current State — add pollution filter",
        "patch_fn": "patch_pollution_only",
    },
    {
        "id": "00OTb000008gUt7MAE",  # SD Days in Stage
        "label": "SD Days in Stage — strengthen pollution filter",
        "patch_fn": "patch_pollution_only",
    },
]


def patch_pipeline_global(current: dict[str, Any]) -> dict[str, Any]:
    """Add Type IN (Land,Expand) so ARR aggregate is meaningful.
    Append pollution filter."""
    filters = list(current.get("reportFilters") or [])
    # Skip if Type already present
    has_type = any(f.get("column") == "TYPE" for f in filters)
    if not has_type:
        filters.append(_filter("TYPE", "equals", "Land,Expand"))
    if not any(
        f.get("column") == "FULL_NAME" and "Sabiniewicz" in str(f.get("value", "")) for f in filters
    ):
        filters.append(POLLUTION_FILTER)
    return {"reportFilters": filters}


def patch_renewal_pipeline_q(current: dict[str, Any]) -> dict[str, Any]:
    """Add ACV aggregate + ACV in detailColumns + pollution."""
    aggs = list(current.get("aggregates") or [])
    if "s!Opportunity.APTS_Renewal_ACV__c.CONVERT" not in aggs:
        aggs.insert(0, "s!Opportunity.APTS_Renewal_ACV__c.CONVERT")
    cols = list(current.get("detailColumns") or [])
    if "Opportunity.APTS_Renewal_ACV__c.CONVERT" not in cols:
        cols.append("Opportunity.APTS_Renewal_ACV__c.CONVERT")
    filters = list(current.get("reportFilters") or [])
    if not any(
        f.get("column") == "FULL_NAME" and "Sabiniewicz" in str(f.get("value", "")) for f in filters
    ):
        filters.append(POLLUTION_FILTER)
    return {"aggregates": aggs, "detailColumns": cols, "reportFilters": filters}


def patch_win_rate_stage(current: dict[str, Any]) -> dict[str, Any]:
    """Replace nonexistent '7 - Opt Out' with handbook-aligned values."""
    filters = list(current.get("reportFilters") or [])
    new_filters = []
    for f in filters:
        if f.get("column") == "STAGE_NAME" and "Opt Out" in str(f.get("value", "")):
            f = dict(f)
            # Drop "7 - Opt Out" — not in this org's picklist.
            v = str(f.get("value", "")).replace(",7 - Opt Out", "").replace("7 - Opt Out,", "")
            f["value"] = v
        new_filters.append(f)
    return {"reportFilters": new_filters}


def patch_renewals_by_stage(current: dict[str, Any]) -> dict[str, Any]:
    """Fix the 'Stager' typo + add pollution."""
    name = current.get("name") or ""
    if "Stager" in name:
        current_name = name.replace("Stager", "Stage")
    else:
        current_name = name
    filters = list(current.get("reportFilters") or [])
    if not any(
        f.get("column") == "FULL_NAME" and "Sabiniewicz" in str(f.get("value", "")) for f in filters
    ):
        filters.append(POLLUTION_FILTER)
    return {"name": current_name, "reportFilters": filters}


def patch_pollution_only(current: dict[str, Any]) -> dict[str, Any]:
    """Just append the FULL_NAME notContain Sabiniewicz filter if not already there."""
    filters = list(current.get("reportFilters") or [])
    if any(
        f.get("column") == "FULL_NAME" and "Sabiniewicz" in str(f.get("value", "")) for f in filters
    ):
        return {}  # already filtered, no-op
    filters.append(POLLUTION_FILTER)
    return {"reportFilters": filters}


PATCH_FUNCTIONS = {
    "patch_pipeline_global": patch_pipeline_global,
    "patch_renewal_pipeline_q": patch_renewal_pipeline_q,
    "patch_win_rate_stage": patch_win_rate_stage,
    "patch_renewals_by_stage": patch_renewals_by_stage,
    "patch_pollution_only": patch_pollution_only,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix the SD Monthly dashboard reports")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", type=str, help="comma-sep report IDs")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    instance, token, _ = sf_session()
    fixes = FIXES
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        fixes = [f for f in fixes if f["id"] in wanted]

    print(f"Applying {len(fixes)} report fix(es) on {instance}\n")
    ok_count = 0
    for fix in fixes:
        rid = fix["id"]
        label = fix["label"]
        fn = PATCH_FUNCTIONS[fix["patch_fn"]]
        # GET current
        r = requests.get(
            f"{instance}/services/data/v65.0/analytics/reports/{rid}/describe",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if r.status_code != 200:
            print(f"✗ {rid}: GET failed {r.status_code}")
            continue
        current = r.json().get("reportMetadata", {})
        patch = fn(current)
        if not patch:
            print(f"⚪ {rid}: {label} — no-op (already fixed)")
            ok_count += 1
            continue
        if args.dry_run:
            print(f"☐ {rid}: {label}")
            print(f"  patch: {json.dumps(patch, default=str)[:300]}")
            continue
        result = patch_report(instance, token, rid, patch)
        if result["ok"]:
            print(f"✓ {rid}: {label}")
            ok_count += 1
        else:
            print(f"✗ {rid}: {label}")
            print(f"  {result['error'][:200]}")

    print(f"\nDone. {ok_count}/{len(fixes)} succeeded.")
    return 0 if ok_count == len(fixes) else 1


if __name__ == "__main__":
    sys.exit(main())
