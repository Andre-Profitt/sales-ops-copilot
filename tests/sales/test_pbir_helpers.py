import json

from scripts.sales._pbir_helpers import build_card_visual, build_table_visual


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
