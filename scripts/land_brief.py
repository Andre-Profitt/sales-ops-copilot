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

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"


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
    detail_q = (
        "SELECT Id, Type, StageName, "
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

    return {
        "by_type": by_type,
        "new_business_by_stage": new_business_by_stage,
        "renewals_by_stage": renewals_by_stage,
        "totals": {
            "new_business_arr_open_this_quarter": round(
                sum(t["arr"] for t in by_type if t["type"] in ("Land", "Expand")), 2
            ),
            "renewal_acv_open_this_quarter": round(
                sum(t["renewal_acv"] for t in by_type if t["type"] == "Renewal"), 2
            ),
        },
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

    kpis = [
        {
            "name": "total_pipeline_arr",
            "value": new_arr,
            "unit": "EUR",
            "narrative_priority": "high",
        },
        {
            "name": "total_renewal_acv",
            "value": renewal_acv,
            "unit": "EUR",
            "narrative_priority": "high",
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
    """Tier-1 accounts in director scope with no open opp in 90d.

    Translates the Opportunity-side where_clause to an Account-side scope
    via the same Region__c / BillingCountry / Industry filters.
    """
    # Strip the "Account." prefix so we can use the same conditions on Account
    # directly.
    acct_where = where_clause.replace("Account.", "")
    q = (
        "SELECT Id, Name FROM Account "
        f"WHERE Tier_Calculation__c = 'Tier 1' AND ({acct_where}) "
        "AND Id NOT IN ("
        "SELECT AccountId FROM Opportunity "
        "WHERE IsClosed = false AND CreatedDate >= LAST_N_DAYS:90"
        ")"
    )
    try:
        rows = _sf_query(q)
        return {"count": len(rows), "sample_accounts": [r.get("Name") for r in rows[:3]]}
    except Exception:
        # Some director scope clauses may not translate cleanly to Account.* fields
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


def _pull_activity_drought_for_director(where_clause: str) -> dict[str, Any]:
    """This-Q open opps with no Task/Event activity in last 30d."""
    q = (
        "SELECT Id, "
        "convertCurrency(APTS_Opportunity_ARR__c) arr_fx "
        "FROM Opportunity "
        f"WHERE IsClosed = false AND {where_clause} "
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
                "claim": f"{cg['count']} Tier-1 accounts in your territory with no open opp in 90d",
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

    # Rule 4: Late-stage concentration < 30% — already computed in highlights_risks
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
                "claim": f"{ad['count']} this-quarter open opps with no activity in 30d "
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
    lines = [
        f"# {d['name']} — {envelope['period']} LAND review",
        "",
        "*Generated by sales-ops-copilot. Aggregate-only per AI Code of Conduct.*",
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
        lines.append(
            f"| {k['name']} | {k['value']:,.0f} | {k['unit']} | {k['narrative_priority']} |"
        )
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
            build_director_excel(envelope, out_dir / "land.xlsx")
            print(
                f"  Wrote {out_dir / 'trends.json'} + brief.md + land.xlsx "
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
