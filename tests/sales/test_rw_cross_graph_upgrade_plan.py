from __future__ import annotations

from scripts.sales.rw_cross_graph_upgrade_plan import build_upgrade_plan, render_markdown


def _pbi_graph() -> dict:
    return {
        "summary": {
            "verdict": "needs_source_or_model_work",
            "page_count": 2,
            "visual_count": 12,
            "visual_type_counts": {
                "card": 6,
                "tableEx": 2,
                "pivotTable": 1,
                "waterfallChart": 0,
            },
            "cleanup_counts": {"info": 0, "low": 0, "medium": 1, "high": 2, "critical": 0},
        },
        "page_summaries": [
            {
                "page": "Forecast",
                "visual_type_counts": {"card": 7, "pivotTable": 1},
                "kpis_served": ["pipeline_coverage_3x", "forecast_accuracy"],
            },
            {
                "page": "Growth Mix",
                "visual_type_counts": {"card": 5, "tableEx": 2},
                "kpis_served": ["synergy_deals_won"],
            },
        ],
        "cleanup_findings": [
            {
                "page": "Forecast",
                "severity": "high",
                "source": "data_surface",
                "message": "Pipeline coverage is partial.",
            }
        ],
    }


def _zebra_infra() -> dict:
    return {
        "total_zebra_visuals": 360,
        "by_family": {
            "ZebraBITables": 146,
            "ZebraWaterfall": 140,
            "ZebraBICards": 74,
        },
    }


def _zebra_transfer() -> dict:
    return {
        "learned_rules": {
            "variance_table": "Zebra Tables -> native tableEx with IBCS order.",
            "waterfall_bridge": "Zebra Waterfall -> native waterfallChart.",
            "kpi_tile": "Zebra Cards -> composite KPI tile.",
            "static_furniture": "Static page furniture is preserved.",
        }
    }


def _flow_rows() -> list[dict]:
    return [
        {"kpi_id": "pipeline_coverage_3x", "dashboard_status": "surfaced_partial"},
        {"kpi_id": "forecast_accuracy", "dashboard_status": "surfaced_partial"},
        {"kpi_id": "synergy_deals_won", "dashboard_status": "surfaced_partial"},
        {"kpi_id": "synergy_deals_pipe", "dashboard_status": "partial_data_or_measure_gap"},
        {"kpi_id": "indexation_arr_growth", "dashboard_status": "surfaced_partial"},
    ]


def test_cross_graph_plan_prioritizes_forecast_and_growth_blockers():
    plan = build_upgrade_plan(
        pbi_graph=_pbi_graph(),
        zebra_infra=_zebra_infra(),
        zebra_transfer=_zebra_transfer(),
        flow_rows=_flow_rows(),
    )

    ids = [item["id"] for item in plan["opportunities"]]
    assert ids[:2] == ["forecast_scenario_spine", "growth_mix_trusted_segmentation"]
    assert plan["summary"]["p0_count"] == 2
    assert any(item["signal"] == "bridge_gap" for item in plan["visual_mix_insights"])
    assert any(item["pattern"] == "waterfall_bridge" for item in plan["zebra_schema_signals"])
    assert "product_segment_retention_churn" in ids


def test_cross_graph_plan_markdown_preserves_guardrails():
    plan = build_upgrade_plan(
        pbi_graph=_pbi_graph(),
        zebra_infra=_zebra_infra(),
        zebra_transfer=_zebra_transfer(),
        flow_rows=_flow_rows(),
    )
    markdown = render_markdown(plan)

    assert "Forecast — `forecast_scenario_spine`" in markdown
    assert "Growth Mix — `growth_mix_trusted_segmentation`" in markdown
    assert "Product Mix — `product_segment_retention_churn`" in markdown
    assert "Product heatmap and churn view both exist" in markdown
    assert "ARR is Land + Expand only" in markdown
    assert "Renewal ACV is Renewal only" in markdown
    assert "Do not count proxy KPIs as finished executive metrics" in markdown
