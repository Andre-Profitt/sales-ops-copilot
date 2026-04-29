#!/usr/bin/env python3
"""
Sales Ops alerts — detect governance + hygiene issues from open Salesforce
pipeline. Each alert returns a count, total impact ($ARR or $ACV), and a
sample of top affected opportunities.

Anchored on the SimCorp Commercial Handbook 8-stage process and the
canonical ARR/ACV split rule. No CRMA dependency.
"""

from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from typing import Any

LATE_STAGE_LIKE = (
    "(StageName LIKE '3%' OR StageName LIKE '4%' OR StageName LIKE '5%' OR StageName LIKE '6%')"
)

# Test-pollution exclusion clause is canonical in scripts/_filters.py.
# Same module is mirrored in account-drilldown/scripts/_filters.py — the two
# files MUST stay byte-identical (verify via scripts/check_filters_sync.py).
#
# sys.path is augmented in brief.py before this module is imported, so the
# import works whether alerts.py is run as a script or imported as a module.
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _filters import EXCLUDE_TEST_ARTIFACTS  # type: ignore[import-not-found,import-untyped]  # noqa: E402


@lru_cache(maxsize=1)
def _ack_exclusion() -> str:
    """Acked opp IDs to exclude from alert queries. Cached per-process; call
    `_ack_exclusion.cache_clear()` after mutating state/acknowledged.json."""
    try:
        from ack import soql_exclusion  # type: ignore[import-not-found]

        return soql_exclusion()
    except Exception:
        return ""


def _sf(soql: str) -> list[dict[str, Any]]:
    """Run SOQL via sf CLI, return record list (stdout-only to avoid CLI warnings)."""
    p = subprocess.run(
        ["sf", "data", "query", "--query", soql, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        return []
    try:
        return json.loads(p.stdout).get("result", {}).get("records", [])
    except json.JSONDecodeError:
        return []


def _agg(soql: str) -> dict[str, Any]:
    rows = _sf(soql)
    return rows[0] if rows else {}


def _sample(soql: str, limit: int = 5) -> list[dict[str, Any]]:
    return _sf(f"{soql} LIMIT {limit}")


def commercial_approval_gap_land() -> dict[str, Any]:
    """Land deals at Stage 3+ without Commercial Approval. Per the SimCorp
    Commercial Handbook, Commercial Approval is mandatory for ALL Land deals.

    Truth field is `Opportunity.Approval_Status__c` (picklist: No Approval
    Necessary / Needs Approval / Awaiting Approval / Approved / Rejected).
    The boolean `Stage_20_Approval__c` is a derived flag that fires false on
    34,618 opps where no approval is required — same lying-boolean shape as
    the KYC bug. Verified 2026-04-28: all 26 opps the boolean-only predicate
    flagged today had Approval_Status__c='No Approval Necessary' (Union AM,
    OPF, BBVA AM, ERS Texas, etc.). Corrected predicate co-conditions on the
    picklist so we only fire on opps actually in the approval queue.
    """
    where = (
        f"IsClosed = false AND Type = 'Land' AND {LATE_STAGE_LIKE} "
        "AND Stage_20_Approval__c = false "
        "AND Approval_Status__c IN ('Needs Approval','Awaiting Approval','Rejected') "
        f"{EXCLUDE_TEST_ARTIFACTS}{_ack_exclusion()}"
    )
    agg = _agg(
        "SELECT COUNT(Id) num, SUM(APTS_Opportunity_ARR__c) total_arr "
        f"FROM Opportunity WHERE {where}"
    )
    samples = _sample(
        "SELECT Id, Name, StageName, APTS_Opportunity_ARR__c, Owner.Name "
        f"FROM Opportunity WHERE {where} ORDER BY APTS_Opportunity_ARR__c DESC NULLS LAST"
    )
    return {
        "name": "Land deals at Stage 3+ without Commercial Approval",
        "severity": "critical",
        "rule": "Per SimCorp Commercial Handbook, ALL Land deals require Commercial Approval before Stage 3.",
        "count": agg.get("num", 0) or 0,
        "total_arr": agg.get("total_arr") or 0,
        "samples": _format_samples(samples, "ARR"),
    }


def commercial_approval_gap_big() -> dict[str, Any]:
    """Land+Expand at Stage 3+ with ARR ≥$500k and no Commercial Approval.

    Same truth-field correction as `commercial_approval_gap_land` — gate on
    `Approval_Status__c` picklist, not on the standalone boolean. Boolean-only
    predicate was flagging 104 opps / $141.8M ARR all with
    Approval_Status__c='No Approval Necessary' (verified 2026-04-28).
    """
    where = (
        f"IsClosed = false AND Type IN ('Land','Expand') AND {LATE_STAGE_LIKE} "
        "AND APTS_Opportunity_ARR__c >= 500000 AND Stage_20_Approval__c = false "
        "AND Approval_Status__c IN ('Needs Approval','Awaiting Approval','Rejected') "
        f"{EXCLUDE_TEST_ARTIFACTS}{_ack_exclusion()}"
    )
    agg = _agg(
        "SELECT COUNT(Id) num, SUM(APTS_Opportunity_ARR__c) total_arr "
        f"FROM Opportunity WHERE {where}"
    )
    samples = _sample(
        "SELECT Id, Name, StageName, APTS_Opportunity_ARR__c, Owner.Name "
        f"FROM Opportunity WHERE {where} ORDER BY APTS_Opportunity_ARR__c DESC NULLS LAST"
    )
    return {
        "name": "Stage 3+ Land/Expand deals ≥$500k ARR without Commercial Approval",
        "severity": "critical",
        "rule": "Expand deals with AER >€500k require Commercial Approval per the handbook.",
        "count": agg.get("num", 0) or 0,
        "total_arr": agg.get("total_arr") or 0,
        "samples": _format_samples(samples, "ARR"),
    }


def close_date_in_past() -> dict[str, Any]:
    """Open opps with close date in the past — distorts every pipeline view."""
    where = f"IsClosed = false AND CloseDate < TODAY {EXCLUDE_TEST_ARTIFACTS}{_ack_exclusion()}"
    agg = _agg(
        "SELECT COUNT(Id) num, SUM(APTS_Opportunity_ARR__c) total_arr "
        f"FROM Opportunity WHERE {where}"
    )
    samples = _sample(
        "SELECT Id, Name, StageName, CloseDate, APTS_Opportunity_ARR__c, Owner.Name "
        f"FROM Opportunity WHERE {where} ORDER BY CloseDate ASC"
    )
    return {
        "name": "Open opportunities with close date in the past",
        "severity": "critical",
        "rule": "Open opps with past CloseDate distort pipeline + forecast views.",
        "count": agg.get("num", 0) or 0,
        "total_arr": agg.get("total_arr") or 0,
        "samples": _format_samples(samples, "ARR", extra="CloseDate"),
    }


def dec_31_placeholder_dates() -> dict[str, Any]:
    """Stage 3+ open opps with CloseDate = December 31 — placeholder dates."""
    where = (
        f"IsClosed = false AND {LATE_STAGE_LIKE} "
        f"AND CALENDAR_MONTH(CloseDate) = 12 AND DAY_IN_MONTH(CloseDate) = 31 "
        f"{EXCLUDE_TEST_ARTIFACTS}{_ack_exclusion()}"
    )
    agg = _agg(
        "SELECT COUNT(Id) num, SUM(APTS_Opportunity_ARR__c) total_arr "
        f"FROM Opportunity WHERE {where}"
    )
    samples = _sample(
        "SELECT Id, Name, StageName, CloseDate, APTS_Opportunity_ARR__c, Owner.Name "
        f"FROM Opportunity WHERE {where} ORDER BY APTS_Opportunity_ARR__c DESC NULLS LAST"
    )
    return {
        "name": "Stage 3+ opps with December 31 close dates (placeholder)",
        "severity": "important",
        "rule": "Dec 31 close dates are typical placeholders that inflate Q4 forecast.",
        "count": agg.get("num", 0) or 0,
        "total_arr": agg.get("total_arr") or 0,
        "samples": _format_samples(samples, "ARR", extra="CloseDate"),
    }


def stale_activity() -> dict[str, Any]:
    """Stage 3+ open opps with no activity in 60+ days."""
    where = (
        f"IsClosed = false AND {LATE_STAGE_LIKE} AND LastActivityDate < LAST_N_DAYS:60 "
        f"{EXCLUDE_TEST_ARTIFACTS}{_ack_exclusion()}"
    )
    agg = _agg(
        "SELECT COUNT(Id) num, SUM(APTS_Opportunity_ARR__c) total_arr "
        f"FROM Opportunity WHERE {where}"
    )
    samples = _sample(
        "SELECT Id, Name, StageName, LastActivityDate, APTS_Opportunity_ARR__c, Owner.Name "
        f"FROM Opportunity WHERE {where} ORDER BY APTS_Opportunity_ARR__c DESC NULLS LAST"
    )
    return {
        "name": "Stage 3+ opportunities with no activity in 60+ days",
        "severity": "important",
        "rule": "Late-stage deals without recent activity are stalling or should be marked lost.",
        "count": agg.get("num", 0) or 0,
        "total_arr": agg.get("total_arr") or 0,
        "samples": _format_samples(samples, "ARR", extra="LastActivityDate"),
    }


def no_activity_ever() -> dict[str, Any]:
    """Stage 3+ open opps that have NEVER had a logged activity."""
    where = (
        f"IsClosed = false AND {LATE_STAGE_LIKE} AND LastActivityDate = null "
        f"{EXCLUDE_TEST_ARTIFACTS}{_ack_exclusion()}"
    )
    agg = _agg(
        "SELECT COUNT(Id) num, SUM(APTS_Opportunity_ARR__c) total_arr "
        f"FROM Opportunity WHERE {where}"
    )
    samples = _sample(
        "SELECT Id, Name, StageName, CreatedDate, APTS_Opportunity_ARR__c, Owner.Name "
        f"FROM Opportunity WHERE {where} ORDER BY APTS_Opportunity_ARR__c DESC NULLS LAST"
    )
    return {
        "name": "Stage 3+ opportunities with no logged activity ever",
        "severity": "important",
        "rule": "Late-stage deals without ANY recorded activity are zombies — high data-quality risk.",
        "count": agg.get("num", 0) or 0,
        "total_arr": agg.get("total_arr") or 0,
        "samples": _format_samples(samples, "ARR", extra="CreatedDate"),
    }


def kyc_gap_late_stage() -> dict[str, Any]:
    """Land/Expand at Stage 5+ (Preferred or Contracting) without KYC clearance.

    KYC source-of-truth is `Account.KYC_Approval_Status__c` (picklist:
    Approved / Approval Requested / Not Started / On Hold). NOT
    `Opportunity.KYC_Approval_Message__c` — that boolean is some unrelated
    message-display flag and was emitting massive false positives (e.g.,
    UBS / Fidelity / Generali, all KYC-Approved at the Account level).
    Verified 2026-04-28.

    Per the SimCorp Commercial Handbook, KYC clearance is a closing-stage
    gate; a deal can't actually close without it. Stage 5+ scopes this to
    deals that should have KYC done by now.
    """
    where = (
        "IsClosed = false AND Type IN ('Land','Expand') "
        "AND (StageName LIKE '5%' OR StageName LIKE '6%') "
        "AND Account.KYC_Approval_Status__c != 'Approved' "
        f"{EXCLUDE_TEST_ARTIFACTS}{_ack_exclusion()}"
    )
    agg = _agg(
        "SELECT COUNT(Id) num, SUM(APTS_Opportunity_ARR__c) total_arr "
        f"FROM Opportunity WHERE {where}"
    )
    samples = _sample(
        "SELECT Id, Name, StageName, APTS_Opportunity_ARR__c, Owner.Name "
        f"FROM Opportunity WHERE {where} ORDER BY APTS_Opportunity_ARR__c DESC NULLS LAST"
    )
    return {
        "name": "Stage 5+ Land/Expand without KYC clearance",
        "severity": "critical",
        "rule": "KYC clearance is a closing-stage gate. Deals at Preferred/Contracting without KYC cannot actually close.",
        "count": agg.get("num", 0) or 0,
        "total_arr": agg.get("total_arr") or 0,
        "samples": _format_samples(samples, "ARR"),
    }


def approval_submitted_pending() -> dict[str, Any]:
    """Stage 3+ deals where Commercial Approval has been SUBMITTED but not yet
    granted. Distinct from 'no approval' (which catches never-submitted).
    Useful as an in-queue signal — these need follow-through, not new submission.

    The submit boolean fires even on opps that don't require approval, so
    co-condition on `Approval_Status__c` to ensure the deal is actually
    in-queue. Verified 2026-04-28: all 6 opps the boolean-only predicate
    flagged today had Approval_Status__c='No Approval Necessary' — same
    lying-boolean shape as Stage_20_Approval__c. 'Rejected' excluded from
    the canonical filter because that's a terminal state, not "still pending".
    """
    where = (
        f"IsClosed = false AND {LATE_STAGE_LIKE} "
        "AND Submit_for_Stage_20_Review__c = true "
        "AND Stage_20_Approval__c = false "
        "AND Approval_Status__c IN ('Needs Approval','Awaiting Approval') "
        f"{EXCLUDE_TEST_ARTIFACTS}{_ack_exclusion()}"
    )
    agg = _agg(
        "SELECT COUNT(Id) num, SUM(APTS_Opportunity_ARR__c) total_arr "
        f"FROM Opportunity WHERE {where}"
    )
    samples = _sample(
        "SELECT Id, Name, StageName, APTS_Opportunity_ARR__c, Owner.Name, "
        "Submit_for_Stage_20_Review_Date__c "
        f"FROM Opportunity WHERE {where} ORDER BY Submit_for_Stage_20_Review_Date__c ASC NULLS LAST"
    )
    return {
        "name": "Commercial Approval submitted but not yet granted",
        "severity": "info",
        "rule": "Distinct from 'no approval' — these are in the review queue and need follow-through, not a new submission.",
        "count": agg.get("num", 0) or 0,
        "total_arr": agg.get("total_arr") or 0,
        "samples": _format_samples(samples, "ARR", extra="Submit_for_Stage_20_Review_Date__c"),
    }


def deal_shaping_gap() -> dict[str, Any]:
    """Land/Expand at Stage 5+ without Deal Shaping approval. Per the SimCorp
    Commercial Handbook, Deal Services Design (Deal Shaping) is mandatory before
    Final Review.

    Same lying-boolean pathology as the Commercial Approval fields:
    `Deal_Shaping_Approved__c=false` on 764 of 795 closed-won Land/Expand
    deals in the last 365d (96%) — the field is functionally abandoned.
    Boolean-only predicate flagged 67 opps / $29.9M ARR today, all with
    Approval_Status__c='No Approval Necessary' (verified 2026-04-28).
    Corrected predicate co-conditions on the picklist; this currently
    yields zero flags, which is the right behaviour until the canonical
    Deal Shaping signal is identified (likely a separate object or CPQ
    flag — TODO follow-up).
    """
    where = (
        "IsClosed = false AND Type IN ('Land','Expand') "
        "AND (StageName LIKE '5%' OR StageName LIKE '6%') "
        "AND Deal_Shaping_Approved__c = false "
        "AND Approval_Status__c IN ('Needs Approval','Awaiting Approval','Rejected') "
        f"{EXCLUDE_TEST_ARTIFACTS}{_ack_exclusion()}"
    )
    agg = _agg(
        "SELECT COUNT(Id) num, SUM(APTS_Opportunity_ARR__c) total_arr "
        f"FROM Opportunity WHERE {where}"
    )
    samples = _sample(
        "SELECT Id, Name, StageName, APTS_Opportunity_ARR__c, Owner.Name "
        f"FROM Opportunity WHERE {where} ORDER BY APTS_Opportunity_ARR__c DESC NULLS LAST"
    )
    return {
        "name": "Stage 5+ Land/Expand without Deal Shaping approval",
        "severity": "important",
        "rule": "Deal Services Design (Deal Shaping) is mandatory before Final Review per the Commercial Handbook.",
        "count": agg.get("num", 0) or 0,
        "total_arr": agg.get("total_arr") or 0,
        "samples": _format_samples(samples, "ARR"),
    }


def inactive_owner() -> dict[str, Any]:
    """Open opps owned by an inactive Salesforce user — alerts go nowhere."""
    where = (
        f"IsClosed = false AND Owner.IsActive = false {EXCLUDE_TEST_ARTIFACTS}{_ack_exclusion()}"
    )
    agg = _agg(
        "SELECT COUNT(Id) num, SUM(APTS_Opportunity_ARR__c) total_arr "
        f"FROM Opportunity WHERE {where}"
    )
    samples = _sample(
        "SELECT Id, Name, StageName, APTS_Opportunity_ARR__c, Owner.Name "
        f"FROM Opportunity WHERE {where} ORDER BY APTS_Opportunity_ARR__c DESC NULLS LAST"
    )
    return {
        "name": "Open opportunities owned by inactive Salesforce user",
        "severity": "important",
        "rule": "Owner offboarded — no one is actually managing these deals.",
        "count": agg.get("num", 0) or 0,
        "total_arr": agg.get("total_arr") or 0,
        "samples": _format_samples(samples, "ARR"),
    }


# --- formatting -------------------------------------------------------------


def _format_samples(records: list[dict], metric: str, extra: str | None = None) -> list[dict]:
    out = []
    for r in records:
        owner = (r.get("Owner") or {}).get("Name", "—")
        amt = r.get("APTS_Opportunity_ARR__c") or 0
        item = {
            "id": r.get("Id"),
            "name": r.get("Name"),
            "stage": r.get("StageName"),
            "owner": owner,
            f"${metric.lower()}": amt,
        }
        if extra and r.get(extra):
            item[extra.lower()] = r[extra]
        out.append(item)
    return out


# --- driver -----------------------------------------------------------------

ALERT_FUNCTIONS = [
    commercial_approval_gap_land,
    commercial_approval_gap_big,
    kyc_gap_late_stage,
    close_date_in_past,
    dec_31_placeholder_dates,
    deal_shaping_gap,
    stale_activity,
    no_activity_ever,
    approval_submitted_pending,
    inactive_owner,
]


SEVERITY_ORDER = {"critical": 0, "important": 1, "info": 2, "error": 99}


def _flagged_union_where() -> str:
    """SOQL union WHERE that matches any open opp falling under at least one
    alert category. Shared by owner-concentration and account-concentration
    rollups so they always use the same predicate as `pull_all_alerts`."""
    return (
        "IsClosed = false AND ("
        # Missing Commercial Approval on big deals (gated by picklist)
        f"  (Type IN ('Land','Expand') AND {LATE_STAGE_LIKE} "
        "    AND APTS_Opportunity_ARR__c >= 500000 "
        "    AND Stage_20_Approval__c = false "
        "    AND Approval_Status__c IN ('Needs Approval','Awaiting Approval','Rejected')) "
        # Land deals at Stage 3+ with no approval (gated by picklist)
        f"  OR (Type = 'Land' AND {LATE_STAGE_LIKE} AND Stage_20_Approval__c = false "
        "       AND Approval_Status__c IN ('Needs Approval','Awaiting Approval','Rejected')) "
        # KYC missing at Stage 5+
        "  OR (Type IN ('Land','Expand') "
        "       AND (StageName LIKE '5%' OR StageName LIKE '6%') "
        "       AND Account.KYC_Approval_Status__c != 'Approved') "
        # Deal Shaping missing at Stage 5+ (gated by picklist)
        "  OR (Type IN ('Land','Expand') "
        "       AND (StageName LIKE '5%' OR StageName LIKE '6%') "
        "       AND Deal_Shaping_Approved__c = false "
        "       AND Approval_Status__c IN ('Needs Approval','Awaiting Approval','Rejected')) "
        # Past close date
        "  OR (CloseDate < TODAY) "
        # Dec 31 placeholder at Stage 3+
        f"  OR ({LATE_STAGE_LIKE} AND CALENDAR_MONTH(CloseDate) = 12 "
        "       AND DAY_IN_MONTH(CloseDate) = 31) "
        # Stale 60d at Stage 3+
        f"  OR ({LATE_STAGE_LIKE} AND LastActivityDate < LAST_N_DAYS:60) "
        # No activity ever at Stage 3+
        f"  OR ({LATE_STAGE_LIKE} AND LastActivityDate = null) "
        # Inactive owner
        "  OR (Owner.IsActive = false) "
        ") "
        f"{EXCLUDE_TEST_ARTIFACTS}{_ack_exclusion()}"
    )


def pull_owner_concentration(top_n: int = 10) -> list[dict[str, Any]]:
    """Roll up flagged-opp ARR by Owner. Returns top N owners by total ARR."""
    soql = (
        "SELECT Owner.Name owner_name, COUNT(Id) num_deals, "
        "SUM(APTS_Opportunity_ARR__c) total_arr "
        f"FROM Opportunity WHERE {_flagged_union_where()} "
        "GROUP BY Owner.Name "
        "ORDER BY SUM(APTS_Opportunity_ARR__c) DESC NULLS LAST "
        f"LIMIT {top_n}"
    )
    rows = _sf(soql)
    return [
        {
            "owner": r.get("owner_name") or "—",
            "deal_count": r.get("num_deals", 0) or 0,
            "total_arr": r.get("total_arr") or 0,
        }
        for r in rows
    ]


def pull_account_concentration(top_n: int = 15) -> list[dict[str, Any]]:
    """Roll up flagged-opp ARR by Account. Returns top N accounts by total ARR.

    Same union predicate as `pull_owner_concentration` — pivots the same set
    of flagged opps from the rep dimension to the account dimension. Useful
    for "where is the governance debt actually concentrated?" — directors
    typically think in accounts, not reps.
    """
    soql = (
        "SELECT Account.Name account_name, COUNT(Id) num_deals, "
        "SUM(APTS_Opportunity_ARR__c) total_arr "
        f"FROM Opportunity WHERE {_flagged_union_where()} "
        "GROUP BY Account.Name "
        "ORDER BY SUM(APTS_Opportunity_ARR__c) DESC NULLS LAST "
        f"LIMIT {top_n}"
    )
    rows = _sf(soql)
    return [
        {
            "account": r.get("account_name") or "—",
            "deal_count": r.get("num_deals", 0) or 0,
            "total_arr": r.get("total_arr") or 0,
        }
        for r in rows
    ]


def deduplicate_samples(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Each opp can be flagged by multiple alerts (e.g., a deal that's both
    Stage 3+ ≥$500k no-approval AND has Dec 31 placeholder close date).
    This dedupes the samples lists so each opp appears in only ONE alert's
    samples — the highest-severity / first-listed one — with an
    'also_flagged_in' tag pointing to the other alerts that match it.

    Counts and total_arr per alert are NOT modified — those are still the
    full set; only the displayed samples are deduped.
    """
    # Build the full opp_id → set-of-alert-names map first (across all samples).
    opp_to_alerts: dict[str, list[str]] = {}
    for a in alerts:
        for s in a.get("samples") or []:
            opp_id = s.get("id")
            if not opp_id:
                continue
            opp_to_alerts.setdefault(opp_id, []).append(a["name"])

    # Process alerts in severity order so critical wins primary placement.
    sorted_alerts = sorted(
        range(len(alerts)),
        key=lambda i: (SEVERITY_ORDER.get(alerts[i].get("severity", ""), 99), i),
    )

    seen: set[str] = set()
    for idx in sorted_alerts:
        a = alerts[idx]
        kept: list[dict[str, Any]] = []
        for s in a.get("samples") or []:
            opp_id = s.get("id")
            if not opp_id or opp_id in seen:
                continue
            seen.add(opp_id)
            also_in = [n for n in opp_to_alerts.get(opp_id, []) if n != a["name"]]
            if also_in:
                s["also_flagged_in"] = also_in
            kept.append(s)
        a["samples"] = kept

    return alerts


def pull_all_alerts() -> list[dict[str, Any]]:
    """Run every alert and return only the ones with count > 0."""
    results: list[dict[str, Any]] = []
    for fn in ALERT_FUNCTIONS:
        try:
            r = fn()
            if r.get("count", 0) > 0:
                results.append(r)
        except Exception as e:
            results.append(
                {
                    "name": fn.__name__,
                    "severity": "error",
                    "error": str(e)[:200],
                    "count": 0,
                    "total_arr": 0,
                    "samples": [],
                }
            )
    return deduplicate_samples(results)


if __name__ == "__main__":
    alerts = pull_all_alerts()
    print(f"Found {len(alerts)} active alerts:\n")
    for a in alerts:
        print(f"[{a['severity'].upper()}] {a['name']}")
        print(f"  count: {a['count']} | total: ${a['total_arr']:,.0f}")
        if a.get("samples"):
            print(f"  top: {a['samples'][0].get('name')} (${a['samples'][0].get('$arr', 0):,.0f})")
        print()
