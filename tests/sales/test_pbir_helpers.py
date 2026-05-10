import json

from scripts.sales._pbir_helpers import (
    add_page,
    build_card_visual,
    build_card_visual_with_objects,
    build_clustered_bar_chart_visual,
    build_matrix_visual,
    build_matrix_style_objects,
    build_rag_card_objects,
    build_rag_card_visual,
    build_shape_visual,
    build_slicer_visual,
    build_table_style_objects,
    build_table_visual,
    build_textbox_visual,
    build_waterfall_chart_visual,
    build_zebra_bi_table_visual,
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


def test_build_rag_card_objects_has_status_treatment():
    objects = build_rag_card_objects(tint="#ffeeee", accent="#cc3333", display_units=1000000)

    assert objects["background"][0]["properties"]["color"]["solid"]["color"]["expr"][
        "Literal"
    ]["Value"] == "'#FFFFFF'"
    assert objects["border"][0]["properties"]["color"]["solid"]["color"]["expr"][
        "Literal"
    ]["Value"] == "'#D8DEE8'"
    assert objects["categoryLabels"][0]["properties"]["color"]["solid"]["color"]["expr"][
        "Literal"
    ]["Value"] == "'#cc3333'"
    assert objects["labels"][0]["properties"]["fontSize"]["expr"]["Literal"]["Value"] == "'28'"
    assert objects["labels"][0]["properties"]["labelDisplayUnits"]["expr"]["Literal"][
        "Value"
    ] == "1D"


def test_build_rag_card_visual_attaches_rag_objects():
    vc = build_rag_card_visual(
        "f_opportunity",
        "At Risk Opps Count",
        "At Risk - count",
        x=20,
        y=42,
        w=320,
        h=78,
        tint="#ffeeee",
        accent="#cc3333",
    )

    config = json.loads(vc["config"])
    objects = config["singleVisual"]["objects"]
    assert config["singleVisual"]["visualType"] == "card"
    assert {"background", "border", "labels", "categoryLabels"} <= set(objects)


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


def test_build_slicer_visual_has_compact_native_chrome():
    vc = build_slicer_visual(
        table="d_region",
        column="region",
        title="Region",
        x=790,
        y=10,
        w=142,
        h=48,
    )

    sv = json.loads(vc["config"])["singleVisual"]
    assert sv["visualType"] == "slicer"
    assert sv["projections"]["Values"][0]["queryRef"] == "d_region.region"
    assert {"general", "header", "items"} <= set(sv["objects"])
    assert {"title", "visualHeader", "border", "background"} <= set(sv["vcObjects"])
    assert sv["vcObjects"]["title"][0]["properties"]["show"]["expr"]["Literal"]["Value"] == "true"
    assert sv["vcObjects"]["border"][0]["properties"]["color"]["solid"]["color"]["expr"]["Literal"]["Value"] == "'#AAB4C4'"
    assert sv["objects"]["header"][0]["properties"]["background"]["solid"]["color"]["expr"]["Literal"]["Value"] == "'#EAF0F7'"


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


def test_build_clustered_bar_chart_visual_has_category_and_measure():
    vc = build_clustered_bar_chart_visual(
        category_table="f_opportunity",
        category_column="stage_name",
        category_title="Stage",
        measure_table="f_opportunity",
        measure_name="Total Open Pipeline Value",
        measure_title="Open Value",
        x=20,
        y=120,
        w=500,
        h=180,
    )

    config = json.loads(vc["config"])
    sv = config["singleVisual"]
    assert sv["visualType"] == "clusteredBarChart"
    assert sv["projections"]["Category"][0]["queryRef"] == "f_opportunity.stage_name"
    assert sv["projections"]["Y"][0]["queryRef"] == "f_opportunity.Total Open Pipeline Value"
    select = sv["prototypeQuery"]["Select"]
    assert "Column" in select[0] and select[0]["Column"]["Property"] == "stage_name"
    assert "Measure" in select[1] and select[1]["Measure"]["Property"] == (
        "Total Open Pipeline Value"
    )
    assert "objects" in sv
    assert sv["prototypeQuery"]["OrderBy"] == [
        {
            "Direction": 1,
            "Expression": {
                    "Column": {
                        "Expression": {"SourceRef": {"Source": "c"}},
                        "Property": "stage_order",
                    }
                },
            }
        ]
    assert sv["objects"]["labels"][0]["properties"]["labelDisplayUnits"]["expr"]["Literal"][
        "Value"
    ] == "1D"


def test_build_waterfall_chart_visual_uses_native_bridge_and_no_auto_units():
    vc = build_waterfall_chart_visual(
        category_table="d_region",
        category_column="region",
        category_title="Region",
        measure_table="f_opportunity",
        measure_name="Total Open Pipeline ARR",
        measure_title="Open ARR (Land + Expand)",
        x=20,
        y=44,
        w=500,
        h=240,
    )

    sv = json.loads(vc["config"])["singleVisual"]

    assert sv["visualType"] == "waterfallChart"
    assert set(sv["projections"]) == {"Category", "Y"}
    assert sv["objects"]["labels"][0]["properties"]["labelDisplayUnits"]["expr"]["Literal"][
        "Value"
    ] == "1D"
    assert sv["objects"]["valueAxis"][0]["properties"]["labelDisplayUnits"]["expr"]["Literal"][
        "Value"
    ] == "1D"


def test_build_zebra_bi_table_visual_has_categories_values_and_no_license():
    vc = build_zebra_bi_table_visual(
        categories=[
            {
                "table": "f_stage_transition",
                "field": "from_stage_name",
                "title": "Stage",
            }
        ],
        values=[
            {
                "table": "f_stage_transition",
                "field": "Stage Forward Pct (LE)",
                "title": "Forward %",
            },
            {
                "table": "f_stage_transition",
                "field": "Avg Days In Prior Stage (LE)",
                "title": "Avg days",
            },
        ],
        x=36,
        y=104,
        w=1208,
        h=560,
    )

    config = json.loads(vc["config"])
    sv = config["singleVisual"]
    assert sv["visualType"] == "ZebraBITables98F88148E5424E949E69864664EE1860"
    assert sv["projections"]["Category"][0]["queryRef"] == (
        "f_stage_transition.from_stage_name"
    )
    assert sv["projections"]["Values"][0]["queryRef"] == (
        "f_stage_transition.Stage Forward Pct (LE)"
    )
    assert sv["prototypeQuery"]["Select"][0]["Column"]["Property"] == "from_stage_name"
    assert sv["prototypeQuery"]["Select"][1]["Measure"]["Property"] == (
        "Stage Forward Pct (LE)"
    )
    assert "licenseSettings" not in sv["objects"]
    query = json.loads(vc["query"])
    binding = query["Commands"][0]["SemanticQueryDataShapeCommand"]["Binding"]
    assert binding["Primary"]["Groupings"][0]["Projections"] == [0, 1, 2]
    assert "Secondary" not in binding
    transforms = json.loads(vc["dataTransforms"])
    assert transforms["projectionOrdering"] == {"Category": [0], "Values": [1, 2]}
    assert transforms["queryMetadata"]["Select"][0]["Name"] == (
        "f_stage_transition.from_stage_name"
    )


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
    objects = build_table_style_objects()
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
        objects=objects,
    )
    config = json.loads(vc["config"])
    assert config["singleVisual"]["visualType"] == "tableEx"
    assert config["singleVisual"]["objects"] == objects
    assert len(config["singleVisual"]["prototypeQuery"]["Select"]) == 3
    sel = config["singleVisual"]["prototypeQuery"]["Select"]
    assert "Column" in sel[0] and sel[0]["Column"]["Property"] == "opp_name"
    assert "Measure" in sel[2] and sel[2]["Measure"]["Property"] == "Total Open Pipeline ARR"


def test_stage_tables_sort_by_numeric_stage_column_when_available():
    vc = build_table_visual(
        name="stage_table",
        columns=[
            {
                "table": "f_stage_transition",
                "field": "from_stage_name",
                "kind": "column",
                "title": "Stage",
            },
            {
                "table": "f_stage_transition",
                "field": "Stage Forward Pct (LE)",
                "kind": "measure",
                "title": "Forward %",
            },
        ],
        x=20,
        y=120,
    )

    sv = json.loads(vc["config"])["singleVisual"]
    assert sv["prototypeQuery"]["OrderBy"] == [
        {
            "Direction": 1,
            "Expression": {
                "Column": {
                    "Expression": {"SourceRef": {"Source": "a"}},
                    "Property": "from_stage_order",
                }
            },
        }
    ]


def test_stage_matrices_sort_by_opportunity_stage_order_key():
    vc = build_matrix_visual(
        rows=[{"table": "f_opportunity", "field": "stage_name", "title": "Stage"}],
        columns=[],
        values=[
            {"table": "f_opportunity", "field": "Total Open Pipeline ARR", "title": "Open ARR"},
        ],
        x=20,
        y=120,
    )

    sv = json.loads(vc["config"])["singleVisual"]
    assert sv["prototypeQuery"]["OrderBy"] == [
        {
            "Direction": 1,
            "Expression": {
                "Column": {
                    "Expression": {"SourceRef": {"Source": "a"}},
                    "Property": "stage_order",
                }
            },
        }
    ]


def test_build_textbox_visual_static_label():
    vc = build_textbox_visual(
        "RISK BAND - only what needs attention",
        x=20,
        y=12,
        w=1200,
        h=26,
    )
    assert vc["filters"] == "[]"
    config = json.loads(vc["config"])
    assert config["singleVisual"]["visualType"] == "textbox"
    run = config["singleVisual"]["objects"]["general"][0]["properties"]["paragraphs"][0][
        "textRuns"
    ][0]
    assert run["value"] == "RISK BAND - only what needs attention"
    assert run["textStyle"]["fontSize"] == "10pt"


def test_build_shape_visual_panel_shape():
    vc = build_shape_visual(x=16, y=38, w=328, h=146, fill="#ffeeee", line="#cc3333", z=100)

    assert vc["z"] == 100
    config = json.loads(vc["config"])
    assert config["singleVisual"]["visualType"] == "basicShape"
    objects = config["singleVisual"]["objects"]
    assert objects["general"][0]["properties"]["shapeType"]["expr"]["Literal"][
        "Value"
    ] == "'rectangle'"
    assert objects["fill"][0]["properties"]["fillColor"]["solid"]["color"]["expr"][
        "Literal"
    ]["Value"] == "'#ffeeee'"


def test_build_matrix_style_objects_has_table_chrome():
    objects = build_matrix_style_objects()

    assert {"grid", "columnHeaders", "rowHeaders", "values"} <= set(objects)
    assert objects["columnHeaders"][0]["properties"]["backColor"]["solid"]["color"]["expr"][
        "Literal"
    ]["Value"] == "'#f0f0f0'"
