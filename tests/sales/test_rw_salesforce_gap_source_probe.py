"""Tests for RW Salesforce source-gap probe rendering."""

from __future__ import annotations

from scripts.sales.rw_salesforce_gap_source_probe import build_findings, to_markdown


def _probe_fixture() -> dict:
    return {
        "schema": "rw-salesforce-gap-source-probe.v1",
        "generated_at": "2026-05-10T12:00:00+00:00",
        "guardrail": (
            "ARR is Land+Expand only; Renewal ACV is Renewal only. "
            "Total Open Pipeline Value is the only explicitly labeled cross-motion value."
        ),
        "queries": {
            "opportunity_one_off_revenue": {
                "records": [
                    {
                        "c": 10,
                        "ps_one_off": 20_000,
                        "ps_non_recurring": 200_000,
                        "pso_one_off": 30_000,
                    }
                ]
            },
            "asset_line_item_active_arr": {"records": [{"c": 100, "arr": 400_000_000}]},
            "asset_line_item_density": {
                "records": [
                    {
                        "total": 1_000,
                        "renewal_adj_count": 0,
                        "renewal_adj_type_count": 0,
                    }
                ]
            },
            "asset_line_item_risk_arr": {
                "records": [
                    {"risk": "High", "c": 10, "arr": 60_000_000},
                    {"risk": "Medium", "c": 20, "arr": 40_000_000},
                    {"risk": "Low", "c": 70, "arr": 300_000_000},
                ]
            },
            "forecasting_quota_summary": {
                "records": [{"c": 36, "max_date": "2023-10-01", "quota": 165_000_000}]
            },
            "opportunity_current_year_quota": {"records": [{"c": 100, "quota_count": 0}]},
            "forecasting_item_summary": {"records": [{"c": 42_920}]},
            "forecasting_fact_summary": {"records": [{"total": 36_979}]},
        },
        "reports": {
            "synergy_deals_pipeline_report": {
                "name": "Synergy Deals in Pipeline",
                "totals": ["0E-18", "0E-18", 0],
            }
        },
    }


def test_build_findings_classifies_bridgeable_and_blocked_sources():
    probe = _probe_fixture()
    findings = {tuple(finding["kpis"]): finding for finding in build_findings(probe)}

    assert findings[("existing_arr_run_rate",)]["status"] == "bridge_found"
    assert findings[("business_at_risk",)]["status"] == "bridge_found"
    assert findings[("one_off_revenues",)]["status"] == "bridge_found"
    assert findings[("pipeline_coverage_3x",)]["status"] == "source_found_but_not_current"
    assert findings[("forecast_accuracy",)]["status"] == "source_found_snapshot_needed"
    assert findings[("indexation_arr_growth",)]["status"] == "blocked_no_populated_source"
    assert findings[("synergy_deals_won", "synergy_deals_pipe")]["status"] == "report_found_but_not_field_grade"


def test_markdown_keeps_guardrail_and_next_engineering_moves():
    probe = _probe_fixture()
    probe["findings"] = build_findings(probe)
    markdown = to_markdown(probe)

    assert "ARR is Land+Expand only; Renewal ACV is Renewal only" in markdown
    assert "Bridgeable now from Salesforce: 3 KPI groups" in markdown
    assert "`existing_arr_run_rate`" in markdown
    assert "`business_at_risk`" in markdown
    assert "`one_off_revenues`" in markdown
    assert "Do not call pipeline coverage solid until a current 2026 quota denominator is identified" in markdown
    assert "Do not use Land won count as Synergy" in markdown
