import json

from scripts.sales._pbir_helpers import build_card_visual


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
