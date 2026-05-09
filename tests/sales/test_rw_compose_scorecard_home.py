import json

from scripts.sales.rw_compose_scorecard_home import _compose


def test_front_page_compose_is_structured_and_within_canvas():
    section = {"visualContainers": []}
    _compose(section)

    visuals = section["visualContainers"]
    assert len(visuals) == 52
    assert all(v["x"] + v["width"] <= 1280 for v in visuals)
    assert all(v["y"] + v["height"] <= 720 for v in visuals)

    types = []
    object_bearing_cards = 0
    for visual in visuals:
        config = json.loads(visual["config"])
        sv = config["singleVisual"]
        types.append(sv["visualType"])
        if sv["visualType"] == "card" and "objects" in sv:
            object_bearing_cards += 1

    assert types.count("card") == 12
    assert object_bearing_cards == 12
    assert types.count("basicShape") == 16
    assert types.count("textbox") == 19
    assert types.count("slicer") == 3
    assert "pivotTable" in types
    assert "tableEx" in types
