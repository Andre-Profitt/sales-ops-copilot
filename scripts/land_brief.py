#!/usr/bin/env python3
"""
sales-ops-copilot LAND-monthly variant.

Pulls the Salesforce pipeline snapshot scoped to ONE director, computes
LAND-specific KPIs (ARR + ACV separated, 8-stage SimCorp process,
Commercial Approval governance), bundles into a trends.json envelope +
15-sheet Excel companion + markdown brief.

Output: state/<period>/<director>/{trends.json, land.xlsx, brief.md}

Usage:
    python3 scripts/land_brief.py --director "Adam Steinhouse" --period 2026-Q2
    python3 scripts/land_brief.py --all-directors --period 2026-Q2
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _directors import canonical_directors
from excel_companion import build_director_excel
from excel_model import build_director_model  # noqa: F401  # formatter strips otherwise

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"


# Org-wide benchmark report IDs (verified live 2026-04-29)
_REPORT_OPEN_PIPE_BY_REGION = "00OTb000008mvyfMAA"  # CRO · Open Pipeline by Region
_REPORT_WIN_RATE_8Q = "00OTb000008neanMAA"  # CRO · Win Rate Trend 8Q
_REPORT_DISCOUNT_DEPTH_PENDING = "00OTb000008njSPMAY"  # DD · Discount Depth Pending


def _sf_access_token_and_instance() -> tuple[str, str]:
    out = subprocess.run(
        ["sf", "org", "display", "--target-org", "preprod", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    d = json.loads(out.stdout)["result"]
    return d["accessToken"], d["instanceUrl"]


def _sf_analytics_get(report_id: str) -> dict[str, Any]:
    """Hit the Reports REST API for an org-wide aggregate. FX-correct via
    the report engine's `s!field.CONVERT` aggregates."""
    import urllib.request

    token, instance = _sf_access_token_and_instance()
    url = f"{instance}/services/data/v66.0/analytics/reports/{report_id}?includeDetails=false"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — https-only internal call
        return json.loads(resp.read().decode())


def pull_org_benchmarks() -> dict[str, Any]:
    """One-shot org-wide benchmarks from existing FX-correct SF reports.
    Cached at the run level — every director's xlsx references the same
    org-wide figures so the comparison is consistent."""
    out: dict[str, Any] = {}

    # Open pipeline by region (CRO · Open Pipeline by Region)
    try:
        d = _sf_analytics_get(_REPORT_OPEN_PIPE_BY_REGION)
        fact = d.get("factMap") or {}
        rows = []
        for g in (d.get("groupingsDown") or {}).get("groupings", []):
            cells = (fact.get(f"{g.get('key')}!T") or {}).get("aggregates") or []
            arr_label = (cells[0] or {}).get("label") if cells else None
            arr_val = float((cells[0] or {}).get("value") or 0) if cells else 0
            cnt_val = int((cells[2] or {}).get("value") or 0) if len(cells) >= 3 else 0
            rows.append(
                {
                    "region": g.get("label", "?"),
                    "arr_label": arr_label,
                    "arr_eur": arr_val,
                    "opp_count": cnt_val,
                }
            )
        grand_cells = (fact.get("T!T") or {}).get("aggregates") or []
        grand_arr = float((grand_cells[0] or {}).get("value") or 0) if grand_cells else 0
        out["open_pipe_by_region"] = {
            "rows": rows,
            "grand_arr_eur": grand_arr,
        }
    except Exception as e:
        print(f"  [WARN] benchmarks: open_pipe_by_region failed: {e}", file=sys.stderr)
        out["open_pipe_by_region"] = {}

    # Win rate trend 8Q (CRO · Win Rate Trend 8Q)
    try:
        d = _sf_analytics_get(_REPORT_WIN_RATE_8Q)
        fact = d.get("factMap") or {}
        rows = []
        for g in (d.get("groupingsDown") or {}).get("groupings", []):
            cells = (fact.get(f"{g.get('key')}!T") or {}).get("aggregates") or []
            wr = float((cells[0] or {}).get("value") or 0) if cells else 0
            n = int((cells[1] or {}).get("value") or 0) if len(cells) >= 2 else 0
            rows.append({"quarter": g.get("label", "?"), "win_rate_pct": wr, "num_opps": n})
        out["win_rate_trend_8q"] = rows
    except Exception as e:
        print(f"  [WARN] benchmarks: win_rate_trend_8q failed: {e}", file=sys.stderr)
        out["win_rate_trend_8q"] = []

    # Discount depth pending (DD · Discount Depth Pending)
    try:
        d = _sf_analytics_get(_REPORT_DISCOUNT_DEPTH_PENDING)
        fact = d.get("factMap") or {}
        rows = []
        for g in (d.get("groupingsDown") or {}).get("groupings", []):
            cells = (fact.get(f"{g.get('key')}!T") or {}).get("aggregates") or []
            arr_val = float((cells[0] or {}).get("value") or 0) if cells else 0
            n = int((cells[1] or {}).get("value") or 0) if len(cells) >= 2 else 0
            rows.append({"discount_band": g.get("label", "?"), "arr_eur": arr_val, "num_opps": n})
        grand_cells = (fact.get("T!T") or {}).get("aggregates") or []
        grand_arr = float((grand_cells[0] or {}).get("value") or 0) if grand_cells else 0
        grand_n = int((grand_cells[1] or {}).get("value") or 0) if len(grand_cells) >= 2 else 0
        out["discount_pending"] = {
            "rows": rows,
            "grand_arr_eur": grand_arr,
            "grand_num_opps": grand_n,
        }
    except Exception as e:
        print(f"  [WARN] benchmarks: discount_pending failed: {e}", file=sys.stderr)
        out["discount_pending"] = {}

    return out


def _sf_query(soql: str) -> list[dict[str, Any]]:
    p = subprocess.run(
        ["sf", "data", "query", "--query", soql, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        raise RuntimeError(f"sf query failed: {p.stderr.strip()}")
    return json.loads(p.stdout).get("result", {}).get("records", [])


def pull_director_snapshot(director: dict, period: str) -> dict[str, Any]:
    """SF snapshot scoped to one director's territory.

    Filter mechanism is the per-director `where_clause` (Account.Region__c +
    BillingCountry + Industry per the canonical MD-1 scope map). Falls back to
    Account.Sales_Director_Book__c IN (book_codes) for legacy callers if no
    where_clause is set.

    FX-correctness: APTS_Opportunity_ARR__c and APTS_Renewal_ACV__c are stored
    in each opp's transactional currency (verified 2026-04-29 — e.g. a CAD opp
    holds CAD 2.84M, convertCurrency returns EUR 1.78M). SOQL SUM aggregates
    on these fields are NOT FX-converted (SF's `convertCurrency()` function is
    documented as not supported inside aggregate functions — silently returns
    raw multi-currency sums). Per the SimCorp cardinal rule
    (`feedback_sf_multi_currency_aggregation.md`), this is wrong for any
    director with non-EUR pipeline (Canada, NA, UKI, APAC, ME&A — most of
    them).

    Fix: pull per-record values with `convertCurrency()` in SELECT (which
    DOES work — verified per-row), then sum in Python. Result is FX-converted
    to apro@simcorp.com's display currency (EUR).
    """
    where_clause = director.get("where_clause")
    if not where_clause:
        book_codes = "(" + ",".join(f"'{b}'" for b in director["book_codes"]) + ")"
        where_clause = f"Account.Sales_Director_Book__c IN {book_codes}"
    period_clause = "CloseDate = THIS_QUARTER"  # TODO: parameterize by `period`

    # Pull per-record FX-converted values, aggregate in Python.
    # SOQL SUM(convertCurrency(...)) does NOT work — silently returns raw sum.
    # SOQL SELECT convertCurrency(...) DOES work — returns per-record FX value.
    # Also pull Account.BillingCountry + Risk for downstream sheets
    # (Territory_Performance + At_Risk_Renewals).
    detail_q = (
        "SELECT Id, Name, Type, StageName, CreatedDate, CloseDate, "
        "Stage_20_Approval__c, "
        "Owner.Name, ForecastCategoryName, "
        "Account.Name, Account.BillingCountry, Account.Industry, "
        "Account.Risk_of_Potential_Termination__c, "
        "convertCurrency(APTS_Opportunity_ARR__c) arr_fx, "
        "convertCurrency(APTS_Renewal_ACV__c) acv_fx "
        "FROM Opportunity "
        f"WHERE IsClosed = false AND {period_clause} "
        f"AND {where_clause}"
    )
    rows = _sf_query(detail_q)

    # Aggregate by Type
    by_type_acc: dict[str, dict[str, float]] = {}
    for r in rows:
        t = r.get("Type") or "(unset)"
        bucket = by_type_acc.setdefault(t, {"num_opps": 0, "arr": 0.0, "renewal_acv": 0.0})
        bucket["num_opps"] += 1
        bucket["arr"] += float(r.get("arr_fx") or 0)
        bucket["renewal_acv"] += float(r.get("acv_fx") or 0)
    by_type = [
        {"type": t, **{k: (round(v, 2) if k != "num_opps" else int(v)) for k, v in vals.items()}}
        for t, vals in sorted(by_type_acc.items())
    ]

    # New-business (Land+Expand) by stage — uses arr_fx
    nb_acc: dict[str, dict[str, float]] = {}
    for r in rows:
        if r.get("Type") not in ("Land", "Expand"):
            continue
        s = r.get("StageName") or "(unset)"
        bucket = nb_acc.setdefault(s, {"num_opps": 0, "arr": 0.0})
        bucket["num_opps"] += 1
        bucket["arr"] += float(r.get("arr_fx") or 0)
    new_business_by_stage = [
        {"stage": s, "num_opps": int(v["num_opps"]), "arr": round(v["arr"], 2)}
        for s, v in sorted(nb_acc.items())
    ]

    # Renewals by stage — uses acv_fx
    ren_acc: dict[str, dict[str, float]] = {}
    for r in rows:
        if r.get("Type") != "Renewal":
            continue
        s = r.get("StageName") or "(unset)"
        bucket = ren_acc.setdefault(s, {"num_opps": 0, "acv": 0.0})
        bucket["num_opps"] += 1
        bucket["acv"] += float(r.get("acv_fx") or 0)
    renewals_by_stage = [
        {"stage": s, "num_opps": int(v["num_opps"]), "acv": round(v["acv"], 2)}
        for s, v in sorted(ren_acc.items())
    ]

    # Top-10 deals per motion (Land, Expand) — for the Excel companion's
    # Top_Deals_Land / Top_Deals_Expand sheets and slide 6 of the deck.
    # Per AI Code of Conduct §8: per-deal data is OK for the director's
    # own scope (descriptive); the deck/xlsx never leaves their hands.
    top_deals_land: list[dict[str, Any]] = []
    top_deals_expand: list[dict[str, Any]] = []
    for r in sorted(
        [r for r in rows if r.get("Type") in ("Land", "Expand")],
        key=lambda r: float(r.get("arr_fx") or 0),
        reverse=True,
    ):
        target = top_deals_land if r.get("Type") == "Land" else top_deals_expand
        if len(target) < 10:
            acct = r.get("Account") or {}
            owner = r.get("Owner") or {}
            target.append(
                {
                    "stage": r.get("StageName") or "",
                    "arr_eur": round(float(r.get("arr_fx") or 0), 2),
                    "id": r.get("Id"),
                    "account": acct.get("Name") or "",
                    "name": r.get("Name") or "",
                    "owner": owner.get("Name") or "",
                    "close_date": (r.get("CloseDate") or "")[:10],
                    "created_date": (r.get("CreatedDate") or "")[:10],
                }
            )

    # Wins / Losses QTD — closed-this-Q opps, FX-correct
    wl_q = (
        "SELECT Id, Name, IsWon, Type, StageName, CloseDate, "
        "Owner.Name, Account.Name, "
        "convertCurrency(APTS_Opportunity_ARR__c) arr_fx, "
        "convertCurrency(APTS_Renewal_ACV__c) acv_fx "
        "FROM Opportunity "
        f"WHERE IsClosed = true AND CloseDate = THIS_QUARTER "
        f"AND {where_clause}"
    )
    try:
        wl_rows = _sf_query(wl_q)
    except Exception:
        wl_rows = []
    won_arr = round(
        sum(
            float(r.get("arr_fx") or 0)
            for r in wl_rows
            if r.get("IsWon") and r.get("Type") in ("Land", "Expand")
        ),
        2,
    )
    won_acv = round(
        sum(
            float(r.get("acv_fx") or 0)
            for r in wl_rows
            if r.get("IsWon") and r.get("Type") == "Renewal"
        ),
        2,
    )
    lost_arr = round(
        sum(
            float(r.get("arr_fx") or 0)
            for r in wl_rows
            if not r.get("IsWon") and r.get("Type") in ("Land", "Expand")
        ),
        2,
    )
    lost_acv = round(
        sum(
            float(r.get("acv_fx") or 0)
            for r in wl_rows
            if not r.get("IsWon") and r.get("Type") == "Renewal"
        ),
        2,
    )
    wins_losses_qtd = {
        "won_count": sum(1 for r in wl_rows if r.get("IsWon")),
        "lost_count": sum(1 for r in wl_rows if not r.get("IsWon")),
        "won_arr_eur": won_arr,
        "won_acv_eur": won_acv,
        "lost_arr_eur": lost_arr,
        "lost_acv_eur": lost_acv,
    }

    # Territory_Performance: open Land+Expand pipeline by sub-region
    # (Account.BillingCountry within director scope). The director's
    # `where_clause` already constrains to their territory; this slices
    # one level deeper.
    territory_acc: dict[str, dict[str, float]] = {}
    for r in rows:
        if r.get("Type") not in ("Land", "Expand"):
            continue
        country = (r.get("Account") or {}).get("BillingCountry") or "(unset)"
        bucket = territory_acc.setdefault(country, {"num_opps": 0, "arr_eur": 0.0})
        bucket["num_opps"] += 1
        bucket["arr_eur"] += float(r.get("arr_fx") or 0)
    territory_performance = sorted(
        [
            {"country": k, "num_opps": int(v["num_opps"]), "arr_eur": round(v["arr_eur"], 2)}
            for k, v in territory_acc.items()
        ],
        key=lambda x: x["arr_eur"],
        reverse=True,
    )

    # At_Risk_Renewals: open Renewal opps where the Account carries an
    # explicit termination-risk flag (High / Very High).
    at_risk_renewals: list[dict[str, Any]] = []
    for r in rows:
        if r.get("Type") != "Renewal":
            continue
        acct = r.get("Account") or {}
        risk = (acct.get("Risk_of_Potential_Termination__c") or "").lower()
        if "high" not in risk:  # catches "High" + "Very High"
            continue
        acv_eur_value = round(float(r.get("acv_fx") or 0), 2)
        # Risk scoring 0-4: combines termination-risk + close-date proximity + size.
        # 0 = safe, 4 = highest urgency. Used for Harvey balls on the deck slide.
        risk_text = (acct.get("Risk_of_Potential_Termination__c") or "").lower()
        risk_base = {"very high": 2, "high": 1, "medium": 0, "low": 0}.get(risk_text, 0)
        # Close-date proximity: this Q = +2, next 6mo = +1, beyond = 0
        close = (r.get("CloseDate") or "")[:10]
        try:
            close_d = dt.date.fromisoformat(close)
            days_out = (close_d - dt.date.today()).days
            proximity_bonus = 2 if days_out <= 90 else (1 if days_out <= 180 else 0)
        except Exception:
            proximity_bonus = 0
        # Size: ACV >= 500K adds +1
        size_bonus = 1 if acv_eur_value >= 500_000 else 0
        risk_score = min(4, risk_base + proximity_bonus + size_bonus)
        at_risk_renewals.append(
            {
                "stage": r.get("StageName") or "",
                "account": acct.get("Name") or "(unknown)",
                "owner": (r.get("Owner") or {}).get("Name") or "",
                "close_date": (r.get("CloseDate") or "")[:10],
                "acv_eur": acv_eur_value,
                "risk_level": acct.get("Risk_of_Potential_Termination__c") or "",
                "risk_score": risk_score,
            }
        )
    at_risk_renewals.sort(key=lambda x: x["acv_eur"], reverse=True)
    at_risk_renewals = at_risk_renewals[:15]

    # Competitive_Pressure: closed-lost Land+Expand opps in CFQ, by competitor
    comp_q = (
        "SELECT Id, Lost_to_Competitor__r.Name, "
        "convertCurrency(APTS_Opportunity_ARR__c) arr_fx, "
        "Reason_Won_Lost__c "
        "FROM Opportunity "
        "WHERE IsClosed = true AND IsWon = false "
        "AND CloseDate = THIS_QUARTER "
        "AND Type IN ('Land','Expand') "
        f"AND {where_clause}"
    )
    try:
        comp_rows = _sf_query(comp_q)
    except Exception:
        comp_rows = []
    comp_acc: dict[str, dict[str, float]] = {}
    for r in comp_rows:
        c = ((r.get("Lost_to_Competitor__r") or {}).get("Name")) or "(no competitor recorded)"
        bucket = comp_acc.setdefault(c, {"num_opps": 0, "arr_eur": 0.0})
        bucket["num_opps"] += 1
        bucket["arr_eur"] += float(r.get("arr_fx") or 0)
    competitive_pressure = sorted(
        [
            {"competitor": k, "num_opps": int(v["num_opps"]), "arr_eur": round(v["arr_eur"], 2)}
            for k, v in comp_acc.items()
        ],
        key=lambda x: x["arr_eur"],
        reverse=True,
    )

    # Retention (GRR proxy): closed-won Renewal ACV / closed-Renewal ACV last
    # 12 months. True NRR (with expansion uplift) needs cohort snapshots that
    # we don't have yet — deferred until Pipeline_Snapshot__c accumulates.
    ret_q = (
        "SELECT Id, Name, IsWon, CloseDate, "
        "Owner.Name, Account.Name, "
        "convertCurrency(APTS_Renewal_ACV__c) acv_fx "
        "FROM Opportunity "
        "WHERE IsClosed = true AND Type = 'Renewal' "
        "AND CloseDate >= LAST_N_DAYS:365 "
        f"AND {where_clause}"
    )
    try:
        ret_rows = _sf_query(ret_q)
    except Exception:
        ret_rows = []
    won_acv = round(sum(float(r.get("acv_fx") or 0) for r in ret_rows if r.get("IsWon")), 2)
    lost_acv = round(sum(float(r.get("acv_fx") or 0) for r in ret_rows if not r.get("IsWon")), 2)
    grr_proxy = round(100.0 * won_acv / (won_acv + lost_acv), 1) if (won_acv + lost_acv) else 0.0
    retention = {
        "won_renewal_acv_eur_l12m": won_acv,
        "lost_renewal_acv_eur_l12m": lost_acv,
        "grr_proxy_pct": grr_proxy,
        "won_count": sum(1 for r in ret_rows if r.get("IsWon")),
        "lost_count": sum(1 for r in ret_rows if not r.get("IsWon")),
    }

    # ARR_Roll: closed-won Land+Expand booked ARR by month, last 6 months.
    # Approximation of the booked-ARR roll-up that would otherwise come from
    # historical snapshots. FX-correct via per-record convertCurrency.
    roll_q = (
        "SELECT Id, Name, Type, StageName, CloseDate, "
        "Owner.Name, Account.Name, "
        "convertCurrency(APTS_Opportunity_ARR__c) arr_fx "
        "FROM Opportunity "
        "WHERE IsClosed = true AND IsWon = true "
        "AND CloseDate >= LAST_N_DAYS:180 "
        "AND Type IN ('Land','Expand') "
        f"AND {where_clause}"
    )
    try:
        roll_rows = _sf_query(roll_q)
    except Exception:
        roll_rows = []
    roll_acc: dict[str, dict[str, float]] = {}
    for r in roll_rows:
        cd = r.get("CloseDate") or ""
        ym = cd[:7] if len(cd) >= 7 else "(unknown)"
        bucket = roll_acc.setdefault(ym, {"num_opps": 0, "arr_eur": 0.0})
        bucket["num_opps"] += 1
        bucket["arr_eur"] += float(r.get("arr_fx") or 0)
    arr_roll = [
        {"month": k, "num_opps": int(v["num_opps"]), "arr_eur": round(v["arr_eur"], 2)}
        for k, v in sorted(roll_acc.items())
    ]

    # Top_Accounts: top 10 accounts by open Land+Expand ARR (account-level
    # aggregate, different from Top_Deals which is per-opp).
    acct_acc: dict[str, dict[str, float]] = {}
    for r in rows:
        if r.get("Type") not in ("Land", "Expand"):
            continue
        acct = (r.get("Account") or {}).get("Name") or "(unknown)"
        bucket = acct_acc.setdefault(acct, {"num_opps": 0, "arr_eur": 0.0})
        bucket["num_opps"] += 1
        bucket["arr_eur"] += float(r.get("arr_fx") or 0)
    top_accounts = sorted(
        [
            {"account": k, "num_opps": int(v["num_opps"]), "arr_eur": round(v["arr_eur"], 2)}
            for k, v in acct_acc.items()
        ],
        key=lambda x: x["arr_eur"],
        reverse=True,
    )[:10]

    # Pipeline_Aging: 5 age buckets via CreatedDate. ARR-weighted distribution.
    today_d = dt.date.today()
    aging_buckets: dict[str, dict[str, float]] = {
        "0-30 days": {"num_opps": 0, "arr_eur": 0.0},
        "31-90 days": {"num_opps": 0, "arr_eur": 0.0},
        "91-180 days": {"num_opps": 0, "arr_eur": 0.0},
        "181-365 days": {"num_opps": 0, "arr_eur": 0.0},
        "365+ days": {"num_opps": 0, "arr_eur": 0.0},
    }
    for r in rows:
        if r.get("Type") not in ("Land", "Expand"):
            continue
        cd = r.get("CreatedDate") or ""
        if len(cd) < 10:
            continue
        try:
            created = dt.date.fromisoformat(cd[:10])
            age = (today_d - created).days
        except Exception:
            continue
        if age <= 30:
            key = "0-30 days"
        elif age <= 90:
            key = "31-90 days"
        elif age <= 180:
            key = "91-180 days"
        elif age <= 365:
            key = "181-365 days"
        else:
            key = "365+ days"
        aging_buckets[key]["num_opps"] += 1
        aging_buckets[key]["arr_eur"] += float(r.get("arr_fx") or 0)
    pipeline_aging = [
        {"bucket": k, "num_opps": int(v["num_opps"]), "arr_eur": round(v["arr_eur"], 2)}
        for k, v in aging_buckets.items()
    ]

    # By_Owner: pipeline rollup by Owner.Name within director scope.
    owner_acc: dict[str, dict[str, float]] = {}
    for r in rows:
        if r.get("Type") not in ("Land", "Expand"):
            continue
        owner = (r.get("Owner") or {}).get("Name") or "(unknown)"
        bucket = owner_acc.setdefault(owner, {"num_opps": 0, "arr_eur": 0.0})
        bucket["num_opps"] += 1
        bucket["arr_eur"] += float(r.get("arr_fx") or 0)
    by_owner = sorted(
        [
            {"owner": k, "num_opps": int(v["num_opps"]), "arr_eur": round(v["arr_eur"], 2)}
            for k, v in owner_acc.items()
        ],
        key=lambda x: x["arr_eur"],
        reverse=True,
    )

    # Pending_Commercial_Approval — Stage 3+ Land/Expand opps without
    # Stage_20_Approval__c flag set. Per SimCorp Commercial Handbook:
    # Land deals require Commercial Approval at Stage 3+; Expand deals
    # at AER >= EUR 500k. We flag both for review.
    pending_approval = []
    for r in rows:
        if r.get("Type") not in ("Land", "Expand"):
            continue
        stage_str = r.get("StageName") or ""
        # Stage label format is "3 - Engagement", "4 - Shortlisted", ...
        try:
            stage_num = int(stage_str.split(" ")[0])
        except (ValueError, IndexError):
            continue
        if stage_num < 3 or stage_num > 6:
            continue
        approved = r.get("Stage_20_Approval__c")
        if approved:  # truthy means approved; None or False means pending
            continue
        arr_eur = float(r.get("arr_fx") or 0)
        # Skip Expand deals below the EUR 500k threshold (handbook gate)
        if r.get("Type") == "Expand" and arr_eur < 500_000:
            continue
        pending_approval.append(
            {
                "account": (r.get("Account") or {}).get("Name") or "(unknown)",
                "name": r.get("Name") or "",
                "owner": (r.get("Owner") or {}).get("Name") or "(unknown)",
                "stage": stage_str,
                "close_date": (r.get("CloseDate") or "")[:10],
                "type": r.get("Type") or "",
                "arr_eur": round(arr_eur, 2),
            }
        )
    pending_approval.sort(key=lambda x: x["arr_eur"], reverse=True)

    # Open Land+Expand ARR beyond CFQ — context for the headline number.
    # Also serves as the seed for the formula-driven model's Data sheet
    # (combined with `rows`, this gives us all open L+E in scope, regardless
    # of CloseDate). Same column shape as the main detail_q so the two can
    # be concatenated into raw_opps below.
    beyond_q = (
        "SELECT Id, Name, Type, StageName, CreatedDate, CloseDate, "
        "Stage_20_Approval__c, "
        "Owner.Name, ForecastCategoryName, "
        "Account.Name, Account.BillingCountry, Account.Industry, "
        "Account.Risk_of_Potential_Termination__c, "
        "convertCurrency(APTS_Opportunity_ARR__c) arr_fx, "
        "convertCurrency(APTS_Renewal_ACV__c) acv_fx "
        "FROM Opportunity "
        "WHERE IsClosed = false AND Type IN ('Land','Expand') "
        "AND CloseDate > THIS_QUARTER "
        f"AND {where_clause}"
    )
    try:
        beyond_rows = _sf_query(beyond_q)
    except Exception:
        beyond_rows = []
    beyond_cfq_arr = round(sum(float(r.get("arr_fx") or 0) for r in beyond_rows), 2)

    # raw_opps — flattened per-row dataset for the formula-driven model's
    # Data sheet. Combines CFQ rows (`rows`) and beyond-CFQ rows. Renewals
    # only show up in `rows` because `beyond_q` is L+E-only (matches what
    # the model needs since renewal pipeline is small and CFQ-bounded).
    def _flat(r: dict) -> dict:
        acct = r.get("Account") or {}
        owner = r.get("Owner") or {}
        return {
            "Id": r.get("Id") or "",
            "Type": r.get("Type") or "",
            "StageName": r.get("StageName") or "",
            "CreatedDate": (r.get("CreatedDate") or "")[:10],
            "CloseDate": (r.get("CloseDate") or "")[:10],
            "OwnerName": owner.get("Name") or "",
            "AccountName": acct.get("Name") or "",
            "BillingCountry": acct.get("BillingCountry") or "",
            "Industry": acct.get("Industry") or "",
            "RiskTermination": acct.get("Risk_of_Potential_Termination__c") or "",
            "ARR_EUR": round(float(r.get("arr_fx") or 0), 2),
            "ACV_EUR": round(float(r.get("acv_fx") or 0), 2),
        }

    raw_opps = [_flat(r) for r in rows] + [_flat(r) for r in beyond_rows]

    # Forecast category breakdown (Land+Expand, CFQ-closing) — matches
    # slide 18 of legacy 2026-04-10 deck format. Categories per SF:
    # Pipeline / Best Case / Commit / Closed / Omitted.
    forecast_acc: dict[str, dict[str, float]] = {}
    for r in rows:  # rows is CFQ-only L+E+R; we filter to L+E here
        if r.get("Type") not in ("Land", "Expand"):
            continue
        cat = r.get("ForecastCategoryName") or "(unset)"
        bucket = forecast_acc.setdefault(cat, {"num_opps": 0, "arr_eur": 0.0})
        bucket["num_opps"] += 1
        bucket["arr_eur"] += float(r.get("arr_fx") or 0)
    forecast_category = [
        {"category": cat, "num_opps": int(v["num_opps"]), "arr_eur": round(v["arr_eur"], 2)}
        for cat, v in sorted(forecast_acc.items())
    ]

    # Raw closed-history rows surfaced for the model's auditable Data
    # sheets. ARR_Roll / Trend_MoM / Trend_QoQ / Retention / Wins_Losses_QTD
    # / Competitive_Pressure all derive from one of these three lists, so
    # writing them as named Excel Tables (`tblClosedCFQ`, `tblClosedWon6mo`,
    # `tblRenewals12mo`) lets every analytical sheet trace SUMIFS back to
    # raw FX-converted opportunity rows. Per AI Code of Conduct §8: per-
    # deal data stays in the director's own xlsx — same scope rule as
    # Top_Deals.
    def _flat_closed(r: dict) -> dict:
        acct = r.get("Account") or {}
        owner = r.get("Owner") or {}
        return {
            "Id": r.get("Id") or "",
            "Name": r.get("Name") or "",
            "Type": r.get("Type") or "",
            "StageName": r.get("StageName") or "",
            "IsWon": bool(r.get("IsWon")),
            "CloseDate": (r.get("CloseDate") or "")[:10],
            "OwnerName": owner.get("Name") or "",
            "AccountName": acct.get("Name") or "",
            "ARR_EUR": round(float(r.get("arr_fx") or 0), 2),
            "ACV_EUR": round(float(r.get("acv_fx") or 0), 2),
        }

    closed_cfq_rows = [_flat_closed(r) for r in wl_rows]
    closed_won_6mo_rows = [_flat_closed(r) for r in roll_rows]
    closed_renewals_12mo_rows = [_flat_closed(r) for r in ret_rows]

    # Pipe movement opening — read prior monthly snapshot if available.
    # Mirrors the per-director out_dir slug used by main(): name with
    # spaces collapsed to hyphens. This unblocks the Pipe_Movement sheet
    # without requiring any new SOQL — when no prior snapshot exists the
    # opening defaults to 0 and the residual bucket carries the closing.
    director_slug = director.get("name", "").replace(" ", "-")
    prev_snapshot_path = STATE_DIR / period / director_slug / "snapshot_prev.json"
    opening_arr = 0.0
    if prev_snapshot_path.exists():
        try:
            with prev_snapshot_path.open() as fh:
                prev = json.load(fh)
            opening_arr = float(
                ((prev.get("totals") or {}).get("new_business_arr_open_this_quarter") or 0)
            )
        except Exception:
            pass

    return {
        "by_type": by_type,
        "new_business_by_stage": new_business_by_stage,
        "renewals_by_stage": renewals_by_stage,
        "top_deals_land": top_deals_land,
        "top_deals_expand": top_deals_expand,
        "wins_losses_qtd": wins_losses_qtd,
        "territory_performance": territory_performance,
        "at_risk_renewals": at_risk_renewals,
        "competitive_pressure": competitive_pressure,
        "arr_roll": arr_roll,
        "retention": retention,
        "top_accounts": top_accounts,
        "pipeline_aging": pipeline_aging,
        "by_owner": by_owner,
        "pending_commercial_approval": pending_approval,
        "forecast_category": forecast_category,
        "totals": {
            "new_business_arr_open_this_quarter": round(
                sum(t["arr"] for t in by_type if t["type"] in ("Land", "Expand")), 2
            ),
            "renewal_acv_open_this_quarter": round(
                sum(t["renewal_acv"] for t in by_type if t["type"] == "Renewal"), 2
            ),
            "new_business_arr_open_beyond_cfq": beyond_cfq_arr,
        },
        "raw_opps": raw_opps,
        "closed_cfq_rows": closed_cfq_rows,
        "closed_won_6mo_rows": closed_won_6mo_rows,
        "closed_renewals_12mo_rows": closed_renewals_12mo_rows,
        "pipe_movement_opening_arr": opening_arr,
        "_fx_converted": True,
        "_fx_target_currency": "EUR (apro display currency)",
    }


def build_trends_envelope(
    sf_snapshot: dict, director: dict, period: str, *, backtest_path: Optional[Path] = None
) -> dict:
    """Produce the trends.json envelope. Aggregate-only — no client-level data."""
    totals = sf_snapshot.get("totals", {})
    new_arr = totals.get("new_business_arr_open_this_quarter", 0) or 0
    renewal_acv = totals.get("renewal_acv_open_this_quarter", 0) or 0
    beyond_cfq_arr = totals.get("new_business_arr_open_beyond_cfq", 0) or 0

    kpis = [
        {
            "name": "total_pipeline_arr",
            "display_label": f"{period} closeable Land+Expand ARR",
            "value": new_arr,
            "unit": "EUR",
            "narrative_priority": "high",
        },
        {
            "name": "total_renewal_acv",
            "display_label": f"{period} renewal ACV",
            "value": renewal_acv,
            "unit": "EUR",
            "narrative_priority": "high",
        },
        {
            # Context for the headline. Director's open Land+Expand pipeline
            # outside the current quarter — so a small CFQ figure is read
            # against the rest of their book, not in isolation.
            "name": "pipeline_arr_beyond_cfq",
            "display_label": f"Open Land+Expand beyond {period}",
            "value": beyond_cfq_arr,
            "unit": "EUR",
            "narrative_priority": "medium",
        },
    ]
    for row in sf_snapshot.get("new_business_by_stage", []):
        kpis.append(
            {
                "name": f"pipeline_arr_stage_{row['stage'].split(' ')[0]}",
                "value": row["arr"],
                "unit": "EUR",
                "stage_label": row["stage"],
                "num_opps": row["num_opps"],
                "narrative_priority": "medium",
            }
        )
    for row in sf_snapshot.get("renewals_by_stage", []):
        kpis.append(
            {
                "name": f"renewal_acv_stage_{row['stage'].split(' ')[0]}",
                "value": row["acv"],
                "unit": "EUR",
                "stage_label": row["stage"],
                "num_opps": row["num_opps"],
                "narrative_priority": "medium",
            }
        )

    if backtest_path and backtest_path.exists():
        backtest = json.loads(backtest_path.read_text())
        for stage, rate in backtest.get("forward_rates", {}).items():
            kpis.append(
                {
                    "name": f"backtest_{stage}",
                    "value": rate * 100,
                    "unit": "pct",
                    "narrative_priority": "low",
                }
            )

    return {
        "schema_version": "1.0",
        "director": {
            "name": director["name"],
            "book_codes": director.get("book_codes", []),
            "scope": director.get("scope"),
            "scope_label": director.get("scope_label", ""),
        },
        "period": period,
        "period_end": dt.date.today().isoformat(),
        "currency": "EUR",
        "currency_format": "mEUR",
        "kpis": kpis,
        "highlights": [],
        "risks": [],
        "context_quotes": [],
        "edge_case_flags": {
            "insufficient_history": False,
            "fy_boundary_span": False,
            "director_inactive": len(kpis) == 2,
            "extraction_partial": False,
        },
    }


def derive_highlights_risks(envelope: dict) -> dict:
    """Rule-based highlights + risks. No LLM judgement."""
    kpis = envelope["kpis"]
    total = next((k for k in kpis if k["name"] == "total_pipeline_arr"), None)
    stages = [k for k in kpis if k["name"].startswith("pipeline_arr_stage_")]

    highlights = []
    risks = []

    late_stage = sum(
        k["value"] for k in stages if k.get("stage_label", "").split(" ")[0] in ("5", "6")
    )
    if total and total["value"] > 0:
        late_pct = 100.0 * late_stage / total["value"]
        if late_pct > 70:
            highlights.append(
                {
                    "kpi_name": "late_stage_concentration_pct",
                    "claim": f"{late_pct:.0f}% of new-business ARR is in Stage 5+ — strong near-term close potential",
                    "rule": "late-stage concentration > 70%",
                    "evidence": [f"late_stage_arr={late_stage}", f"total_arr={total['value']}"],
                }
            )
        elif late_pct < 30:
            risks.append(
                {
                    "kpi_name": "late_stage_concentration_pct",
                    "claim": f"only {late_pct:.0f}% of pipeline in Stage 5+ — quarter coverage at risk",
                    "rule": "late-stage concentration < 30%",
                    "evidence": [f"late_stage_arr={late_stage}", f"total_arr={total['value']}"],
                }
            )

    renewal = next((k for k in kpis if k["name"] == "total_renewal_acv"), None)
    if renewal and renewal["value"] < 100_000:
        risks.append(
            {
                "kpi_name": "total_renewal_acv",
                "claim": "renewal ACV in this quarter is below 100K — verify renewal-eligible accounts",
                "rule": "renewal_acv < 100K",
                "evidence": [f"renewal_acv={renewal['value']}"],
            }
        )

    envelope["highlights"] = highlights[:5]
    envelope["risks"] = risks[:5]
    return envelope


# ──────────────────────────────────────────────────────────────────────────────
# Action-item rule set (schema_version=2)
#
# Six rules, each scoped to one director's territory via their where_clause.
# Each rule emits 0..1 action_items per director when the threshold trips. The
# action_items list is what the deck's "Action Items" slide consumes, and what
# the regional memo aggregates for region-level rollup.
# ──────────────────────────────────────────────────────────────────────────────


def _pull_zombie_for_director(where_clause: str) -> dict[str, Any]:
    """Open Land+Expand opps >730d old with no Task/Event activity in 60d.

    SOQL `Id NOT IN (subquery)` pattern; FX-correct via per-record
    convertCurrency.
    """
    q = (
        "SELECT Id, Owner.Name, "
        "convertCurrency(APTS_Opportunity_ARR__c) arr_fx "
        "FROM Opportunity "
        f"WHERE IsClosed = false AND {where_clause} "
        "AND Type IN ('Land','Expand') "
        "AND CreatedDate <= LAST_N_DAYS:730 "
        "AND Id NOT IN (SELECT WhatId FROM Task WHERE ActivityDate >= LAST_N_DAYS:60) "
        "AND Id NOT IN (SELECT WhatId FROM Event WHERE ActivityDate >= LAST_N_DAYS:60)"
    )
    rows = _sf_query(q)
    return {
        "count": len(rows),
        "total_arr_eur": round(sum(float(r.get("arr_fx") or 0) for r in rows), 2),
        "top_owner": max(rows, key=lambda r: (r.get("arr_fx") or 0))["Owner"]["Name"]
        if rows
        else None,
    }


def _pull_coverage_gap_for_director(where_clause: str) -> dict[str, Any]:
    """Tier-1 accounts in director scope with no open Land+Expand opp in 90d.

    The intent of "coverage gap" is "no new-business pipeline" — a Renewal
    in flight does NOT count as coverage. So the subquery is scoped to
    Type IN ('Land','Expand'). Per the SimCorp ARR/ACV split rule.

    Translates the Opportunity-side where_clause to an Account-side scope
    via the same Region__c / BillingCountry / Industry filters.
    """
    acct_where = where_clause.replace("Account.", "")
    q = (
        "SELECT Id, Name FROM Account "
        f"WHERE Tier_Calculation__c = 'Tier 1' AND ({acct_where}) "
        "AND Id NOT IN ("
        "SELECT AccountId FROM Opportunity "
        "WHERE IsClosed = false "
        "AND Type IN ('Land','Expand') "
        "AND CreatedDate >= LAST_N_DAYS:90"
        ")"
    )
    try:
        rows = _sf_query(q)
        return {"count": len(rows), "sample_accounts": [r.get("Name") for r in rows[:3]]}
    except Exception:
        return {"count": 0, "sample_accounts": [], "_skipped": True}


def _pull_approval_gap_for_director(where_clause: str) -> dict[str, Any]:
    """Stage 3+ Land+Expand opps >= EUR 500k without Commercial Approval
    (Stage_20_Approval__c = false).
    """
    q = (
        "SELECT Id, Name, Owner.Name, "
        "convertCurrency(APTS_Opportunity_ARR__c) arr_fx "
        "FROM Opportunity "
        f"WHERE IsClosed = false AND {where_clause} "
        "AND Type IN ('Land','Expand') "
        "AND APTS_Opportunity_ARR__c >= 500000 "
        "AND StageName IN ('3 - Engagement','4 - Shortlisted','5 - Preferred','6 - Contracting') "
        "AND (Stage_20_Approval__c = false OR Stage_20_Approval__c = null)"
    )
    rows = _sf_query(q)
    return {
        "count": len(rows),
        "total_arr_eur": round(sum(float(r.get("arr_fx") or 0) for r in rows), 2),
        "sample": [r.get("Name") for r in rows[:3]],
    }


def _pull_simcorp_one_share_for_director(where_clause: str) -> dict[str, Any]:
    """SimCorp One (Standard Platform) attach rate within director's open
    Land+Expand pipeline.

    Defines "SimCorp One opp" as any open Land/Expand opp that has a
    `Standard Platform` line item attached (via OpportunityLineItem +
    Product2.Name). Returns total open Land+Expand count + SP-attached
    count + ratio. Use the ratio to drive the action: < 30% triggers a
    platform-selling motion review.
    """
    # Total open L+E opps in director scope
    total_q = (
        "SELECT COUNT(Id) n FROM Opportunity "
        f"WHERE IsClosed = false AND {where_clause} "
        "AND Type IN ('Land','Expand')"
    )
    total = _sf_query(total_q)
    total_count = int((total[0].get("n") if total else 0) or 0)

    # Subset that has a 'Standard Platform' line item — uses IN-subquery
    # against OpportunityLineItem.
    sp_q = (
        "SELECT Id FROM Opportunity "
        f"WHERE IsClosed = false AND {where_clause} "
        "AND Type IN ('Land','Expand') "
        "AND Id IN ("
        "SELECT OpportunityId FROM OpportunityLineItem "
        "WHERE Product2.Name = 'Standard Platform'"
        ")"
    )
    sp_rows = _sf_query(sp_q)
    sp_count = len(sp_rows)

    pct = round(100.0 * sp_count / total_count, 1) if total_count else 0.0
    return {
        "total_count": total_count,
        "sp_count": sp_count,
        "share_pct": pct,
    }


def _pull_activity_drought_for_director(where_clause: str) -> dict[str, Any]:
    """This-Q open Land+Expand opps with no Task/Event activity in last 30d.

    Type-scoped to Land+Expand so the count and the ARR claim line up — a
    Renewal opp in this list would inflate the count while contributing
    EUR 0 to the ARR sum (per the APTS_Opportunity_ARR__c formula that
    zeros it out for Renewal sub-types). For Renewal activity drought,
    add a separate rule that uses ACV.
    """
    q = (
        "SELECT Id, "
        "convertCurrency(APTS_Opportunity_ARR__c) arr_fx "
        "FROM Opportunity "
        f"WHERE IsClosed = false AND {where_clause} "
        "AND Type IN ('Land','Expand') "
        "AND CloseDate = THIS_QUARTER "
        "AND Id NOT IN (SELECT WhatId FROM Task WHERE ActivityDate >= LAST_N_DAYS:30) "
        "AND Id NOT IN (SELECT WhatId FROM Event WHERE ActivityDate >= LAST_N_DAYS:30)"
    )
    rows = _sf_query(q)
    return {
        "count": len(rows),
        "total_arr_eur": round(sum(float(r.get("arr_fx") or 0) for r in rows), 2),
    }


def pull_director_action_data(director: dict) -> dict[str, Any]:
    """Runs the four director-scoped action queries. Each rule wrapped so a
    single failure doesn't break the rest."""
    where = director.get("where_clause")
    if not where:
        book_codes = "(" + ",".join(f"'{b}'" for b in director["book_codes"]) + ")"
        where = f"Account.Sales_Director_Book__c IN {book_codes}"

    out: dict[str, Any] = {}
    for key, fn in [
        ("zombie", _pull_zombie_for_director),
        ("coverage_gap", _pull_coverage_gap_for_director),
        ("approval_gap", _pull_approval_gap_for_director),
        ("simcorp_one_share", _pull_simcorp_one_share_for_director),
        ("activity_drought", _pull_activity_drought_for_director),
    ]:
        try:
            out[key] = fn(where)
        except Exception as e:
            print(f"  [WARN] action-data {key} failed: {e}", file=sys.stderr)
            out[key] = {"_error": str(e)}
    return out


def _next_month_end_iso() -> str:
    """Default action-item due date — last day of next month."""
    today = dt.date.today()
    if today.month == 12:
        nxt = dt.date(today.year + 1, 1, 1)
    else:
        nxt = dt.date(today.year, today.month + 1, 1)
    if nxt.month == 12:
        eom = dt.date(nxt.year + 1, 1, 1) - dt.timedelta(days=1)
    else:
        eom = dt.date(nxt.year, nxt.month + 1, 1) - dt.timedelta(days=1)
    return eom.isoformat()


def derive_action_items(envelope: dict, action_data: dict) -> dict:
    """Generate prioritized action items from rule evaluations + envelope.

    Each action_item has:
      - rule_id           stable key for de-dup / tracking
      - priority          high / medium / low
      - claim             one-line numeric statement
      - suggested_action  what to do next
      - evidence          list of supporting datapoints
      - owner             defaults to the director's name
      - due_date          last day of next month
    """
    director = envelope["director"]
    owner = director["name"]
    due = _next_month_end_iso()
    items: list[dict[str, Any]] = []

    # Rule 1: Zombie ARR exposure
    z = action_data.get("zombie") or {}
    if z.get("count", 0) > 0 and (z.get("total_arr_eur") or 0) >= 1_000_000:
        items.append(
            {
                "rule_id": "zombie_arr",
                "priority": "high" if (z.get("total_arr_eur") or 0) >= 5_000_000 else "medium",
                "claim": f"{z['count']} open Land+Expand opps >730 days old with no activity in 60d "
                f"— EUR {z.get('total_arr_eur', 0):,.0f} stale ARR",
                "suggested_action": "Review zombie deals 1:1 with each rep; decide close/disqualify "
                "by EOM. Top owner: " + (z.get("top_owner") or "n/a"),
                "evidence": [f"count={z['count']}", f"arr_eur={z.get('total_arr_eur', 0)}"],
                "owner": owner,
                "due_date": due,
            }
        )

    # Rule 2: Coverage Gap on Tier-1 accounts
    cg = action_data.get("coverage_gap") or {}
    if cg.get("count", 0) >= 5:
        items.append(
            {
                "rule_id": "coverage_gap",
                "priority": "medium",
                "claim": f"{cg['count']} Tier-1 accounts in your territory with no open Land/Expand opp in 90d",
                "suggested_action": "Run an account-coverage review with reps; assign opener "
                "responsibility for each starved Tier-1.",
                "evidence": [
                    f"count={cg['count']}",
                    "sample=" + ",".join(cg.get("sample_accounts") or []),
                ],
                "owner": owner,
                "due_date": due,
            }
        )

    # Rule 3: Approval Gap (Commercial Approval missing)
    ag = action_data.get("approval_gap") or {}
    if ag.get("count", 0) > 0:
        items.append(
            {
                "rule_id": "approval_gap",
                "priority": "high",
                "claim": f"{ag['count']} Stage 3+ Land/Expand opps ≥ EUR 500k missing Commercial "
                f"Approval — EUR {ag.get('total_arr_eur', 0):,.0f} ARR exposure",
                "suggested_action": "Submit each opp for Commercial Approval before EOM. "
                "Commercial Approval is mandatory for ALL Land deals per the 8-stage process.",
                "evidence": [f"count={ag['count']}", f"arr_eur={ag.get('total_arr_eur', 0)}"],
                "owner": owner,
                "due_date": due,
            }
        )

    # Rule 4: SimCorp One attach rate < 30% in open Land+Expand pipeline.
    # SimCorp One = the Standard Platform core product. Sub-30% attach means
    # the territory is selling adjuncts/modules without the platform anchor.
    sp = action_data.get("simcorp_one_share") or {}
    if (sp.get("total_count") or 0) >= 5 and sp.get("share_pct", 100) < 30:
        items.append(
            {
                "rule_id": "simcorp_one_attach_low",
                "priority": "medium",
                "claim": f"only {sp.get('share_pct', 0):.0f}% of open Land/Expand opps "
                f"({sp.get('sp_count', 0)} of {sp.get('total_count', 0)}) attach Standard "
                "Platform — SimCorp One penetration is thin",
                "suggested_action": "Review platform-led selling motion with reps; identify "
                "5-10 module-only opps where Standard Platform should be added before next "
                "stage gate. Pair with the SimCorp One product team if needed.",
                "evidence": [
                    f"sp_count={sp.get('sp_count', 0)}",
                    f"total_count={sp.get('total_count', 0)}",
                    f"share_pct={sp.get('share_pct', 0)}",
                ],
                "owner": owner,
                "due_date": due,
            }
        )

    # Rule 5: Late-stage concentration < 30% — already computed in highlights_risks
    kpis = envelope["kpis"]
    total = next((k for k in kpis if k["name"] == "total_pipeline_arr"), None)
    stages = [k for k in kpis if k["name"].startswith("pipeline_arr_stage_")]
    late_stage = sum(
        k["value"] for k in stages if k.get("stage_label", "").split(" ")[0] in ("5", "6")
    )
    if total and (total["value"] or 0) > 0:
        late_pct = 100.0 * late_stage / total["value"]
        if late_pct < 30:
            items.append(
                {
                    "rule_id": "late_stage_concentration",
                    "priority": "medium",
                    "claim": f"only {late_pct:.0f}% of pipeline ARR in Stage 5+ — quarter "
                    "coverage at risk",
                    "suggested_action": "Schedule Stage 3 → 4 progression workshops with each rep; "
                    "identify the 3-5 deals most likely to advance.",
                    "evidence": [f"late_pct={late_pct:.1f}", f"late_arr={late_stage}"],
                    "owner": owner,
                    "due_date": due,
                }
            )

    # Rule 5: Activity drought
    ad = action_data.get("activity_drought") or {}
    if ad.get("count", 0) >= 5:
        items.append(
            {
                "rule_id": "activity_drought",
                "priority": "medium",
                "claim": f"{ad['count']} this-quarter open Land/Expand opps with no activity in 30d "
                f"(EUR {ad.get('total_arr_eur', 0):,.0f} ARR)",
                "suggested_action": "Reset 14-day activity SLA with reps; require one logged "
                "Task/Event per opp every 14 days to maintain forecast credibility.",
                "evidence": [f"count={ad['count']}", f"arr_eur={ad.get('total_arr_eur', 0)}"],
                "owner": owner,
                "due_date": due,
            }
        )

    # Rule 6: Renewal pipeline thin — already in risks; reframe as action
    renewal = next((k for k in kpis if k["name"] == "total_renewal_acv"), None)
    if renewal and (renewal["value"] or 0) < 100_000:
        items.append(
            {
                "rule_id": "renewal_thin",
                "priority": "low",
                "claim": f"renewal ACV in pipeline is EUR {renewal['value']:,.0f} — below the "
                "EUR 100k threshold for healthy retention coverage",
                "suggested_action": "Verify renewal-eligible accounts are surfaced. CSM team "
                "to validate cohort coverage with the data team.",
                "evidence": [f"renewal_acv_eur={renewal['value']}"],
                "owner": owner,
                "due_date": due,
            }
        )

    # Sort high → medium → low; cap at 8 (avoid memo bloat)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda x: priority_order.get(x["priority"], 9))
    envelope["action_items"] = items[:8]
    envelope["schema_version"] = 2  # introduces action_items field
    return envelope


def render_director_brief(envelope: dict) -> str:
    d = envelope["director"]
    period = envelope["period"]
    lines = [
        f"# {d['name']} — {period} LAND review",
        "",
        "*Generated by sales-ops-copilot. Aggregate-only per AI Code of Conduct.*",
        "",
    ]

    # Headline summary — CFQ closeable + beyond-CFQ context. Prevents a
    # director seeing a small CFQ number from concluding the deck is broken.
    cfq_kpi = next((k for k in envelope["kpis"] if k["name"] == "total_pipeline_arr"), None)
    beyond_kpi = next((k for k in envelope["kpis"] if k["name"] == "pipeline_arr_beyond_cfq"), None)
    renewal_kpi = next((k for k in envelope["kpis"] if k["name"] == "total_renewal_acv"), None)
    if cfq_kpi:
        cfq_meur = (cfq_kpi.get("value") or 0) / 1_000_000
        beyond_meur = (beyond_kpi.get("value") or 0) / 1_000_000 if beyond_kpi else 0.0
        renewal_meur = (renewal_kpi.get("value") or 0) / 1_000_000 if renewal_kpi else 0.0
        lines += [
            "## Headline",
            "",
            f"- **{period} closeable Land+Expand ARR:** EUR {cfq_meur:.1f}M",
            f"- Open Land+Expand beyond {period}: EUR {beyond_meur:.1f}M "
            f"_(out-of-quarter pipe — context, not currently in forecast)_",
            f"- {period} renewal ACV: EUR {renewal_meur:.1f}M",
            "",
        ]

    if envelope["highlights"]:
        lines += ["## Highlights", ""]
        for h in envelope["highlights"]:
            lines += [f"- **{h['claim']}** _(rule: {h['rule']})_"]
        lines.append("")

    if envelope.get("action_items"):
        lines += [
            "## Action items",
            "",
            f"*{len(envelope['action_items'])} ranked actions for {envelope['director']['name']} this month. "
            f"Due: {envelope['action_items'][0]['due_date']}.*",
            "",
            "| # | Priority | Claim | Suggested action |",
            "|---|---|---|---|",
        ]
        for i, a in enumerate(envelope["action_items"], 1):
            lines.append(
                f"| {i} | {a['priority'].upper()} | {a['claim']} | {a['suggested_action']} |"
            )
        lines.append("")

    if envelope["risks"]:
        lines += ["## Risks", ""]
        for r in envelope["risks"]:
            lines += [f"- **{r['claim']}** _(rule: {r['rule']})_"]
        lines.append("")

    backtest_kpis = [k for k in envelope["kpis"] if k["name"].startswith("backtest_")]
    if backtest_kpis:
        lines += [
            "## Forecast backtest (last 4 quarters)",
            "",
            "| Stage transition | Forward rate |",
            "|---|---:|",
        ]
        for k in backtest_kpis:
            stage_num = k["name"].replace("backtest_stage_", "").replace("_forward_rate", "")
            lines.append(f"| Stage {stage_num} → next | {k['value']:.1f}% |")
        lines.append("")

    lines += ["## KPIs", "", "| KPI | Value | Unit | Priority |", "|---|---:|---|---|"]
    for k in envelope["kpis"]:
        # Prefer display_label (stakeholder-facing) over the internal name key
        # when present; older envelopes without display_label still render fine.
        label = k.get("display_label") or k["name"]
        lines.append(f"| {label} | {k['value']:,.0f} | {k['unit']} | {k['narrative_priority']} |")
    lines.append("")

    if any(envelope["edge_case_flags"].values()):
        lines += ["## Edge cases flagged", ""]
        for k, v in envelope["edge_case_flags"].items():
            if v:
                lines.append(f"- {k}")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--director", help="Single director name (e.g., 'Adam Steinhouse')")
    ap.add_argument("--all-directors", action="store_true", help="Run for all 9 MD-1 directors")
    ap.add_argument("--period", required=True, help="e.g., 2026-Q2")
    args = ap.parse_args()

    if not args.director and not args.all_directors:
        print("ERROR: pass either --director or --all-directors", file=sys.stderr)
        return 1

    directors = (
        canonical_directors()
        if args.all_directors
        else [d for d in canonical_directors() if d["name"] == args.director]
    )
    if not directors:
        print(f"ERROR: no director matching {args.director!r}", file=sys.stderr)
        return 1

    STATE_DIR.mkdir(exist_ok=True)
    period_dir = STATE_DIR / args.period
    period_dir.mkdir(exist_ok=True)

    backtest_path = STATE_DIR / "forecast_backtest_q4.json"

    # Pull org-wide benchmarks once (shared across all 9 directors so they
    # can compare their scope vs the org).
    print("→ Pulling org-wide benchmarks (shared across directors)...")
    try:
        benchmarks = pull_org_benchmarks()
    except Exception as e:
        print(f"  [WARN] benchmark pull failed: {e}", file=sys.stderr)
        benchmarks = {}

    failures = []
    for d in directors:
        dn = d["name"].replace(" ", "-")
        out_dir = period_dir / dn
        out_dir.mkdir(exist_ok=True)
        try:
            print(f"→ {d['name']}: pulling SF snapshot...")
            sf = pull_director_snapshot(d, args.period)
            envelope = build_trends_envelope(sf, d, args.period, backtest_path=backtest_path)
            envelope = derive_highlights_risks(envelope)
            action_data = pull_director_action_data(d)
            envelope = derive_action_items(envelope, action_data)
            (out_dir / "trends.json").write_text(json.dumps(envelope, indent=2))
            (out_dir / "brief.md").write_text(render_director_brief(envelope))
            backtest_data = (
                json.loads(backtest_path.read_text()) if backtest_path.exists() else None
            )
            # Merge action_data (which has simcorp_one_share + others) into the
            # snapshot dict so excel_companion can populate the SimCorp_One sheet.
            sf_with_actions = {
                **sf,
                "simcorp_one": action_data.get("simcorp_one_share") or {},
                "benchmarks": benchmarks,
            }
            build_director_excel(
                envelope,
                out_dir / "land.xlsx",
                snapshot=sf_with_actions,
                backtest=backtest_data,
            )
            # Formula-driven sibling — same envelope + snapshot, but with a
            # canonical Data sheet and SUMIFS-based analytical sheets so a
            # director / analyst can trace any KPI to its inputs.
            build_director_model(
                envelope,
                out_dir / "land.model.xlsx",
                snapshot=sf_with_actions,
                backtest=backtest_data,
            )
            print(
                f"  Wrote {out_dir / 'trends.json'} + brief.md + land.xlsx + land.model.xlsx "
                f"({len(envelope.get('action_items') or [])} action items)"
            )
        except Exception as e:
            failures.append({"director": d["name"], "error": str(e)})
            print(f"  ✗ {d['name']}: {e}", file=sys.stderr)

    if failures:
        print(f"\n{len(failures)} director(s) failed", file=sys.stderr)
        return 2
    print(f"\n✓ {len(directors)} director(s) processed; output at {period_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
