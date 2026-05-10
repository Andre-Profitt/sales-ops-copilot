"""Contract tests for the RW KPI-targeted Power BI pages."""

from __future__ import annotations

import json

from scripts.sales.rw_compose_all_pages import compose_report, validate_contract_pages
from scripts.sales.rw_dashboard_harness import audit
from scripts.sales.rw_page_kpi_contract import PAGE_KPI_CONTRACTS, required_measures


def _visual_type(vc: dict) -> str:
    return json.loads(vc["config"])["singleVisual"]["visualType"]


def _page(report: dict, display_name: str) -> dict:
    return next(s for s in report["sections"] if s["displayName"] == display_name)


def test_all_target_pages_compose_against_declared_kpi_contracts():
    report = compose_report({"sections": []})

    assert set(PAGE_KPI_CONTRACTS) <= {s["displayName"] for s in report["sections"]}
    assert validate_contract_pages(report) == []
    for page in PAGE_KPI_CONTRACTS:
        assert _page(report, page)["visualContainers"], page


def test_target_pages_use_only_native_power_bi_visual_types():
    report = compose_report({"sections": []})
    allowed = {"basicShape", "textbox", "card", "tableEx", "clusteredBarChart", "pivotTable"}

    unexpected: list[tuple[str, str]] = []
    for page in PAGE_KPI_CONTRACTS:
        for vc in _page(report, page)["visualContainers"]:
            visual_type = _visual_type(vc)
            if visual_type not in allowed:
                unexpected.append((page, visual_type))

    assert unexpected == []


def test_target_pages_have_no_plain_card_or_plain_table_visual_debt():
    report = compose_report({"sections": []})
    findings = [
        finding
        for finding in audit(report)
        if finding.startswith("[plain-card]") or finding.startswith("[plain-table]")
    ]

    assert findings == []


def test_total_open_pipeline_value_is_the_only_cross_motion_measure():
    report = compose_report({"sections": []})
    encoded_by_page = {
        section["displayName"]: "\n".join(v["config"] for v in section["visualContainers"])
        for section in report["sections"]
    }

    pages_with_cross_motion_value = [
        page for page, encoded in encoded_by_page.items() if "Total Open Pipeline Value" in encoded
    ]

    assert required_measures() >= {"Total Open Pipeline Value", "Total Open Pipeline ARR"}
    assert pages_with_cross_motion_value == ["Forecast"]
    assert PAGE_KPI_CONTRACTS["Forecast"].caveat.startswith(
        "Total Open Pipeline Value is the only explicit cross-motion value measure"
    )


def test_arr_and_renewal_acv_contracts_stay_separate_by_page():
    renewal_measures = {
        "Total Open Renewal ACV",
        "Total Renewal ACV Due",
        "Renewal Retention Pct (Period)",
        "Total Renewal ACV Won",
        "Total Renewal ACV Lost",
    }
    growth_arr_measures = {
        "Open Land ARR",
        "Open Expand ARR",
        "Partner ARR",
        "Partner Pct",
        "Total Open Pipeline ARR",
        "Total Land Won Count",
    }

    assert set(PAGE_KPI_CONTRACTS["Renewals"].measures) == renewal_measures
    assert set(PAGE_KPI_CONTRACTS["Growth Mix"].measures) == growth_arr_measures
    assert PAGE_KPI_CONTRACTS["Renewals"].motion == "renewal_acv"
    assert PAGE_KPI_CONTRACTS["Growth Mix"].motion == "land_expand_arr"
