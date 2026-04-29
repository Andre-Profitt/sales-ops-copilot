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
            (out_dir / "trends.json").write_text(json.dumps(envelope, indent=2))
            (out_dir / "brief.md").write_text(render_director_brief(envelope))
            build_director_excel(envelope, out_dir / "land.xlsx")
            print(f"  Wrote {out_dir / 'trends.json'} + brief.md + land.xlsx")
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
