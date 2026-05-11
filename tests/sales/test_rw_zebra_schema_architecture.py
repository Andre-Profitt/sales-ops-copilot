"""Tests for Zebra schema architecture mining."""

from __future__ import annotations

from scripts.sales.rw_semantic_filter_audit import audit_semantic_filter_flow
from scripts.sales.rw_zebra_schema_architecture import (
    DEFAULT_SCHEMAS,
    build_zebra_schema_benchmark,
    classify_zebra_schema,
)


def test_sales_funnel_schema_exposes_kpi_scenario_and_ordering_patterns():
    result = classify_zebra_schema(DEFAULT_SCHEMAS / "sales-funnel-power-bi-template")

    assert result["long_fact_kpi_scenario"] is True
    assert result["scenario_columns"]["Data"] == ["Scenario"]
    assert result["ordered_dimension_columns"]["Products"] == ["Ranking"]
    assert result["kpi_tables"] == ["KPIs"]
    assert result["bidirectional_relationship_count"] == 0


def test_zebra_schema_benchmark_quantifies_architecture_guidance():
    benchmark = build_zebra_schema_benchmark()
    summary = benchmark["summary"]
    guidance = {row["pattern"]: row for row in benchmark["guidance"]}

    assert summary["template_count"] >= 20
    assert summary["total_relationships"] >= 100
    assert summary["single_direction_relationships"] > summary["bidirectional_relationships"]
    assert summary["templates_with_ordered_dimensions"] > 0
    assert summary["templates_with_role_playing_dims"] > 0
    assert "d_stage" in guidance["ordered_dimensions"]["rw_application"]
    assert "Motion" in guidance["scenario_as_axis"]["rw_application"]


def test_semantic_filter_audit_embeds_zebra_schema_benchmark():
    result = audit_semantic_filter_flow(report={"sections": []})
    zebra = result["zebra_schema_benchmark"]

    assert zebra["schema"] == "rw-zebra-schema-architecture.v1"
    assert zebra["summary"]["template_count"] >= 20
    assert {row["pattern"] for row in zebra["guidance"]} >= {
        "single_direction_star",
        "role_playing_dates",
        "ordered_dimensions",
        "scenario_as_axis",
        "kpi_dictionary",
    }
