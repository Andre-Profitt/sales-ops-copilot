"""Phase 10 — scrub em-dashes from live SF report descriptions and dashboard
component headers/titles.

Em-dashes look sloppy in exec-facing artifacts. Replace with cleaner separators:
  ' — ' → '. ' (sentence break) or ': ' (label break)

This script targets just the metadata I created today (KPI reports, audit
reports, KPI tile components on SD Monthly + Sales Ops Q dashboards).

Usage:
  python3 -m scripts.sf_audit.scrub_emdashes --dry-run
  python3 -m scripts.sf_audit.scrub_emdashes
"""

from __future__ import annotations

import argparse
import logging
import sys

import requests

from scripts.sf_audit.reports import sf_session

logger = logging.getLogger("sf_audit.scrub_emdashes")

EMDASH = "—"

# Hardcoded clean text per report ID, keyed by what to update.
# Author-decided phrasing — beats any auto-clean heuristic.
REPORT_CLEAN: dict[str, dict[str, str]] = {
    # KPI reports (kpi_reports.py)
    "00OTb000008msSvMAI": {
        "description": "Closed-Lost Land+Expand opps in current quarter. ARR sum and count by stage where lost.",
    },
    "00OTb000008msZNMAY": {
        "description": "Opportunities entering Stage 3 or higher in last month. Governance volume KPI.",
    },
    # Audit reports (reports.py)
    "00OTb000008ms7xMAA": {
        "description": "Standard Contract objects in Status='Created' for >30 days; likely abandoned. 13,904 records identified by sf_audit/dq.py.",
    },
    "00OTb000008msBBMAY": {
        "description": "Opps with CloseDate<TODAY but IsClosed=false; slipped without status update.",
    },
    "00OTb000008mrn0MAA": {
        "description": "Open opps with CreatedDate >120d ago (target threshold). KPI median age in this org is 258d, 2x over.",
    },
    "00OTb000008msCnMAI": {
        "description": "Contacts where Email is null; cannot be reached via email. ~13.7K records.",
    },
}

# Hardcoded clean header per dashboard-component reportId.
COMPONENT_CLEAN: dict[str, str] = {
    "00OTb000008msSvMAI": "Lost ARR by Stage Where Lost",
    "00OTb000008msPhMAI": "Pipeline Concentration by Owner",
    "00OTb000008msW9MAI": "Pipeline Velocity by Type",
    "00OTb000008msZNMAY": "Governance Volume: Stage 3+ entry",
}


def clean(text: str) -> str:
    """Strip em-dash by replacing with simple separators when no override exists."""
    if not text or EMDASH not in text:
        return text
    return text.replace(f" {EMDASH} ", ", ").replace(EMDASH, "-")


def patch_report(instance: str, token: str, rid: str, dry_run: bool = False) -> bool:
    """Scrub em-dash from a report's description/name. Returns True if patched."""
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        f"{instance}/services/data/v65.0/analytics/reports/{rid}/describe",
        headers=headers,
        timeout=30,
    )
    if r.status_code != 200:
        return False
    md = r.json().get("reportMetadata") or {}
    name = md.get("name") or ""
    desc = md.get("description") or ""
    new_name = clean(name)
    # Hardcoded override beats heuristic when available
    if rid in REPORT_CLEAN and "description" in REPORT_CLEAN[rid]:
        new_desc = REPORT_CLEAN[rid]["description"]
    else:
        new_desc = clean(desc)
    if new_name == name and new_desc == desc:
        return False
    print(f"  {rid}")
    if new_name != name:
        print(f"    name:  {name!r} -> {new_name!r}")
    if new_desc != desc:
        print(f"    desc:  {desc[:60]!r}... -> {new_desc[:60]!r}...")
    if dry_run:
        return True
    md["name"] = new_name
    md["description"] = new_desc
    for ro in ("id", "type", "currency", "buckets", "crossFilters", "scope"):
        md.pop(ro, None)
    pr = requests.patch(
        f"{instance}/services/data/v65.0/analytics/reports/{rid}",
        headers={**headers, "Content-Type": "application/json"},
        json={"reportMetadata": md},
        timeout=60,
    )
    return pr.status_code in (200, 201)


def patch_dashboard_components(instance: str, token: str, did: str, dry_run: bool = False) -> int:
    """Scrub em-dashes from each component's header/title on a dashboard."""
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        f"{instance}/services/data/v65.0/analytics/dashboards/{did}/describe",
        headers=headers,
        timeout=30,
    )
    if r.status_code != 200:
        return 0
    md = r.json()
    components = list(md.get("components") or [])
    changed = 0
    for c in components:
        h = c.get("header") or ""
        t = c.get("title") or ""
        rid = c.get("reportId") or ""
        # Hardcoded override beats heuristic when available
        nh = COMPONENT_CLEAN.get(rid, clean(h))
        nt = clean(t)
        if nh != h or nt != t:
            changed += 1
            print(f"  [{did}] component {c.get('reportId', '?')}")
            if nh != h:
                print(f"    header: {h!r} -> {nh!r}")
            if nt != t:
                print(f"    title:  {t!r} -> {nt!r}")
            c["header"] = nh
            c["title"] = nt
    if changed and not dry_run:
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
        md["components"] = components
        pr = requests.patch(
            f"{instance}/services/data/v65.0/analytics/dashboards/{did}",
            headers={**headers, "Content-Type": "application/json"},
            json=md,
            timeout=60,
        )
        if pr.status_code not in (200, 201):
            print(f"  PATCH failed: {pr.status_code} {pr.text[:200]}")
            return 0
    return changed


# Reports I created today (full inventory).
REPORT_IDS = [
    # KPI reports (kpi_reports.py)
    "00OTb000008msO5MAI",  # Pipeline by Stage
    "00OTb000008msPhMAI",  # Pipeline by Owner
    "00OTb000008msRJMAY",  # Closed Won this Q
    "00OTb000008msSvMAI",  # Lost ARR this Q
    "00OTb000008msUXMAY",  # Renewal Pipeline ACV
    "00OTb000008msW9MAI",  # New Opps Last Month
    "00OTb000008msXlMAI",  # Won vs Lost this Q
    "00OTb000008msZNMAY",  # Stage 3+ this month
    # Audit reports (reports.py)
    "00OTb000008ms7xMAA",  # Stuck-Created Contracts
    "00OTb000008ms9ZMAQ",  # Stale Leads >1y
    "00OTb000008msBBMAY",  # Past-Close Open Opps
    "00OTb000008mrn0MAA",  # Stale Open Opps >120d
    "00OTb000008msCnMAI",  # Missing-Email Contacts
]

DASHBOARD_IDS = [
    "01ZTb00000FSP7hMAH",  # SD Monthly
    "01ZTb00000FSP9JMAX",  # Sales Ops Quarterly KPI
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrub em-dashes from SF reports + dashboards")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    instance, token, _ = sf_session()

    print(f"Scrubbing reports ({len(REPORT_IDS)}):")
    rep_changed = 0
    for rid in REPORT_IDS:
        if patch_report(instance, token, rid, dry_run=args.dry_run):
            rep_changed += 1
    print(f"  reports patched: {rep_changed}/{len(REPORT_IDS)}")

    print(f"\nScrubbing dashboards ({len(DASHBOARD_IDS)}):")
    dash_changed = 0
    for did in DASHBOARD_IDS:
        n = patch_dashboard_components(instance, token, did, dry_run=args.dry_run)
        if n:
            dash_changed += n
            print(f"  {did}: {n} components updated")
    print(f"  total components updated: {dash_changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
