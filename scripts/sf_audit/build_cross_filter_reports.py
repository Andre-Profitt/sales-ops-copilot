"""Build two native SF cross-filter reports for the Sales Ops cockpit:

1. Cockpit_Zombie_v1 — open Land/Expand opps >2yr old with NO Activity in 60d
   (cross-filter: WITHOUT Activity where ActivityDate >= LAST_N_DAYS:60).
2. Cockpit_CoverageGap_v1 — Tier-A accounts with NO recent open Opportunity
   in 90d (cross-filter: WITHOUT Opportunity where IsClosed=false AND
   CreatedDate >= LAST_N_DAYS:90).

These two stand-alone reports replicate the SOQL+Python alerts in
`scripts/alerts.py` (`pipeline_aging_365_plus` family + a coverage-gap
notion that wasn't a discrete alert) as drillable Lightning reports.

Cross-filter shape was reverse-engineered from existing reports in the
preprod org (e.g. `00O2o000007lLVUEA2`) — the SF docs' `primaryTableColumn`
+ `relatedTable` shape returns JSON_PARSER_ERROR; the right shape is
`primaryEntityField` + `relatedEntity` + `relatedEntityJoinField` +
`includesObject:bool` + criteria with `column`+`entityName`.

Activity-related cross-filter MUST use `relatedEntity:"Activity"`
(Task / Event / OpenActivity / ActivityHistory all rejected). Activity is
the parent entity that joins via WhatId for both Tasks and Events, so a
single WITHOUT-Activity filter covers both per the task spec.

Account tier is `Account.Tier_Calculation__c = 'Tier 1'` (a calculated
formula field, values Tier 1..5). There is no "Tier A" picklist —
'Tier 1' is the SimCorp equivalent. Customer_Segment__c='A' is sparse
(29 accounts vs 1066 Tier 1) and not used.

AccountList reports require `scope:"organization"` to span the whole org;
sharing visibility on Account still narrows the result set heavily — known
behaviour, see `build_wave1_widgets.py` for the same caveat.

Idempotent: if a report with the target DeveloperName already exists, we
PATCH its metadata in place rather than POSTing a duplicate.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Any

import requests

from .reports import _filter, create_report, sf_session

API_VERSION = "v66.0"

ARR = "Opportunity.APTS_Opportunity_ARR__c.CONVERT"
sARR = f"s!{ARR}"


def _xf_criterion(column: str, entity: str, op: str, value: str) -> dict[str, Any]:
    """Cross-filter criterion: note `column` is the unprefixed API name and
    `entityName` carries the object — verified via probe of working report
    00O2o000007lLVUEA2 in preprod."""
    return {
        "column": column,
        "entityName": entity,
        "operator": op,
        "value": value,
        "filterType": "fieldValue",
        "isRunPageEditable": False,
    }


def _xfilter(
    primary: str,
    related: str,
    join: str,
    includes: bool,
    criteria: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "primaryEntityField": primary,
        "relatedEntity": related,
        "relatedEntityJoinField": join,
        "includesObject": includes,
        "criteria": criteria,
    }


def find_by_developer_name(instance: str, token: str, dev_name: str) -> str | None:
    headers = {"Authorization": f"Bearer {token}"}
    soql = f"SELECT Id FROM Report WHERE DeveloperName='{dev_name}' LIMIT 1"
    r = requests.get(
        f"{instance}/services/data/{API_VERSION}/query",
        headers=headers,
        params={"q": soql},
        timeout=20,
    )
    if r.status_code == 200:
        recs = r.json().get("records") or []
        if recs:
            return recs[0]["Id"]
    return None


def patch_report(instance: str, token: str, rid: str, metadata: dict[str, Any]) -> bool:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.patch(
        f"{instance}/services/data/{API_VERSION}/analytics/reports/{rid}",
        headers=headers,
        json={"reportMetadata": metadata},
        timeout=60,
    )
    if r.status_code in (200, 201):
        return True
    print(f"    PATCH {rid} failed {r.status_code}: {r.text[:300]}")
    return False


def run_instance(instance: str, token: str, rid: str) -> dict[str, Any]:
    """Kick off /instances and poll until Success/Error. Returns final json."""
    headers = {"Authorization": f"Bearer {token}"}
    inst = requests.post(
        f"{instance}/services/data/{API_VERSION}/analytics/reports/{rid}/instances",
        headers=headers,
        timeout=30,
    )
    if not inst.ok:
        return {"error": f"instance create failed {inst.status_code}: {inst.text[:200]}"}
    iid = inst.json().get("id")
    for _ in range(15):
        time.sleep(2)
        r = requests.get(
            f"{instance}/services/data/{API_VERSION}/analytics/reports/{rid}/instances/{iid}",
            headers=headers,
            timeout=30,
        )
        if not r.ok:
            continue
        j = r.json()
        st = j.get("attributes", {}).get("status")
        if st in ("Success", "Error"):
            return j
    return {"error": "timeout"}


def zombie_metadata() -> dict[str, Any]:
    return {
        "name": "Cockpit - Zombie (no Activity 60d)",
        "developerName": "Cockpit_Zombie_v1",
        "description": (
            "Open Land/Expand opportunities created >2 years ago with no Task or "
            "Event in the last 60 days. Cross-filter excludes any opp that has at "
            "least one Activity (Task or Event) with ActivityDate >= LAST_N_DAYS:60. "
            "ARR sums use s!field.CONVERT (FX-correct)."
        ),
        "reportFormat": "SUMMARY",
        "reportType": {"type": "Opportunity"},
        "detailColumns": [
            "OPPORTUNITY_NAME",
            "ACCOUNT_NAME",
            "STAGE_NAME",
            ARR,
            "CREATED_DATE",
            "CLOSE_DATE",
        ],
        "groupingsDown": [{"name": "FULL_NAME", "sortOrder": "Asc", "dateGranularity": "None"}],
        "aggregates": [sARR, "RowCount"],
        "reportFilters": [
            _filter("CLOSED", "equals", "0"),
            _filter("TYPE", "equals", "Land,Expand"),
            _filter("CREATED_DATE", "lessThan", "LAST_N_DAYS:730"),
        ],
        "sortBy": [{"sortColumn": ARR, "sortOrder": "Desc"}],
        "crossFilters": [
            _xfilter(
                primary="OPPORTUNITY_ID",
                related="Activity",
                join="WhatId",
                includes=False,
                criteria=[
                    _xf_criterion(
                        column="ActivityDate",
                        entity="Activity",
                        op="greaterOrEqual",
                        value="LAST_N_DAYS:60",
                    )
                ],
            )
        ],
        "standardDateFilter": {
            "column": "CREATED_DATE",
            "durationValue": "CUSTOM",
            "startDate": None,
            "endDate": None,
        },
    }


def coverage_gap_metadata() -> dict[str, Any]:
    return {
        "name": "Cockpit - Coverage Gap (Tier-A 90d)",
        "developerName": "Cockpit_CoverageGap_v1",
        "description": (
            "Tier-1 accounts with no open Opportunity in the last 90 days. "
            "Tier-A = Tier_Calculation__c='Tier 1'. AccountList scope=organization."
        ),
        "reportFormat": "SUMMARY",
        "reportType": {"type": "AccountList"},
        "scope": "organization",
        "detailColumns": ["ACCOUNT.NAME", "Account.Tier_Calculation__c"],
        "groupingsDown": [
            {"name": "Account.Region__c", "sortOrder": "Asc", "dateGranularity": "None"}
        ],
        "aggregates": ["RowCount"],
        "reportFilters": [
            _filter("Account.Tier_Calculation__c", "equals", "Tier 1"),
        ],
        "crossFilters": [
            _xfilter(
                primary="ACCOUNT_ID",
                related="Opportunity",
                join="AccountId",
                includes=False,
                criteria=[
                    _xf_criterion(
                        column="IsClosed",
                        entity="Opportunity",
                        op="equals",
                        value="false",
                    ),
                    _xf_criterion(
                        column="CreatedDate",
                        entity="Opportunity",
                        op="greaterOrEqual",
                        value="LAST_N_DAYS:90",
                    ),
                ],
            )
        ],
    }


def upsert_report(instance: str, token: str, metadata: dict[str, Any]) -> str:
    """Idempotent: PATCH if DeveloperName exists, else POST then PATCH-rename.

    POST `developerName` is rejected ("invalid parameter value") on SF Reports
    REST in v66 — SF derives it from `name`. We POST without it, then PATCH the
    derived report to set the canonical Cockpit_*_v1 dev name.
    """
    dev = metadata["developerName"]
    existing = find_by_developer_name(instance, token, dev)
    if existing:
        patch_md = dict(metadata)
        for ro in ("reportType", "scope", "type", "id"):
            patch_md.pop(ro, None)
        if patch_report(instance, token, existing, patch_md):
            print(f"  PATCHED existing {dev} -> {existing}")
        return existing

    # POST without developerName (SF auto-derives from name)
    post_md = dict(metadata)
    post_md.pop("developerName", None)
    result = create_report(instance, token, post_md)
    if not result.get("ok"):
        raise RuntimeError(f"create {dev} failed: {result.get('error', '?')[:300]}")
    rid = result["id"]
    # PATCH-rename to canonical developerName
    rename_md = dict(metadata)
    for ro in ("reportType", "scope", "type", "id"):
        rename_md.pop(ro, None)
    if patch_report(instance, token, rid, rename_md):
        print(f"  CREATED + renamed {dev} -> {rid}")
    else:
        print(f"  CREATED {rid} but rename to {dev} failed (auto-name kept)")
    return rid


def verify(instance: str, token: str, rid: str, label: str) -> str:
    j = run_instance(instance, token, rid)
    if j.get("error"):
        return f"{label}: VERIFY FAILED — {j['error']}"
    fm = j.get("factMap", {}).get("T!T", {})
    agg = fm.get("aggregates") or []
    status = j.get("attributes", {}).get("status")
    return f"{label}: status={status} aggregates={agg}"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    instance, token, _ = sf_session()

    print("=== Cockpit cross-filter reports ===")
    zid = upsert_report(instance, token, zombie_metadata())
    cid = upsert_report(instance, token, coverage_gap_metadata())

    print("\n=== Verifying instances ===")
    print(" ", verify(instance, token, zid, f"Cockpit_Zombie_v1 ({zid})"))
    print(" ", verify(instance, token, cid, f"Cockpit_CoverageGap_v1 ({cid})"))

    print("\nLightning URLs:")
    print(f"  Zombie:        {instance}/lightning/r/Report/{zid}/view")
    print(f"  Coverage Gap:  {instance}/lightning/r/Report/{cid}/view")
    return 0


if __name__ == "__main__":
    sys.exit(main())
