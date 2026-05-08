import json

from scripts.sales._pbir_helpers import (
    add_page,
    build_card_visual,
    build_card_visual_with_objects,
    build_matrix_visual,
    build_table_visual,
    ensure_pages,
    remove_page,
)


def test_build_card_visual_with_objects_attaches_objects_block():
    rag = {
        "general": [
            {
                "properties": {
                    "orientation": {"expr": {"Literal": {"Value": "1D"}}},
                }
            }
        ]
    }
    vc = build_card_visual_with_objects(
        measure_table="f_opportunity",
        measure_name="Win Rate ARR",
        display_title="Win Rate",
        x=0,
        y=0,
        objects=rag,
    )
    config = json.loads(vc["config"])
    assert config["singleVisual"]["visualType"] == "card"
    assert config["singleVisual"]["objects"] == rag


def test_build_card_visual_with_objects_no_block_falls_through():
    """When objects is None, output should match plain build_card_visual."""
    vc = build_card_visual_with_objects(
        measure_table="f_opportunity",
        measure_name="Win Rate ARR",
        display_title="Win Rate",
        x=0,
        y=0,
        objects=None,
    )
    config = json.loads(vc["config"])
    assert "objects" not in config["singleVisual"]


def test_add_page_appends_section(empty_report):
    add_page(empty_report, name="ReportSection2", display_name="Forecast")
    names = [s["name"] for s in empty_report["sections"]]
    assert "ReportSection2" in names
    new = [s for s in empty_report["sections"] if s["name"] == "ReportSection2"][0]
    assert new["displayName"] == "Forecast"
    assert new["visualContainers"] == []


def test_remove_page_drops_section(empty_report):
    add_page(empty_report, name="X", display_name="X")
    remove_page(empty_report, name="X")
    assert all(s["name"] != "X" for s in empty_report["sections"])


def test_ensure_pages_idempotent(empty_report):
    targets = [
        ("PageWhatChanged", "What Changed"),
        ("PageForecast", "Forecast"),
        ("PageStageHygiene", "Stage Hygiene"),
        ("PageRenewals", "Renewals"),
        ("PageGrowthMix", "Growth Mix"),
    ]
    ensure_pages(empty_report, targets)
    ensure_pages(empty_report, targets)
    names = [s["name"] for s in empty_report["sections"]]
    for n, _ in targets:
        assert n in names
    assert len(names) == len(set(names))


def test_build_matrix_visual_axes():
    vc = build_matrix_visual(
        rows=[{"table": "f_opportunity", "field": "stage_name", "title": "Stage"}],
        columns=[{"table": "f_opportunity", "field": "motion_type", "title": "Motion"}],
        values=[
            {"table": "f_opportunity", "field": "Total Open Pipeline ARR", "title": "Open ARR"},
            {"table": "f_opportunity", "field": "Total Closed Won ARR", "title": "Won ARR"},
        ],
        x=20,
        y=120,
        w=900,
        h=260,
    )
    config = json.loads(vc["config"])
    assert config["singleVisual"]["visualType"] == "pivotTable"
    proj = config["singleVisual"]["projections"]
    assert "Rows" in proj and "Columns" in proj and "Values" in proj
    assert len(proj["Values"]) == 2


def test_build_card_visual_basic_shape():
    vc = build_card_visual(
        measure_table="f_opportunity",
        measure_name="Total Closed Won ARR",
        display_title="Closed Won ARR",
        x=20,
        y=20,
        w=280,
        h=110,
    )
    assert vc["x"] == 20 and vc["y"] == 20
    assert vc["width"] == 280 and vc["height"] == 110
    config = json.loads(vc["config"])
    assert config["singleVisual"]["visualType"] == "card"
    select = config["singleVisual"]["prototypeQuery"]["Select"][0]
    assert select["Measure"]["Property"] == "Total Closed Won ARR"


def test_build_table_visual_columns():
    vc = build_table_visual(
        name="commit_risk_table",
        columns=[
            {"table": "f_opportunity", "field": "opp_name", "kind": "column", "title": "Opp"},
            {"table": "f_opportunity", "field": "account_name", "kind": "column", "title": "Acct"},
            {
                "table": "f_opportunity",
                "field": "Total Open Pipeline ARR",
                "kind": "measure",
                "title": "ARR",
            },
        ],
        x=20,
        y=400,
        w=900,
        h=240,
    )
    config = json.loads(vc["config"])
    assert config["singleVisual"]["visualType"] == "tableEx"
    assert len(config["singleVisual"]["prototypeQuery"]["Select"]) == 3
    sel = config["singleVisual"]["prototypeQuery"]["Select"]
    assert "Column" in sel[0] and sel[0]["Column"]["Property"] == "opp_name"
    assert "Measure" in sel[2] and sel[2]["Measure"]["Property"] == "Total Open Pipeline ARR"
