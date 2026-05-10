"""Tests for the RW KPI expected-vs-BI coverage checklist."""

from __future__ import annotations

from scripts.sales.rw_kpi_coverage_checklist import build_checklist, to_markdown
from scripts.sales.rw_kpi_graph import GRAPH


def test_checklist_covers_every_expected_rw_kpi_once():
    checklist = build_checklist()
    rows = checklist["rows"]
    graph_ids = {kpi.kpi_id for kpi in GRAPH.kpis}

    assert checklist["schema"] == "rw-kpi-coverage-checklist.v1"
    assert len(rows) == 31
    assert {row["kpi_id"] for row in rows} == graph_ids


def test_checklist_rollup_matches_current_bi_coverage_contract():
    summary = build_checklist()["summary"]

    assert summary["total_kpis"] == 31
    assert summary["covered"] == 23
    assert summary["partial_proxy"] == 6
    assert summary["model_measure_gap"] == 1
    assert summary["source_data_gap"] == 1
    assert summary["usable_on_bi_including_proxy"] == 29
    assert summary["not_dependable_yet"] == 2


def test_checklist_keeps_arr_acv_guardrail_and_clear_status_labels():
    checklist = build_checklist()
    markdown = to_markdown(checklist)

    assert "ARR is Land+Expand only; Renewal ACV is Renewal only" in markdown
    assert "Total Open Pipeline Value is the only explicitly labeled cross-motion value" in markdown
    assert "Checklist legend: `[x]` covered, `[~]` partial/proxy on BI, `[ ]` not dependable yet." in markdown
    assert "| Check | KPI | RW expects | Impact | Motion | BI coverage | Pages | Measure evidence | Gap / next action |" in markdown
    assert "`pipeline_coverage_3x`" in markdown
    assert "Partial/proxy on BI" in markdown
    assert "missing: Pipeline Coverage Ratio" in markdown


def test_high_impact_gap_queue_calls_out_expected_blockers():
    checklist = build_checklist()
    high_gap_ids = {row["kpi_id"] for row in checklist["high_impact_gaps"]}

    assert {
        "pipeline_coverage_3x",
        "forecast_accuracy",
        "existing_arr_run_rate",
        "business_at_risk",
        "synergy_deals_won",
    } <= high_gap_ids


def test_coverage_rows_retain_page_and_measure_evidence():
    rows = {row["kpi_id"]: row for row in build_checklist()["rows"]}

    forecast = rows["forecast_closed_won"]
    assert forecast["check"] == "[x]"
    assert forecast["bi_coverage"] == "Covered"
    assert "Forecast" in forecast["pages"]
    assert "Total Closed Won ARR" in forecast["present_measures"]

    pipeline = rows["pipeline_coverage_3x"]
    assert pipeline["check"] == "[~]"
    assert pipeline["bi_coverage"] == "Partial/proxy on BI"
    assert "Forecast" in pipeline["pages"]
    assert "Pipeline Coverage Ratio" in pipeline["missing_measures"]
