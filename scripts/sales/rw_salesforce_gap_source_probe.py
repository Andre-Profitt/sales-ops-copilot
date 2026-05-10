"""Probe Salesforce sources that can close the remaining RW KPI gaps.

This is a read-only source-discovery harness. It does not publish to Fabric and
does not write credentials. It answers whether the non-solid RW KPIs are true
Salesforce source gaps or just unstaged/model gaps.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


SF_ORG = "preprod"
API_VERSION = "66.0"

DEFAULT_MARKDOWN = Path("docs/sales/RW_SALESFORCE_GAP_SOURCE_PROBE.md")
DEFAULT_JSON = (
    Path("output")
    / "rw_dashboard_harness"
    / "salesforce_gap_source_probe"
    / "rw_salesforce_gap_source_probe.json"
)

SYNERGY_REPORTS = {
    "synergy_deals_pipeline_report": "00OTb000008TYcnMAG",
    "synergy_deals_closed_won_report": "00OTb000008TZIjMAO",
}


@dataclass(frozen=True)
class QuerySpec:
    label: str
    soql: str


QUERY_SPECS: dict[str, QuerySpec] = {
    "opportunity_quota_by_record_type": QuerySpec(
        label="Opportunity quota fields by record type",
        soql="""
            SELECT RecordType.Name rt, COUNT(Id) c, COUNT(Quota_Amount__c) quota_count,
                   SUM(Quota_Amount__c) quota_sum
            FROM Opportunity
            GROUP BY RecordType.Name
            ORDER BY COUNT(Id) DESC
        """,
    ),
    "opportunity_current_year_quota": QuerySpec(
        label="Opportunity current fiscal year quota",
        soql="""
            SELECT COUNT(Id) c, COUNT(Quota_Amount__c) quota_count, SUM(Quota_Amount__c) quota_sum
            FROM Opportunity
            WHERE CloseDate = THIS_FISCAL_YEAR
        """,
    ),
    "forecasting_quota_summary": QuerySpec(
        label="ForecastingQuota date coverage",
        soql="""
            SELECT MIN(StartDate) min_date, MAX(StartDate) max_date, COUNT(Id) c, SUM(QuotaAmount) quota
            FROM ForecastingQuota
        """,
    ),
    "forecasting_item_summary": QuerySpec(
        label="ForecastingItem freshness",
        soql="""
            SELECT MIN(SystemModstamp) min_stamp, MAX(SystemModstamp) max_stamp, COUNT(Id) c
            FROM ForecastingItem
        """,
    ),
    "forecasting_fact_summary": QuerySpec(
        label="ForecastingFact opportunity grain",
        soql="""
            SELECT COUNT(Id) total, COUNT(ForecastedObjectId) opp_line_count, COUNT(OpportunityId) opp_count
            FROM ForecastingFact
        """,
    ),
    "asset_line_item_density": QuerySpec(
        label="Apttus asset line item density",
        soql="""
            SELECT COUNT(Id) total, COUNT(APTS_Asset_Line_Item_ARR__c) arr_count,
                   COUNT(Apttus_Config2__EndDate__c) end_count,
                   COUNT(Apttus_Config2__RenewalAdjustmentAmount__c) renewal_adj_count,
                   COUNT(Apttus_Config2__RenewalAdjustmentType__c) renewal_adj_type_count,
                   COUNT(APTS_Renewal_Scope__c) renewal_scope_count
            FROM Apttus_Config2__AssetLineItem__c
        """,
    ),
    "asset_line_item_active_arr": QuerySpec(
        label="Current active asset ARR",
        soql="""
            SELECT COUNT(Id) c, SUM(APTS_Asset_Line_Item_ARR__c) arr
            FROM Apttus_Config2__AssetLineItem__c
            WHERE Apttus_Config2__IsInactive__c = false
              AND Apttus_Config2__EndDate__c >= TODAY
        """,
    ),
    "asset_line_item_risk_arr": QuerySpec(
        label="Current active asset ARR by account termination risk",
        soql="""
            SELECT Apttus_Config2__AccountId__r.Risk_of_Potential_Termination__c risk,
                   COUNT(Id) c, SUM(APTS_Asset_Line_Item_ARR__c) arr
            FROM Apttus_Config2__AssetLineItem__c
            WHERE Apttus_Config2__IsInactive__c = false
              AND Apttus_Config2__EndDate__c >= TODAY
            GROUP BY Apttus_Config2__AccountId__r.Risk_of_Potential_Termination__c
        """,
    ),
    "opportunity_one_off_revenue": QuerySpec(
        label="Opportunity one-off/non-recurring revenue fields",
        soql="""
            SELECT COUNT(Id) c,
                   SUM(APTS_RH_PS_One_Off__c) ps_one_off,
                   SUM(APTS_PS_Non_Recurring_NPP_Display__c) ps_non_recurring,
                   SUM(APTS_RH_3rd_Party_One_Off__c) third_party_one_off,
                   SUM(APTS_CDD_One_Off_TCV_Display__c) cdd_one_off,
                   SUM(APTS_PSO_One_Off_TCV_Display__c) pso_one_off,
                   SUM(APTS_RUS_PSI_PSA_One_Off__c) psi_psa_one_off
            FROM Opportunity
            WHERE CloseDate = THIS_FISCAL_YEAR
        """,
    ),
    "opportunity_line_item_revenue_density": QuerySpec(
        label="OpportunityLineItem product/revenue stream density",
        soql="""
            SELECT COUNT(Id) total, COUNT(Revenue_Stream__c) rev_stream,
                   COUNT(Revenue_Stream_Input__c) rev_stream_input,
                   COUNT(Product_Family__c) product_family,
                   COUNT(APTS_Revenue_Stream__c) apts_rev_stream,
                   COUNT(APTS_Net_Product_Price__c) net_price,
                   COUNT(APTS_Opportunity_Product_ARR__c) arr
            FROM OpportunityLineItem
        """,
    ),
    "synergy_name_signal": QuerySpec(
        label="Opportunity name contains Synergy",
        soql="""
            SELECT Type, IsClosed, IsWon, COUNT(Id) c,
                   SUM(APTS_Opportunity_ARR__c) arr,
                   SUM(APTS_Forecast_ARR__c) forecast_arr,
                   SUM(Opportunity_Average_ACV__c) avg_acv
            FROM Opportunity
            WHERE Name LIKE '%Synergy%'
            GROUP BY Type, IsClosed, IsWon
            ORDER BY COUNT(Id) DESC
        """,
    ),
}


def _compact_soql(soql: str) -> str:
    return " ".join(soql.split())


def _run_json(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": (proc.stderr or proc.stdout)[-2000:],
            "records": [],
        }
    data = json.loads(proc.stdout)
    return {"ok": True, "data": data, "records": data.get("result", {}).get("records", [])}


def _run_soql(soql: str) -> dict[str, Any]:
    return _run_json(
        [
            "sf",
            "data",
            "query",
            "--target-org",
            SF_ORG,
            "--api-version",
            API_VERSION,
            "--query",
            _compact_soql(soql),
            "--json",
        ]
    )


def _sf_org_context() -> tuple[str, str]:
    data = _run_json(["sf", "org", "display", "--target-org", SF_ORG, "--json"])
    result = data.get("data", {}).get("result", {})
    token = result.get("accessToken")
    instance_url = result.get("instanceUrl")
    if not token or not instance_url:
        raise RuntimeError("Unable to read Salesforce org context from sf CLI")
    return instance_url, token


def _report_payloads() -> dict[str, Any]:
    instance_url, token = _sf_org_context()
    headers = {"Authorization": f"Bearer {token}"}
    out: dict[str, Any] = {}
    for key, report_id in SYNERGY_REPORTS.items():
        base = f"{instance_url}/services/data/v{API_VERSION}/analytics/reports/{report_id}"
        describe = requests.get(f"{base}/describe", headers=headers, timeout=60)
        run = requests.get(f"{base}?includeDetails=false", headers=headers, timeout=60)
        describe.raise_for_status()
        run.raise_for_status()
        meta = describe.json().get("reportMetadata", {})
        result = run.json()
        out[key] = {
            "report_id": report_id,
            "name": meta.get("name"),
            "report_type": meta.get("reportType", {}).get("type"),
            "detail_columns": meta.get("detailColumns", []),
            "aggregates": meta.get("aggregates", []),
            "report_filters": meta.get("reportFilters", []),
            "standard_filters": meta.get("standardFilters", []),
            "totals": [
                agg.get("value")
                for agg in result.get("factMap", {}).get("T!T", {}).get("aggregates", [])
            ],
        }
    return out


def _first_record(probe: dict[str, Any], key: str) -> dict[str, Any]:
    records = probe["queries"].get(key, {}).get("records", [])
    return records[0] if records else {}


def _risk_high_medium_sum(records: list[dict[str, Any]]) -> float:
    return sum(float(row.get("arr") or 0) for row in records if row.get("risk") in {"High", "Medium"})


def build_findings(probe: dict[str, Any]) -> list[dict[str, Any]]:
    one_off = _first_record(probe, "opportunity_one_off_revenue")
    active_arr = _first_record(probe, "asset_line_item_active_arr")
    asset_density = _first_record(probe, "asset_line_item_density")
    quota = _first_record(probe, "forecasting_quota_summary")
    opp_quota = _first_record(probe, "opportunity_current_year_quota")
    forecast_items = _first_record(probe, "forecasting_item_summary")
    forecast_facts = _first_record(probe, "forecasting_fact_summary")
    risk_records = probe["queries"].get("asset_line_item_risk_arr", {}).get("records", [])
    synergy_reports = probe.get("reports", {})
    synergy_totals = [
        total
        for report in synergy_reports.values()
        for total in report.get("totals", [])
        if total not in (None, "0E-18", 0)
    ]

    return [
        {
            "kpis": ["existing_arr_run_rate"],
            "status": "bridge_found",
            "source": "Apttus_Config2__AssetLineItem__c",
            "evidence": (
                f"{int(active_arr.get('c') or 0):,} current active/non-expired asset rows; "
                f"ARR sum {float(active_arr.get('arr') or 0):,.0f}."
            ),
            "implementation": "Stage f_asset_line_item and add active ARR run-rate measures by account, product, region, and renewal quarter.",
        },
        {
            "kpis": ["business_at_risk"],
            "status": "bridge_found",
            "source": "AssetLineItem + Account.Risk_of_Potential_Termination__c",
            "evidence": (
                f"High/Medium risk active ARR sum {_risk_high_medium_sum(risk_records):,.0f}; "
                "grain is active asset ARR, not renewal-opportunity ACV."
            ),
            "implementation": "Replace Renewal opp-risk proxy with active-base ARR at risk, grouped by account risk and renewal/end date.",
        },
        {
            "kpis": ["one_off_revenues"],
            "status": "bridge_found",
            "source": "Opportunity one-off fields plus OpportunityLineItem revenue stream/product family",
            "evidence": (
                f"Current FY PS non-recurring sum {float(one_off.get('ps_non_recurring') or 0):,.0f}; "
                f"PS one-off {float(one_off.get('ps_one_off') or 0):,.0f}; "
                f"PSO one-off {float(one_off.get('pso_one_off') or 0):,.0f}."
            ),
            "implementation": "Stage one-off amount columns and/or f_opportunity_line_item to build a non-recurring revenue page/ledger.",
        },
        {
            "kpis": ["pipeline_coverage_3x"],
            "status": "source_found_but_not_current",
            "source": "ForecastingQuota and Opportunity Quota record type",
            "evidence": (
                f"ForecastingQuota has {int(quota.get('c') or 0):,} rows through {quota.get('max_date')}; "
                f"current FY Opportunity quota_count={int(opp_quota.get('quota_count') or 0)}."
            ),
            "implementation": "Do not use as 2026 denominator yet. Need current quota/target feed or confirmed quota object scope.",
        },
        {
            "kpis": ["forecast_accuracy"],
            "status": "source_found_snapshot_needed",
            "source": "ForecastingItem and ForecastingFact",
            "evidence": (
                f"ForecastingItem rows={int(forecast_items.get('c') or 0):,}; "
                f"ForecastingFact rows={int(forecast_facts.get('total') or 0):,}. "
                "These are current-state forecast objects, not an as-of forecast submission history."
            ),
            "implementation": "Stage daily/weekly f_forecast_snapshot now; backtest accuracy once snapshots exist against actual closed won ARR.",
        },
        {
            "kpis": ["indexation_arr_growth"],
            "status": "blocked_no_populated_source",
            "source": "Apttus asset renewal adjustment fields",
            "evidence": (
                f"AssetLineItem renewal adjustment count={int(asset_density.get('renewal_adj_count') or 0)}; "
                f"renewal adjustment type count={int(asset_density.get('renewal_adj_type_count') or 0)}."
            ),
            "implementation": "Find a different uplift/indexation source or get the commercial field populated; current asset object does not close this.",
        },
        {
            "kpis": ["synergy_deals_won", "synergy_deals_pipe"],
            "status": "report_found_but_not_field_grade",
            "source": "Existing Salesforce Synergy reports",
            "evidence": (
                "Reports filter Opportunity Name contains 'Synergy' and currently return zero totals. "
                f"Non-zero report totals found={len(synergy_totals)}."
            ),
            "implementation": "Either accept the report definition as official zero, or add/stage a trusted Synergy flag; do not count Land won as Synergy.",
        },
    ]


def build_probe() -> dict[str, Any]:
    queries: dict[str, Any] = {}
    for key, spec in QUERY_SPECS.items():
        result = _run_soql(spec.soql)
        queries[key] = {
            "label": spec.label,
            "soql": _compact_soql(spec.soql),
            "ok": result["ok"],
            "records": result["records"],
            **({"error": result["error"]} if not result["ok"] else {}),
        }
    probe = {
        "schema": "rw-salesforce-gap-source-probe.v1",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sf_org": SF_ORG,
        "api_version": API_VERSION,
        "guardrail": (
            "ARR is Land+Expand only; Renewal ACV is Renewal only. "
            "Total Open Pipeline Value is the only explicitly labeled cross-motion value."
        ),
        "queries": queries,
        "reports": _report_payloads(),
    }
    probe["findings"] = build_findings(probe)
    return probe


def _md_cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def to_markdown(probe: dict[str, Any]) -> str:
    findings = probe["findings"]
    bridge = [f for f in findings if f["status"] == "bridge_found"]
    partial = [
        f
        for f in findings
        if f["status"] in {"source_found_but_not_current", "source_found_snapshot_needed", "report_found_but_not_field_grade"}
    ]
    blocked = [f for f in findings if f["status"] == "blocked_no_populated_source"]

    lines = [
        "# RW Salesforce Gap Source Probe",
        "",
        "Read-only probe against Salesforce via `sf` CLI and Report REST. It does not publish to Fabric.",
        "",
        f"Generated: `{probe['generated_at']}`",
        "",
        f"Cardinal guardrail: {probe['guardrail']}",
        "",
        "## Answer",
        "",
        f"- Bridgeable now from Salesforce: {len(bridge)} KPI groups.",
        f"- Salesforce source exists but is not solid production coverage yet: {len(partial)} KPI groups.",
        f"- Still blocked by missing/population issue: {len(blocked)} KPI groups.",
        "",
        "## Findings",
        "",
        "| KPI(s) | Status | Source | Evidence | Implementation move |",
        "| --- | --- | --- | --- | --- |",
    ]
    for finding in findings:
        lines.append(
            "| "
            + " | ".join(
                [
                    ", ".join(f"`{kpi}`" for kpi in finding["kpis"]),
                    finding["status"],
                    _md_cell(finding["source"]),
                    _md_cell(finding["evidence"]),
                    _md_cell(finding["implementation"]),
                ]
            )
            + " |"
        )

    lines += [
        "",
        "## Engineering Read",
        "",
        "- Stage `Apttus_Config2__AssetLineItem__c` next. It can replace the renewal-risk proxy with active-base ARR and unlock existing ARR run-rate.",
        "- Stage one-off Opportunity fields or `OpportunityLineItem` next. Salesforce already has non-recurring/one-off signal; this is not a true source gap.",
        "- Do not call pipeline coverage solid until a current 2026 quota denominator is identified. Existing quota records are stale for this dashboard.",
        "- Start a ForecastingItem/ForecastingFact snapshot table now. True forecast accuracy needs as-of snapshots, not just current forecast state.",
        "- Do not use Land won count as Synergy. Existing Synergy reports are name-filtered and zero today; use that definition only if RW accepts it as official.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(
    markdown_path: Path = DEFAULT_MARKDOWN,
    json_path: Path = DEFAULT_JSON,
    probe: dict[str, Any] | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    result = probe or build_probe()
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(to_markdown(result), encoding="utf-8")
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return markdown_path, json_path, result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    markdown_path, json_path, result = write_outputs(args.markdown, args.json)
    print(f"salesforce gap source markdown: {markdown_path}")
    print(f"salesforce gap source json: {json_path}")
    for finding in result["findings"]:
        print(f"{','.join(finding['kpis'])}: {finding['status']}")


if __name__ == "__main__":
    main()
