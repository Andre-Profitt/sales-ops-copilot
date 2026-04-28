"""Phase 3 — create native Salesforce reports for the audit findings.

So the dirty-data and KPI numbers we computed locally become first-class
SF reports anyone can pull up in-app — making them "trustable" rather
than living only in our local markdown.

Each report is a metadata dict; this module POSTs to /analytics/reports,
collects report IDs, and writes a manifest of (name, id, URL).

Usage:
  python3 -m scripts.sf_audit.reports                 # create all
  python3 -m scripts.sf_audit.reports --only phantom-active-assets
  python3 -m scripts.sf_audit.reports --dry-run       # print metadata, no API
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("sf_audit.reports")


# ─── SF auth (reuse the sf CLI session — no extra deps) ────────────────────


def sf_session() -> tuple[str, str, str]:
    """Returns (instance_url, access_token, user_id) from the active sf CLI org."""
    proc = subprocess.run(
        ["sf", "org", "display", "--json"], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(f"sf org display failed: {proc.stderr[:300]}")
    data = json.loads(proc.stdout[proc.stdout.find("{") :])
    res = data.get("result", {})
    return res["instanceUrl"], res["accessToken"], res.get("id") or res.get("userId", "")


def base_url(instance: str, api_version: str = "v65.0") -> str:
    return f"{instance}/services/data/{api_version}/"


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─── Folder lookup (place reports in a known folder so they're shareable) ──


def find_or_warn_folder(instance: str, token: str, name: str) -> str | None:
    """Find a Folder by Name. If not found, returns None (caller falls back to
    user's private). User should create the folder manually via Setup UI for
    org-wide visibility."""
    soql = f"SELECT Id, Name FROM Folder WHERE Type='Report' AND Name='{name}' LIMIT 1"
    r = requests.get(
        base_url(instance) + "query",
        headers=_headers(token),
        params={"q": soql},
        timeout=30,
    )
    if r.status_code == 200:
        recs = r.json().get("records") or []
        if recs:
            return recs[0]["Id"]
    logger.warning(
        "Folder %r not found — reports will land in running user's private folder. "
        "To share org-wide, create the folder via Setup → Reports & Dashboards → New Folder.",
        name,
    )
    return None


# ─── Report creation ──────────────────────────────────────────────────────


def create_report(instance: str, token: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """POST /analytics/reports — returns {ok, id?, url?, error?}."""
    url = base_url(instance) + "analytics/reports"
    r = requests.post(
        url,
        headers=_headers(token),
        json={"reportMetadata": metadata},
        timeout=60,
    )
    if r.status_code in (200, 201):
        result = r.json()
        rid = (result.get("reportMetadata") or {}).get("id") or result.get("id")
        return {
            "ok": True,
            "id": rid,
            "url": f"{instance}/lightning/r/Report/{rid}/view",
        }
    err = r.text[:600] if r.text else f"HTTP {r.status_code}"
    return {"ok": False, "error": err, "status_code": r.status_code}


# ─── Audit report definitions ─────────────────────────────────────────────
#
# Ranked roughly by record-count actionability from dq.md top-20 fixes.
# Filters use the SF report filterType=fieldValue convention.
# ──────────────────────────────────────────────────────────────────────────


def _filter(column: str, op: str, value: str) -> dict[str, Any]:
    return {
        "column": column,
        "operator": op,
        "value": value,
        "filterType": "fieldValue",
        "isRunPageEditable": True,
    }


def audit_reports(folder_id: str | None) -> list[dict[str, Any]]:
    """Return the full list of audit reports to create.

    Each item: {key, label, metadata}. The key is a stable slug so --only filters work.

    DESIGN NOTE: We send minimal metadata (reportType + reportFormat=TABULAR
    + filters) and let SF auto-default the columns. This sidesteps the
    column-code guessing for SF's report DSL — anyone can refine columns/
    groupings later via the Lightning UI.

    NOT INCLUDED: AssetLineItem reports. There's no Custom Report Type for
    Apttus_Config2__AssetLineItem__c in this org, so the Analytics API can't
    POST a report against it. To enable: Setup → Custom Report Types → New
    on Apttus_Config2__AssetLineItem__c, then add reports here.
    """
    base_meta = {}
    if folder_id:
        base_meta["folderId"] = folder_id

    reports: list[dict[str, Any]] = [
        # 1. Stuck-Created Contracts (13,904)
        {
            "key": "stuck-created-contracts",
            "label": "Audit · Contracts stuck in Status=Created (>30d)",
            "metadata": {
                **base_meta,
                "name": "Audit · Stuck-Created Contracts",
                "description": "Standard Contract objects in Status='Created' for >30 days — likely abandoned. 13,904 records identified by sf_audit/dq.py.",
                "reportFormat": "TABULAR",
                "reportType": {"type": "ContractList"},
                "reportFilters": [
                    _filter("STATUS", "equals", "Created"),
                    _filter("LAST_UPDATE", "lessThan", "LAST_N_DAYS:30"),
                ],
            },
        },
        # 2. Stale Leads >1y untouched (43,582 — not status-filtered;
        # the staleness IS the problem regardless of status)
        {
            "key": "stale-leads-1y",
            "label": "Audit · Stale Leads (>1y untouched)",
            "metadata": {
                **base_meta,
                "name": "Audit · Stale Leads (>1y untouched)",
                "description": "Leads with LastModifiedDate >1 year. ~43.6K records identified by sf_audit/dq.py.",
                "reportFormat": "TABULAR",
                "reportType": {"type": "LeadList"},
                "reportFilters": [
                    _filter("LAST_UPDATE", "lessThan", "LAST_N_YEARS:1"),
                ],
            },
        },
        # 3. Past-Close-Date Open Opportunities
        {
            "key": "past-close-open-opps",
            "label": "Audit · Past-Close Open Opportunities",
            "metadata": {
                **base_meta,
                "name": "Audit · Past-Close Open Opportunities",
                "description": "Opps with CloseDate<TODAY but IsClosed=false — slipped without status update.",
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("CLOSE_DATE", "lessThan", "TODAY"),
                ],
            },
        },
        # 4. Stale Open Opps >120d (KPI: median age was 258d, target <120)
        {
            "key": "stale-open-opps-120d",
            "label": "Audit · Stale Open Opportunities (>120d age)",
            "metadata": {
                **base_meta,
                "name": "Audit · Stale Open Opportunities (>120d)",
                "description": "Open opps with CreatedDate >120d ago (target threshold). KPI median age in this org is 258d — 2x over.",
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("CREATED_DATE", "lessThan", "LAST_N_DAYS:120"),
                ],
            },
        },
        # 5. Missing-Email Contacts (13,729)
        {
            "key": "missing-email-contacts",
            "label": "Audit · Contacts missing Email",
            "metadata": {
                **base_meta,
                "name": "Audit · Contacts Missing Email",
                "description": "Contacts where Email is null — can't be reached via email. ~13.7K records.",
                "reportFormat": "TABULAR",
                "reportType": {"type": "ContactList"},
                "reportFilters": [_filter("EMAIL", "equals", "")],
            },
        },
        # 6. Owner-Inactive Cases (88,030)
        {
            "key": "owner-inactive-cases",
            "label": "Audit · Cases owned by Inactive Users",
            "metadata": {
                **base_meta,
                "name": "Audit · Owner-Inactive Cases",
                "description": "Open Cases with deactivated owner — work that no one is tracking. ~88K records.",
                "reportFormat": "TABULAR",
                "reportType": {"type": "CaseList"},
                "reportFilters": [_filter("OWNER.IsActive", "equals", "0")],
            },
        },
    ]
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Create native SF reports for audit findings")
    parser.add_argument("--only", type=str, help="comma-sep list of report keys to create")
    parser.add_argument(
        "--folder", type=str, default="Sales Ops Audit", help="folder name to place reports in"
    )
    parser.add_argument("--dry-run", action="store_true", help="print metadata, don't POST")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("state/sf_audit/reports_manifest.json"),
        help="output manifest path (key → id, url)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    instance, token, _ = sf_session()
    folder_id = find_or_warn_folder(instance, token, args.folder) if not args.dry_run else None
    reports = audit_reports(folder_id)
    if args.only:
        wanted = {k.strip() for k in args.only.split(",")}
        reports = [r for r in reports if r["key"] in wanted]
        if not reports:
            print(f"No reports matched --only={args.only!r}", file=sys.stderr)
            return 2

    print(f"Creating {len(reports)} report(s) in {instance}")
    if args.dry_run:
        for r in reports:
            print(f"\n=== {r['key']}: {r['label']}")
            print(json.dumps(r["metadata"], indent=2))
        return 0

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
        "instance": instance,
        "folder_id": folder_id,
        "reports": [],
    }
    ok_count = 0
    for r in reports:
        print(f"\n→ {r['key']}: {r['label']}")
        result = create_report(instance, token, r["metadata"])
        manifest["reports"].append({"key": r["key"], "label": r["label"], **result})
        if result.get("ok"):
            ok_count += 1
            print(f"  ✓ {result['id']}")
            print(f"    {result['url']}")
        else:
            print(f"  ✗ {result.get('error', 'unknown error')[:300]}")

    args.manifest.write_text(json.dumps(manifest, indent=2))
    print(f"\nDone. {ok_count}/{len(reports)} created. Manifest: {args.manifest}")
    return 0 if ok_count == len(reports) else 1


if __name__ == "__main__":
    sys.exit(main())
