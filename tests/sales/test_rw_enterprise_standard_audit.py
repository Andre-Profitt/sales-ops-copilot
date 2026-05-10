"""Tests for the consolidated RW enterprise/Zebra standard audit."""

from __future__ import annotations

from scripts.sales.rw_compose_all_pages import compose_report
from scripts.sales.rw_enterprise_standard_audit import audit_enterprise_standard
from scripts.sales.rw_page_kpi_contract import PAGE_KPI_CONTRACTS


def test_enterprise_standard_audit_rolls_up_readiness_gates():
    result = audit_enterprise_standard(report=compose_report({"sections": []}))

    assert result["schema"] == "rw-enterprise-zebra-standard.v1"
    assert result["verdict"] == "not_enterprise_ready"
    assert result["summary"]["unit_policy_counts"]["high"] == 0
    assert result["summary"]["visual_qa_counts"]["medium"] == 0
    assert result["summary"]["visual_qa_counts"]["high"] == 0
    assert result["summary"]["data_surface_verdict"] == "not_exec_complete"
    assert any(
        finding["id"] == "kpi_flow_not_enterprise_complete"
        for finding in result["findings"]
    )
    assert not any(finding["lane"] == "zebra visual grammar" for finding in result["findings"])


def test_enterprise_standard_reports_zebra_native_page_coverage():
    result = audit_enterprise_standard(report=compose_report({"sections": []}))
    rows = {row["page"]: row for row in result["zebra_native_page_coverage"]}

    assert set(rows) == {*PAGE_KPI_CONTRACTS, "RW KPI Explorer"}
    assert rows["What Changed"]["zebra_native_visuals"] > 0
    assert rows["Stage Hygiene"]["zebra_native_visuals"] > 0
    assert rows["Forecast"]["zebra_native_coverage"] >= 0.9
    assert rows["Renewals"]["zebra_native_coverage"] >= 0.9
    assert rows["Growth Mix"]["zebra_native_coverage"] >= 0.9
    assert rows["RW KPI Explorer"]["zebra_native_coverage"] >= 0.9


def test_enterprise_standard_backlog_starts_with_data_engineering_spine():
    result = audit_enterprise_standard(report=compose_report({"sections": []}))
    backlog = result["upgrade_backlog"]

    assert backlog[0]["lane"] == "semantic spine"
    assert "d_stage" in backlog[0]["work"]
    assert any(item["lane"] == "forecast data" for item in backlog)
    assert not any(item["lane"].startswith("page:") for item in backlog)
