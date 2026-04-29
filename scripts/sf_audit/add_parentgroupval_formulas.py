"""Attempt to append a `% of grand total ARR` summary formula (FORMULA2) to
existing SimCorp cockpit reports that already use FORMULA1 and sum
Opportunity.APTS_Opportunity_ARR__c.CONVERT.

KNOWN LIMITATION (verified 2026-04-29 against simcorp.my.salesforce.com v66.0):
The Analytics REST API rejects every customSummaryFormula whose `formula`
contains PARENTGROUPVAL. Two reproducible 400 BAD_REQUEST responses:
  - downGroup=null + downGroupType='all'  →  "You must select a grouping
    context to use any report summary function" (specificErrorCode 113)
  - downGroup=<row-grouping-name> + any downGroupType  →  "Invalid custom
    summary formula grouping <NAME> for the given grouping type"
Tried downGroupType in {this, thisAndBelow, all, none, specific, grouping,
group, total, previous} and integer/named PGV second args — all rejected.
The Tooling API does not expose Report sObject (404). Net: PARENTGROUPVAL
formulas can only be added via the Lightning Reports UI (or Metadata API
zip-package retrieve/deploy, which is out of scope for this surgical edit).

The script below still does the safe portion: identify candidate reports,
attempt the PATCH, and report the rejection cleanly so a runbook can be
handed to the user for UI completion.

Strategy:
- Fetch /analytics/reports/{id}/describe
- Skip if FORMULA1 is absent (per task constraint) or if FORMULA2 already exists
- Append FORMULA2 to customSummaryFormula and to aggregates
- PATCH /analytics/reports/{id} with the mutated reportMetadata; on rejection,
  log the precise error and continue
- Verify post-PATCH by re-fetching describe and running the report instance

Usage: python3 -m scripts.sf_audit.add_parentgroupval_formulas
"""

from __future__ import annotations

import copy
import time
from typing import Any

import requests

from .reports import sf_session

API_VERSION = "v66.0"
ARR_AGG = "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT"
FORMULA2_KEY = "FORMULA2"
ARR_FIELD_SUM = "Opportunity.APTS_Opportunity_ARR__c.CONVERT:SUM"

# DeveloperName -> rationale; IDs resolved at runtime.
TARGETS: dict[str, str] = {
    "CRO_Quota_Attainment_YTD_v1": "by-rep ARR share of pipeline",
    "CRO_Coverage_X_By_Rep_v1": "by-rep coverage ARR share",
    "FA_Forecast_Accuracy_8Q_v1": "ARR share by fiscal quarter",
}

FORMULA2_DEF: dict[str, Any] = {
    "label": "% of Total ARR",
    "description": "Group ARR divided by grand-total ARR (FX-converted)",
    "formula": f"{ARR_FIELD_SUM} / PARENTGROUPVAL({ARR_FIELD_SUM}, GRAND_SUMMARY)",
    "formulaType": "percent",
    "decimalPlaces": 1,
    # Mirror FORMULA1's wrapper shape — every FORMULA1 created in
    # remediate_priority_dashboards.py uses these exact keys/values.
    "downGroup": None,
    "downGroupType": "all",
    "acrossGroup": None,
    "acrossGroupType": "all",
}


def _base(instance: str) -> str:
    return f"{instance}/services/data/{API_VERSION}"


def _resolve_targets(instance: str, headers: dict[str, str]) -> dict[str, str]:
    quoted = ",".join(f"'{n}'" for n in TARGETS)
    soql = f"SELECT Id, DeveloperName FROM Report WHERE DeveloperName IN ({quoted})"
    r = requests.get(f"{_base(instance)}/query", headers=headers, params={"q": soql}, timeout=60)
    r.raise_for_status()
    return {rec["DeveloperName"]: rec["Id"] for rec in r.json().get("records") or []}


def _describe(instance: str, headers: dict[str, str], rid: str) -> dict[str, Any]:
    r = requests.get(
        f"{_base(instance)}/analytics/reports/{rid}/describe", headers=headers, timeout=60
    )
    r.raise_for_status()
    return r.json()


def _patch(instance: str, headers: dict[str, str], rid: str, body: dict[str, Any]) -> None:
    r = requests.patch(
        f"{_base(instance)}/analytics/reports/{rid}", headers=headers, json=body, timeout=60
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"PATCH {rid} failed {r.status_code}: {r.text[:400]}")


def _run_report(instance: str, headers: dict[str, str], rid: str) -> dict[str, Any]:
    r = requests.post(
        f"{_base(instance)}/analytics/reports/{rid}/instances",
        headers=headers,
        json={},
        timeout=60,
    )
    r.raise_for_status()
    iid = r.json()["id"]
    body: dict[str, Any] = {}
    for _ in range(20):
        time.sleep(1.5)
        g = requests.get(
            f"{_base(instance)}/analytics/reports/{rid}/instances/{iid}",
            headers=headers,
            timeout=60,
        )
        g.raise_for_status()
        body = g.json()
        if (body.get("attributes") or {}).get("status") == "Success":
            return body
    return body


def _f2_grand_value(instance: str, headers: dict[str, str], rid: str) -> float | None:
    body = _run_report(instance, headers, rid)
    factmap = body.get("factMap") or {}
    grand = factmap.get("T!T") or {}
    aggregates = grand.get("aggregates") or []
    columns = (body.get("reportMetadata") or {}).get("aggregates") or []
    if FORMULA2_KEY not in columns:
        return None
    idx = columns.index(FORMULA2_KEY)
    if idx >= len(aggregates):
        return None
    val = aggregates[idx].get("value")
    return float(val) if isinstance(val, (int, float)) else None


def add_formula2(instance: str, headers: dict[str, str], rid: str, dn: str) -> str:
    desc = _describe(instance, headers, rid)
    md = copy.deepcopy(desc.get("reportMetadata") or {})
    csf = dict(md.get("customSummaryFormula") or {})
    aggs = list(md.get("aggregates") or [])

    if "FORMULA1" not in csf:
        return f"SKIP {dn} ({rid}): no FORMULA1 present"
    if FORMULA2_KEY in csf:
        return f"SKIP {dn} ({rid}): FORMULA2 already set"
    if ARR_AGG not in aggs:
        return f"SKIP {dn} ({rid}): ARR aggregate missing — would be a no-op"

    csf[FORMULA2_KEY] = copy.deepcopy(FORMULA2_DEF)
    md["customSummaryFormula"] = csf
    if FORMULA2_KEY not in aggs:
        aggs.append(FORMULA2_KEY)
    md["aggregates"] = aggs

    # The Analytics REST API rejects a few read-only / immutable keys on PATCH.
    for ro in ("id", "type", "currency", "buckets", "crossFilters", "scope"):
        md.pop(ro, None)

    try:
        _patch(instance, headers, rid, {"reportMetadata": md})
    except RuntimeError as e:
        # Expected: Analytics REST does not accept PARENTGROUPVAL formulas.
        return f"REJECT {dn} ({rid}): {e}"
    return f"PATCH {dn} ({rid}): FORMULA2 appended"


def verify(instance: str, headers: dict[str, str], rid: str, dn: str) -> str:
    md = _describe(instance, headers, rid).get("reportMetadata") or {}
    csf = md.get("customSummaryFormula") or {}
    aggs = md.get("aggregates") or []
    if FORMULA2_KEY not in csf or FORMULA2_KEY not in aggs:
        return f"VERIFY-FAIL {dn} ({rid}): FORMULA2 missing post-PATCH"
    try:
        val = _f2_grand_value(instance, headers, rid)
    except Exception as e:  # noqa: BLE001 — log + continue per task spec
        return f"VERIFY-FAIL {dn} ({rid}): run failed {e!r}"
    if val is None:
        return f"VERIFY-WARN {dn} ({rid}): FORMULA2 column present, no grand-summary value yet"
    if not (0.0 - 1e-6 <= val <= 1.0 + 1e-6):
        return f"VERIFY-WARN {dn} ({rid}): grand-summary FORMULA2={val} outside [0,1]"
    return f"VERIFY-OK   {dn} ({rid}): FORMULA2 grand-summary={val:.4f}"


def main() -> int:
    instance, token, _ = sf_session()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    resolved = _resolve_targets(instance, headers)
    missing = sorted(set(TARGETS) - set(resolved))
    if missing:
        print(f"WARN: unresolved DeveloperNames: {missing}")

    print("Targets:")
    for dn in TARGETS:
        rid = resolved.get(dn, "<missing>")
        print(f"  {rid}  {dn}  -- {TARGETS[dn]}")
    print()

    for dn, rid in resolved.items():
        print(add_formula2(instance, headers, rid, dn))

    print()
    for dn, rid in resolved.items():
        print(verify(instance, headers, rid, dn))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
