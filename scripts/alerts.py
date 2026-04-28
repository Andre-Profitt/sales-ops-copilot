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
from typing import Any

LATE_STAGE_LIKE = (
    "(StageName LIKE '3%' OR StageName LIKE '4%' OR StageName LIKE '5%' OR StageName LIKE '6%')"
)


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
        f"IsClosed = false AND Type = 'Land' AND {LATE_STAGE_LIKE} AND Stage_20_Approval__c = false"
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
        "AND APTS_Opportunity_ARR__c >= 500000 AND Stage_20_Approval__c = false"
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
    where = "IsClosed = false AND CloseDate < TODAY"
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
        "AND CALENDAR_MONTH(CloseDate) = 12 AND DAY_IN_MONTH(CloseDate) = 31"
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
    where = f"IsClosed = false AND {LATE_STAGE_LIKE} AND LastActivityDate < LAST_N_DAYS:60"
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
    where = f"IsClosed = false AND {LATE_STAGE_LIKE} AND LastActivityDate = null"
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
    where = "IsClosed = false AND Owner.IsActive = false"
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


def pull_all_alerts() -> list[dict[str, Any]]:
    """Run every alert and return only the ones with count > 0."""
    results = []
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
    return results


if __name__ == "__main__":

    alerts = pull_all_alerts()
    print(f"Found {len(alerts)} active alerts:\n")
    for a in alerts:
        print(f"[{a['severity'].upper()}] {a['name']}")
        print(f"  count: {a['count']} | total: ${a['total_arr']:,.0f}")
        if a.get("samples"):
            print(f"  top: {a['samples'][0].get('name')} (${a['samples'][0].get('$arr', 0):,.0f})")
        print()
