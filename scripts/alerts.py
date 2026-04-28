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

# SOQL fragment that excludes known test-bot artifacts from open-pipeline
# alert queries. Inlined here (rather than imported from _filters.py) so a
# code formatter can't strip the cross-file import.
#
# Verified 2026-04-28 — Maria Sabiniewicz owns 43 open opps totaling $16.7M
# ARR of QtC SOL test fixtures; CLM_SimCorp QtC* and QtC * are internal test
# orgs; Test/TEST*/ASH Dummy/SBL Opp%/Back Office are obvious test names.
#
# SOQL gotcha: `AND NOT field LIKE 'X'` is rejected. Each NOT must be wrapped
# in its own parens: `(NOT field LIKE 'X')`. To negate an OR-of-LIKEs, use
# De Morgan's law: NOT (A OR B) ≡ (NOT A) AND (NOT B).
EXCLUDE_TEST_ARTIFACTS = (
    "AND (NOT Owner.Name LIKE 'Maria Sabiniewicz%') "
    "AND ((NOT Account.Name LIKE 'CLM_SimCorp QtC%') "
    "AND (NOT Account.Name LIKE 'QtC %')) "
    "AND ((NOT Name = 'Test') AND (NOT Name LIKE 'TEST %') "
    "AND (NOT Name LIKE 'test_%') AND (NOT Name LIKE 'TEST_%') "
    "AND (NOT Name LIKE 'QTC_Test%') AND (NOT Name LIKE 'ASH Dummy%') "
    "AND (NOT Name LIKE 'SBL Opp%') AND (NOT Name = 'Back Office'))"
)


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
    """
    where = (
        f"IsClosed = false AND Type = 'Land' AND {LATE_STAGE_LIKE} "
        f"AND Stage_20_Approval__c = false {EXCLUDE_TEST_ARTIFACTS}{_ack_exclusion()}"
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
    """Land+Expand at Stage 3+ with ARR ≥$500k and no Commercial Approval."""
    where = (
        f"IsClosed = false AND Type IN ('Land','Expand') AND {LATE_STAGE_LIKE} "
        f"AND APTS_Opportunity_ARR__c >= 500000 AND Stage_20_Approval__c = false "
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
    close_date_in_past,
    dec_31_placeholder_dates,
    stale_activity,
    no_activity_ever,
    inactive_owner,
]


SEVERITY_ORDER = {"critical": 0, "important": 1, "info": 2, "error": 99}


def pull_owner_concentration(top_n: int = 10) -> list[dict[str, Any]]:
    """
    Roll up open-pipeline ARR by Owner across the deals that fall under
    *any* of the alert categories. Returns the top N owners by total ARR.

    Uses a single GROUP BY query that mirrors the union of the alert
    WHERE clauses (any deal that's: missing approval at Stage 3+, OR has
    a past close date, OR has Dec 31 placeholder, OR is stale 60d, OR
    has no activity ever, OR has inactive owner). This gives a complete
    view, not just the top-5 samples per alert.
    """
    union_where = (
        "IsClosed = false AND ("
        # Missing Commercial Approval on big deals
        f"  (Type IN ('Land','Expand') AND {LATE_STAGE_LIKE} "
        "    AND APTS_Opportunity_ARR__c >= 500000 "
        "    AND Stage_20_Approval__c = false) "
        # Land deals at Stage 3+ with no approval
        f"  OR (Type = 'Land' AND {LATE_STAGE_LIKE} AND Stage_20_Approval__c = false) "
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
    soql = (
        "SELECT Owner.Name owner_name, COUNT(Id) num_deals, "
        "SUM(APTS_Opportunity_ARR__c) total_arr "
        f"FROM Opportunity WHERE {union_where} "
        "GROUP BY Owner.Name "
        "ORDER BY SUM(APTS_Opportunity_ARR__c) DESC NULLS LAST "
        f"LIMIT {top_n}"
    )
    rows = _sf(soql)
    out: list[dict[str, Any]] = []
    for r in rows:
        owner = r.get("owner_name") or "—"
        out.append(
            {
                "owner": owner,
                "deal_count": r.get("num_deals", 0) or 0,
                "total_arr": r.get("total_arr") or 0,
            }
        )
    return out


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
