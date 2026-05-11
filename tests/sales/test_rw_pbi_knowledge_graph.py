from __future__ import annotations

from pathlib import Path
import json

from scripts.sales import rw_pbi_knowledge_graph as kg
from scripts.sales._pbir_helpers import build_card_visual
from scripts.sales.rw_unit_policy import CURRENCY_M_FORMAT


def _model_bim() -> dict:
    return {
        "model": {
            "tables": [
                {
                    "name": "f_opportunity",
                    "columns": [
                        {"name": "opp_id", "dataType": "string"},
                        {"name": "arr_org_ccy", "dataType": "decimal"},
                    ],
                    "measures": [
                        {
                            "name": "Total Closed Won ARR",
                            "expression": "SUM ( f_opportunity[arr_org_ccy] )",
                            "formatString": CURRENCY_M_FORMAT,
                            "description": "ARR field, Land + Expand only.",
                        },
                        {
                            "name": "Total Open Pipeline ARR",
                            "expression": "[Total Closed Won ARR]",
                            "formatString": CURRENCY_M_FORMAT,
                        },
                    ],
                },
                {
                    "name": "d_region",
                    "columns": [{"name": "region", "dataType": "string"}],
                },
            ],
            "relationships": [
                {
                    "name": "rel_opp_region",
                    "fromTable": "f_opportunity",
                    "fromColumn": "region",
                    "toTable": "d_region",
                    "toColumn": "region",
                }
            ],
        }
    }


def _report() -> dict:
    return {
        "sections": [
            {
                "name": "page1",
                "displayName": "VP Ops Scorecard",
                "visualContainers": [
                    build_card_visual(
                        "f_opportunity",
                        "Total Closed Won ARR",
                        "Closed won ARR (Land + Expand)",
                        x=20,
                        y=20,
                        w=240,
                        h=120,
                    )
                ],
            }
        ]
    }


def test_pbi_knowledge_graph_connects_report_page_visual_measure_and_kpi():
    graph = kg.build_pbi_knowledge_graph(
        _report(),
        model_bim=_model_bim(),
        source="unit",
        include_audits=False,
    )

    edge_types = {(edge["source"], edge["target"], edge["type"]) for edge in graph["edges"]}
    page_id = kg.page_id("VP Ops Scorecard")
    measure_id = kg.measure_id("f_opportunity", "Total Closed Won ARR")
    column_id = kg.column_id("f_opportunity", "arr_org_ccy")

    assert (kg.REPORT_ID, page_id, "HAS_PAGE") in edge_types
    assert any(edge["source"] == page_id and edge["type"] == "HAS_VISUAL" for edge in graph["edges"])
    assert any(edge["target"] == measure_id and edge["type"] == "USES_MEASURE" for edge in graph["edges"])
    assert (measure_id, column_id, "DAX_USES_COLUMN") in edge_types
    assert (page_id, kg.kpi_id("forecast_closed_won"), "SERVES_KPI") in edge_types
    assert graph["summary"]["used_measure_count"] == 1
    assert graph["page_summaries"][0]["measures_used"] == ["f_opportunity.Total Closed Won ARR"]


def test_pbi_knowledge_graph_attaches_cleanup_findings_to_pages(monkeypatch):
    def fake_findings(_report: dict, _model_bim: dict):
        return (
            [
                {
                    "id": "finding:test",
                    "source": "unit",
                    "source_id": "test",
                    "severity": "high",
                    "page": "VP Ops Scorecard",
                    "pages": [],
                    "kpi_id": "",
                    "lane": "unit",
                    "message": "Test cleanup item.",
                    "next_action": "Fix the test issue.",
                    "visual_name": "",
                    "visual_type": "",
                    "measure": "",
                    "evidence": {},
                }
            ],
            {},
        )

    monkeypatch.setattr(kg, "collect_cleanup_findings", fake_findings)
    graph = kg.build_pbi_knowledge_graph(
        _report(),
        model_bim=_model_bim(),
        source="unit",
        include_audits=True,
    )

    assert graph["summary"]["cleanup_counts"]["high"] == 1
    assert graph["summary"]["verdict"] == "needs_source_or_model_work"
    assert any(
        edge["source"] == "finding:test"
        and edge["target"] == kg.page_id("VP Ops Scorecard")
        and edge["type"] == "FINDING_ON_PAGE"
        for edge in graph["edges"]
    )
    assert graph["page_summaries"][0]["cleanup_findings"][0]["message"] == "Test cleanup item."


def test_pbi_knowledge_graph_flags_custom_visual_and_uncontracted_tab():
    custom_visual = build_card_visual(
        "f_opportunity",
        "Total Closed Won ARR",
        "Closed won ARR (Land + Expand)",
        x=20,
        y=20,
        w=240,
        h=120,
    )
    cfg = json.loads(custom_visual["config"])
    cfg["singleVisual"]["visualType"] = "ZebraBITables98F88148E5424E949E69864664EE1860"
    custom_visual["config"] = json.dumps(cfg)
    report = {
        "sections": [
            {
                "name": "custom",
                "displayName": "Zebra Exceptions",
                "visualContainers": [custom_visual],
            }
        ]
    }

    graph = kg.build_pbi_knowledge_graph(
        report,
        model_bim=_model_bim(),
        source="unit",
        include_audits=False,
    )

    source_ids = {finding["source_id"] for finding in graph["cleanup_findings"]}
    assert source_ids == {"custom_visual", "uncontracted_page"}
    assert graph["summary"]["cleanup_counts"]["high"] == 1
    assert graph["summary"]["cleanup_counts"]["medium"] == 1
    assert graph["page_summaries"][0]["cleanup_counts"]["high"] == 1


def test_render_markdown_includes_tab_map_and_guardrails():
    graph = kg.build_pbi_knowledge_graph(
        _report(),
        model_bim=_model_bim(),
        source="unit",
        include_audits=False,
    )
    markdown = kg.render_markdown(graph, json_path=Path("output/test.json"))

    assert "# RW Power BI Knowledge Graph" in markdown
    assert "## Tab Map" in markdown
    assert "VP Ops Scorecard" in markdown
    assert "ARR means Land + Expand only" in markdown
    assert "`Total Open Pipeline Value` is the only cross-motion value measure" in markdown
