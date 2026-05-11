"""Tests for visible metric-basis labels on RW Power BI visuals."""

from __future__ import annotations

from scripts.sales._pbir_helpers import build_card_visual
from scripts.sales.rw_compose_all_pages import compose_report
from scripts.sales.rw_metric_basis_audit import audit_metric_basis, rule_for_measure


def _report(page: str, visuals: list[dict]) -> dict:
    return {"sections": [{"displayName": page, "visualContainers": visuals}]}


def test_metric_basis_audit_flags_ambiguous_weighted_rate_label():
    report = _report(
        "VP Ops Scorecard",
        [build_card_visual("f_opportunity", "Win Rate ARR", "Win rate", x=24, y=80)],
    )

    result = audit_metric_basis(report)

    assert result["summary"]["finding_count"] == 1
    finding = result["findings"][0]
    assert finding["id"] == "ambiguous_metric_basis_label"
    assert finding["measure"] == "Win Rate ARR"
    assert finding["basis"] == "arr_weighted_rate"


def test_metric_basis_rules_classify_load_bearing_measure_families():
    assert rule_for_measure("Total Closed Won ARR").basis == "land_expand_arr"
    assert rule_for_measure("Total Open Renewal ACV").basis == "renewal_acv"
    assert rule_for_measure("Existing ARR Run Rate").basis == "active_base_arr"
    assert rule_for_measure("Total Open Pipeline Value").basis == "cross_motion_arr_acv"
    assert rule_for_measure("Renewal Retention Pct (Period)").basis == "acv_weighted_rate"
    assert rule_for_measure("One Off Revenues").basis == "non_recurring_revenue"


def test_composed_rw_report_has_no_metric_basis_label_findings():
    result = audit_metric_basis(compose_report({"sections": []}))

    assert result["summary"]["finding_count"] == 0
    assert result["summary"]["severity_counts"]["medium"] == 0
    assert result["summary"]["severity_counts"]["high"] == 0
