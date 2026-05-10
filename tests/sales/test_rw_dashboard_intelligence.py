"""Tests for the RW dashboard KPI intelligence matrix."""

from __future__ import annotations

from scripts.sales.rw_dashboard_intelligence import (
    build_intelligence_rows,
    rollup,
    to_markdown,
)
from scripts.sales.rw_kpi_graph import GRAPH
from scripts.sales.rw_page_kpi_contract import PAGE_KPI_CONTRACTS


def _row_map():
    return {row.kpi_id: row for row in build_intelligence_rows()}


def test_intelligence_matrix_covers_all_31_rw_kpis():
    rows = build_intelligence_rows()
    graph_ids = {kpi.kpi_id for kpi in GRAPH.kpis}
    page_ids = {
        kpi_id
        for contract in PAGE_KPI_CONTRACTS.values()
        for kpi_id in contract.kpi_ids
    }

    assert len(rows) == 31
    assert {row.kpi_id for row in rows} == graph_ids
    assert page_ids <= graph_ids


def test_rollup_keeps_proxy_kpis_out_of_cleanly_surfaced_count():
    counts = rollup(build_intelligence_rows())

    assert counts == {
        "total_kpis": 31,
        "surfaced": 14,
        "surfaced_partial": 6,
        "model_available_not_surfaced": 3,
        "partial_data_or_measure_gap": 3,
        "source_data_gap": 5,
    }


def test_partial_statuses_call_out_the_actual_missing_measure():
    rows = _row_map()

    assert rows["pipeline_coverage_3x"].dashboard_status == "surfaced_partial"
    assert "Pipeline Coverage Ratio" in rows["pipeline_coverage_3x"].missing_measures
    assert rows["forecast_accuracy"].dashboard_status == "surfaced_partial"
    assert "Forecast Accuracy" in rows["forecast_accuracy"].missing_measures
    assert rows["stage3_approvals_compliance"].dashboard_status == "surfaced_partial"
    assert "Commercial Approval Compliance Pct" in (
        rows["stage3_approvals_compliance"].missing_measures
    )
    assert rows["existing_arr_run_rate"].dashboard_status == "surfaced_partial"
    assert rows["indexation_arr_growth"].dashboard_status == "surfaced_partial"
    assert rows["synergy_deals_won"].dashboard_status == "surfaced_partial"


def test_model_available_queue_identifies_fast_page_upgrades():
    rows = _row_map()
    fast_page_upgrades = {
        kpi_id
        for kpi_id, row in rows.items()
        if row.dashboard_status == "model_available_not_surfaced"
    }

    assert fast_page_upgrades == {
        "sales_cycle_length",
        "closed_won_avg_deal_size",
        "lost_arr_quarterly",
    }


def test_markdown_preserves_cardinal_rule_and_upgrade_lanes():
    markdown = to_markdown(build_intelligence_rows())

    assert (
        "ARR is Land+Expand only; Renewal ACV is Renewal only" in markdown
    )
    assert (
        "The only cross-motion value measure remains `Total Open Pipeline Value`"
        in markdown
    )
    assert "## Immediate Upgrade Lanes" in markdown
    assert "| KG Source Status | Dashboard Status |" in markdown
    assert "`pipeline_coverage_3x`: Add quota denominator" in markdown
