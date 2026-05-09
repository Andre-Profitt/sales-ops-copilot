import json

from scripts.sales.rw_compose_scorecard_home import FRONT_PAGE_KPI_ROUTES, _compose
from scripts.sales.rw_kpi_graph import find_kpi


def test_front_page_compose_is_structured_and_within_canvas():
    section = {"visualContainers": []}
    _compose(section)

    visuals = section["visualContainers"]
    assert len(visuals) == 45
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

    assert types.count("card") == 10
    assert object_bearing_cards == 10
    assert types.count("basicShape") == 15
    assert types.count("textbox") == 14
    assert types.count("slicer") == 3
    assert types.count("clusteredBarChart") == 2
    assert "tableEx" in types

    for visual in visuals:
        config = json.loads(visual["config"])
        sv = config["singleVisual"]
        if sv["visualType"] in {"clusteredBarChart", "tableEx"}:
            assert "objects" in sv

        if sv["visualType"] == "textbox":
            assert visual["height"] >= 34

        if sv["visualType"] == "card":
            assert visual["height"] >= 76
            labels = sv["objects"]["labels"]
            units = labels[0]["properties"].get("labelDisplayUnits")
            assert units is not None
            assert units["expr"]["Literal"]["Value"] == "1.0D"
            category = sv["objects"]["categoryLabels"][0]["properties"]["show"]
            assert category["expr"]["Literal"]["Value"] == "true"


def test_front_page_kpi_routes_resolve_against_graph():
    for route, kpi_ids in FRONT_PAGE_KPI_ROUTES.items():
        assert kpi_ids, route
        for kpi_id in kpi_ids:
            assert find_kpi(kpi_id) is not None, f"{route}: {kpi_id}"
