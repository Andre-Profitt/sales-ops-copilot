#!/usr/bin/env python3
"""Evaluate think-cell visual fit for current-quarter decks using live Salesforce.

The gate answers a narrow question: which think-cell families are actually
eligible for the May 2026 / 2026-Q2 Sales Director decks when the data source is
the live Salesforce org, not just the existing workbook artifacts.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from _directors import canonical_directors
from sales_director_row_filters import is_internal_sales_record


ROOT = Path(__file__).resolve().parent.parent
Q2_START = date(2026, 4, 1)
Q2_END = date(2026, 6, 30)
FY26_END = date(2026, 12, 31)
STAGE_3PLUS = {
    "3 - Engagement",
    "4 - Shortlisted",
    "5 - Preferred",
    "6 - Contracting",
}


@dataclass
class DirectorVisualFit:
    director: str
    territory: str
    q2_open_arr_count: int
    q2_open_arr_eur: float
    q2_open_renewal_count: int
    q2_open_renewal_acv_eur: float
    fy26_open_renewal_count: int
    fy26_open_renewal_acv_eur: float
    internal_rows_removed: int
    visual_fit: dict[str, Any]
    recommended_this_quarter: list[str]
    avoid_this_quarter: list[str]
    top_deal_rows: list[dict[str, Any]]


def _run_sf_query(query: str, target_org: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["sf", "data", "query", "--target-org", target_org, "--json", "--query", query],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    payload = json.loads(result.stdout)
    if payload.get("status") != 0:
        raise RuntimeError(json.dumps(payload, indent=2))
    return list(payload.get("result", {}).get("records", []))


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _account(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("Account")
    return value if isinstance(value, dict) else {}


def _owner(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("Owner")
    return value if isinstance(value, dict) else {}


def _director_match(record: dict[str, Any], director: dict[str, Any]) -> bool:
    account = _account(record)
    country = _text(account.get("BillingCountry"))
    region = _text(account.get("Region__c"))
    industry = _text(account.get("Industry"))
    label = str(director["scope_label"])
    if label == "Canada":
        return country == "Canada"
    if label == "NA Asset Management":
        return region == "North America" and country != "Canada" and industry == "Asset Management"
    if label == "APAC":
        return region == "APAC"
    if label == "Central Europe":
        return region == "Central Europe"
    if label == "Southern Europe":
        return region == "Southwestern Europe"
    if label == "UK & Ireland":
        return region == "United Kingdom & Ireland"
    if label == "NL & Nordics":
        return region == "Northern Europe"
    if label == "Middle East & Africa":
        return region == "Middle East & Africa"
    if label == "US Pension & Insurance":
        return region == "North America" and country != "Canada" and industry in {"Pension", "Insurance"}
    return False


def _is_internal(record: dict[str, Any]) -> bool:
    account = _account(record)
    normalized = {
        "Account": account,
        "AccountName": account.get("Name"),
        "Name": record.get("Name"),
        "Opportunity": record.get("Name"),
    }
    return is_internal_sales_record(normalized)


def _date_key(value: Any) -> str | None:
    text = _text(value)
    return text[:10] if text else None


def _sum_arr(rows: list[dict[str, Any]]) -> float:
    return sum(_number(row.get("APTS_Opportunity_ARR__c")) for row in rows if row.get("Type") in {"Land", "Expand"})


def _sum_acv(rows: list[dict[str, Any]]) -> float:
    return sum(_number(row.get("APTS_Renewal_ACV__c")) for row in rows if row.get("Type") == "Renewal")


def _distinct_positive(values: list[Any]) -> int:
    return len({round(_number(value), 2) for value in values if _number(value) > 0})


def _stage_sort_key(stage: str) -> tuple[int, str]:
    try:
        return int(stage.split(" ", 1)[0]), stage
    except Exception:
        return 99, stage


def _visual_fit_for_rows(
    q2_rows: list[dict[str, Any]], fy26_renewal_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    arr_rows = [row for row in q2_rows if row.get("Type") in {"Land", "Expand"}]
    renewal_q2 = [row for row in q2_rows if row.get("Type") == "Renewal"]
    stage_counts = Counter(_text(row.get("StageName")) for row in arr_rows)
    forecast_counts = Counter(_text(row.get("ForecastCategoryName")) for row in arr_rows)
    owner_counts = Counter(_text(_owner(row).get("Name")) for row in arr_rows)
    country_counts = Counter(_text(_account(row).get("BillingCountry")) for row in arr_rows)
    industry_counts = Counter(_text(_account(row).get("Industry")) for row in arr_rows)
    stage_industry = {
        (_text(row.get("StageName")), _text(_account(row).get("Industry")))
        for row in arr_rows
        if _text(row.get("StageName")) and _text(_account(row).get("Industry"))
    }
    approval_gaps = [
        row
        for row in arr_rows
        if _text(row.get("StageName")) in STAGE_3PLUS and not bool(row.get("Stage_20_Approval__c"))
    ]
    scatter_x = _distinct_positive([row.get("Probability") for row in arr_rows])
    scatter_y = _distinct_positive([row.get("APTS_Opportunity_ARR__c") for row in arr_rows])
    q2_renewal_dates = sorted({date for row in renewal_q2 if (date := _date_key(row.get("CloseDate")))})
    fy26_renewal_dates = sorted({date for row in fy26_renewal_rows if (date := _date_key(row.get("CloseDate")))})
    close_dates = sorted({date for row in arr_rows if (date := _date_key(row.get("CloseDate")))})
    no_activity = sum(1 for row in arr_rows if not _text(row.get("LastActivityDate")))
    no_next_step = sum(1 for row in arr_rows if not _text(row.get("NextStep")))
    stage_ordered = dict(sorted(stage_counts.items(), key=lambda item: _stage_sort_key(item[0])))
    return {
        "bar_column": {
            "eligible": len(stage_counts) >= 2 or len(owner_counts) >= 2 or len(forecast_counts) >= 2,
            "stage_counts": stage_ordered,
            "forecast_counts": dict(forecast_counts),
            "owner_count": len(owner_counts),
            "country_count": len(country_counts),
            "use": "stage, forecast, owner, country, aging/stale activity",
        },
        "waterfall": {
            "eligible": "conditional",
            "reason": "needs prior snapshot or workbook movement bridge; live Salesforce alone provides current and QTD rows, not opening movement",
        },
        "scatter_bubble": {
            "eligible": scatter_x >= 2 and scatter_y >= 2,
            "distinct_probability_values": scatter_x,
            "distinct_positive_arr_values": scatter_y,
            "use": "deal risk inspection by probability versus converted ARR",
        },
        "timeline_gantt": {
            "eligible_for_q2_renewals": len(q2_renewal_dates) >= 2,
            "eligible_for_fy26_renewals": len(fy26_renewal_dates) >= 2,
            "q2_renewal_dates": q2_renewal_dates,
            "fy26_renewal_dates": fy26_renewal_dates,
            "arr_close_date_spread": len(close_dates),
        },
        "mekko": {
            "eligible": len(stage_counts) >= 2 and len(industry_counts) >= 2 and len(stage_industry) >= 5,
            "stage_count": len(stage_counts),
            "industry_count": len(industry_counts),
            "non_empty_stage_industry_cells": len(stage_industry),
        },
        "tables": {
            "eligible": len(arr_rows) > 0 or len(renewal_q2) > 0,
            "named_arr_deals": len(arr_rows),
            "named_q2_renewals": len(renewal_q2),
            "approval_gap_rows": len(approval_gaps),
            "approval_gap_arr_eur": round(_sum_arr(approval_gaps), 2),
        },
        "action_register": {
            "eligible": True,
            "gantt_eligible_from_salesforce": False,
            "reason": "Salesforce NextStep is text and action due dates are not structured enough for a real Gantt",
            "no_activity_rows": no_activity,
            "no_next_step_rows": no_next_step,
        },
        "map": {
            "eligible": len(country_counts) >= 2,
            "country_counts": dict(country_counts),
            "fallback": "ranked country bar",
        },
    }


def _recommendations(fit: dict[str, Any]) -> tuple[list[str], list[str]]:
    recommended: list[str] = []
    avoid: list[str] = []
    if fit["bar_column"]["eligible"]:
        recommended.append("Bar/Column for stage, forecast, owner, and geography rankings")
    if fit["scatter_bubble"]["eligible"]:
        recommended.append("Scatter/Bubble for named Q2 deal-risk inspection")
    else:
        avoid.append("Scatter/Bubble unless a better risk axis is introduced")
    if fit["timeline_gantt"]["eligible_for_fy26_renewals"]:
        recommended.append("Timeline/Gantt for renewal ACV milestone spread")
    else:
        avoid.append("Renewal Timeline/Gantt; close dates collapse")
    if fit["mekko"]["eligible"]:
        recommended.append("Mekko candidate for stage x industry mix")
    else:
        avoid.append("Mekko; matrix is too sparse or one-dimensional")
    recommended.append("Tables/table-image lane for named deals, approval gaps, renewals, and actions")
    avoid.append("Action Gantt from current Salesforce fields; keep decision register")
    avoid.append("Funnels for the SimCorp 8-stage process")
    return recommended, avoid


def _top_deals(rows: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    arr_rows = [row for row in rows if row.get("Type") in {"Land", "Expand"}]
    ranked = sorted(arr_rows, key=lambda row: _number(row.get("APTS_Opportunity_ARR__c")), reverse=True)
    output: list[dict[str, Any]] = []
    for row in ranked[:limit]:
        output.append(
            {
                "account": _text(_account(row).get("Name")),
                "opportunity": _text(row.get("Name")),
                "owner": _text(_owner(row).get("Name")),
                "stage": _text(row.get("StageName")),
                "forecast": _text(row.get("ForecastCategoryName")),
                "close_date": _date_key(row.get("CloseDate")),
                "arr_eur_converted": round(_number(row.get("APTS_Opportunity_ARR__c")), 2),
                "probability": _number(row.get("Probability")),
            }
        )
    return output


def _build_report(target_org: str) -> dict[str, Any]:
    q2_query = f"""
        SELECT Id, Name, Type, StageName, ForecastCategoryName, Probability,
               CloseDate, CreatedDate, LastActivityDate, NextStep,
               Owner.Name, Account.Name, Account.BillingCountry, Account.Region__c,
               Account.Industry, CurrencyIsoCode,
               convertCurrency(APTS_Opportunity_ARR__c),
               convertCurrency(APTS_Renewal_ACV__c),
               Stage_20_Approval__c, Submit_for_Stage_20_Review_Date__c
        FROM Opportunity
        WHERE IsClosed = false
          AND CloseDate >= {Q2_START.isoformat()}
          AND CloseDate <= {Q2_END.isoformat()}
          AND Type IN ('Land','Expand','Renewal')
    """
    fy26_renewal_query = f"""
        SELECT Id, Name, Type, StageName, ForecastCategoryName, Probability,
               CloseDate, Owner.Name, Account.Name, Account.BillingCountry,
               Account.Region__c, Account.Industry, CurrencyIsoCode,
               convertCurrency(APTS_Renewal_ACV__c)
        FROM Opportunity
        WHERE IsClosed = false
          AND CloseDate >= {Q2_START.isoformat()}
          AND CloseDate <= {FY26_END.isoformat()}
          AND Type = 'Renewal'
    """
    q2_raw = _run_sf_query(" ".join(q2_query.split()), target_org)
    fy26_renewals_raw = _run_sf_query(" ".join(fy26_renewal_query.split()), target_org)
    directors: list[DirectorVisualFit] = []
    totals = {
        "q2_raw_rows": len(q2_raw),
        "q2_publishable_rows": 0,
        "q2_internal_rows_removed": 0,
        "sf_target_org": target_org,
        "q2_window": [Q2_START.isoformat(), Q2_END.isoformat()],
        "renewal_window": [Q2_START.isoformat(), FY26_END.isoformat()],
        "currency_basis": "SOQL convertCurrency(...) values returned by Salesforce CLI; treated as org/reporting currency EUR for deck eligibility and directional totals.",
    }
    for director in canonical_directors():
        scoped_q2 = [row for row in q2_raw if _director_match(row, director)]
        scoped_renewals = [row for row in fy26_renewals_raw if _director_match(row, director)]
        publishable_q2 = [row for row in scoped_q2 if not _is_internal(row)]
        publishable_renewals = [row for row in scoped_renewals if not _is_internal(row)]
        removed = len(scoped_q2) - len(publishable_q2)
        totals["q2_publishable_rows"] += len(publishable_q2)
        totals["q2_internal_rows_removed"] += removed
        fit = _visual_fit_for_rows(publishable_q2, publishable_renewals)
        recommended, avoid = _recommendations(fit)
        q2_arr_rows = [row for row in publishable_q2 if row.get("Type") in {"Land", "Expand"}]
        q2_renewal_rows = [row for row in publishable_q2 if row.get("Type") == "Renewal"]
        directors.append(
            DirectorVisualFit(
                director=str(director["name"]),
                territory=str(director["scope_label"]),
                q2_open_arr_count=len(q2_arr_rows),
                q2_open_arr_eur=round(_sum_arr(q2_arr_rows), 2),
                q2_open_renewal_count=len(q2_renewal_rows),
                q2_open_renewal_acv_eur=round(_sum_acv(q2_renewal_rows), 2),
                fy26_open_renewal_count=len(publishable_renewals),
                fy26_open_renewal_acv_eur=round(_sum_acv(publishable_renewals), 2),
                internal_rows_removed=removed,
                visual_fit=fit,
                recommended_this_quarter=recommended,
                avoid_this_quarter=avoid,
                top_deal_rows=_top_deals(publishable_q2),
            )
        )
    family_counts: dict[str, int] = defaultdict(int)
    for director in directors:
        fit = director.visual_fit
        if fit["bar_column"]["eligible"]:
            family_counts["bar_column"] += 1
        if fit["scatter_bubble"]["eligible"]:
            family_counts["scatter_bubble"] += 1
        if fit["timeline_gantt"]["eligible_for_fy26_renewals"]:
            family_counts["timeline_gantt_fy26_renewals"] += 1
        if fit["timeline_gantt"]["eligible_for_q2_renewals"]:
            family_counts["timeline_gantt_q2_renewals"] += 1
        if fit["mekko"]["eligible"]:
            family_counts["mekko"] += 1
        if fit["map"]["eligible"]:
            family_counts["map"] += 1
    return {
        "schema": "thinkcell-quarter-salesforce-fit/v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "period": "2026-Q2",
        "deck_month": "May 2026",
        "totals": totals,
        "family_eligibility_counts": dict(sorted(family_counts.items())),
        "directors": [asdict(director) for director in directors],
    }


def _fmt_eur(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"EUR {value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"EUR {value / 1_000:.0f}K"
    return f"EUR {value:.0f}"


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# think-cell Quarter Deck Salesforce Fit",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Period: `{payload['period']}`",
        f"- Salesforce target: `{payload['totals']['sf_target_org']}`",
        f"- Q2 source rows: `{payload['totals']['q2_raw_rows']}` raw, `{payload['totals']['q2_publishable_rows']}` publishable after internal/test filters",
        f"- Internal/test Q2 rows removed: `{payload['totals']['q2_internal_rows_removed']}`",
        f"- Currency basis: {payload['totals']['currency_basis']}",
        "",
        "## Family Eligibility",
        "",
        "| Family | Eligible directors | Production implication |",
        "|---|---:|---|",
    ]
    counts = payload["family_eligibility_counts"]
    implications = {
        "bar_column": "Use broadly for stage, forecast, owner, and geography rankings.",
        "scatter_bubble": "Use where deal probability and ARR both have spread.",
        "timeline_gantt_fy26_renewals": "Use for FY26 renewal milestone spread; fallback to table where dates collapse.",
        "timeline_gantt_q2_renewals": "Use only when Q2 renewal dates have spread.",
        "mekko": "Rare candidate; only if stage x industry is dense.",
        "map": "Geography has some spread, but ranked bars remain the default.",
    }
    for key, value in counts.items():
        lines.append(f"| `{key}` | {value}/9 | {implications.get(key, '')} |")
    lines += [
        "",
        "## Director Detail",
        "",
        "| Director | Territory | Q2 L+E rows | Q2 ARR | Q2 renewal rows | Q2 ACV | FY26 renewal rows | FY26 ACV | Scatter | Renewal timeline | Mekko | Removed |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for director in payload["directors"]:
        fit = director["visual_fit"]
        lines.append(
            "| {director} | {territory} | {arr_count} | {arr} | {ren_count} | {acv} | {fyren_count} | {fyacv} | {scatter} | {timeline} | {mekko} | {removed} |".format(
                director=director["director"],
                territory=director["territory"],
                arr_count=director["q2_open_arr_count"],
                arr=_fmt_eur(director["q2_open_arr_eur"]),
                ren_count=director["q2_open_renewal_count"],
                acv=_fmt_eur(director["q2_open_renewal_acv_eur"]),
                fyren_count=director["fy26_open_renewal_count"],
                fyacv=_fmt_eur(director["fy26_open_renewal_acv_eur"]),
                scatter="yes" if fit["scatter_bubble"]["eligible"] else "no",
                timeline="yes" if fit["timeline_gantt"]["eligible_for_fy26_renewals"] else "no",
                mekko="yes" if fit["mekko"]["eligible"] else "no",
                removed=director["internal_rows_removed"],
            )
        )
    lines += ["", "## This-Quarter Recommendation", ""]
    lines += [
        "- Keep Bar/Column as the default live chart family across all regions.",
        "- Add Scatter/Bubble only for directors where probability and converted ARR both have real spread.",
        "- Add Renewal Timeline/Gantt conditionally from FY26 renewal close dates; use table-only where dates collapse.",
        "- Keep dense table-image slides for named deals, approval gaps, renewals, owner coaching, and decisions.",
        "- Do not turn action items into Gantt charts from current Salesforce fields; `NextStep` is text, not a structured milestone date.",
        "- Do not use funnels for the SimCorp 8-stage process.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-org", default="preprod")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "state" / "2026-Q2" / "__regional__" / "thinkcell_sf_fit",
    )
    args = parser.parse_args()
    payload = _build_report(args.target_org)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "thinkcell_quarter_salesforce_fit.json"
    md_path = args.output_dir / "thinkcell_quarter_salesforce_fit.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _write_markdown(payload, md_path)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "status": "pass"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
