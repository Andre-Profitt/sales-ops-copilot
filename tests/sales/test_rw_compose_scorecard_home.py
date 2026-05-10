"""Tests for scripts.sales.rw_compose_scorecard_home.

The page is native Zebra/IBCS: KPI pulse, exception spine, stage distribution,
stage hygiene, and 7-day movement pulse. It deliberately avoids Zebra custom
visual types so SimCorp tenant policy cannot block the front page.
"""

import json

import pytest

from scripts.sales.rw_compose_scorecard_home import (
    KPI_STRIP_MEASURES,
    MOVEMENT_PULSE_MEASURES,
    PAGE,
    _build_exception_spine,
    _build_kpi_strip,
    _build_movement_pulse,
    _build_stage_distribution_panel,
    _build_stage_hygiene_panel,
    _compose,
)


def _visual_type(vc: dict) -> str:
    return json.loads(vc["config"])["singleVisual"]["visualType"]


@pytest.fixture(autouse=True)
def _stub_fetch_measures_by_table(monkeypatch):
    """Autouse: stub fetch_measures_by_table so composer tests don't hit live
    Fabric REST. The 4 spine measures + the 4 KPI strip measures must be
    present so _build_exception_spine + _build_kpi_strip don't drop visuals.

    Tests that need a different stub (e.g. zero-measure case) override via
    their own monkeypatch.setattr — pytest applies the test-local patch
    after this fixture's setattr, so the test-local one wins.
    """
    from scripts.sales import rw_compose_scorecard_home as composer

    monkeypatch.setattr(
        composer,
        "fetch_measures_by_table",
        lambda: {
            "f_opportunity": [
                "Exception ARR",
                "Exception Opps Count",
                "At Risk Opps ARR",
                "Watch Opps ARR",
                "Total Closed Won ARR",
                "Win Rate ARR",
                "Renewal Retention Pct (Period)",
                "New Opps Count 7d",
                "Closed Won Count 7d",
                "Total Open Pipeline ARR",
            ],
            "f_stage_transition": [
                "Stage Forward Pct (LE)",
                "Stage Backward Pct (LE)",
                "Avg Days In Prior Stage (LE)",
                "Stage Moves ARR 7d",
                "Backward Moves Count 7d",
            ],
        },
    )


# ---------- top-level shape ----------


def test_compose_emits_native_zebra_layout_visualcontainers():
    section = {"visualContainers": []}
    _compose(section)
    assert len(section["visualContainers"]) == 25


def test_compose_visuals_within_canvas():
    section = {"visualContainers": []}
    _compose(section)
    for v in section["visualContainers"]:
        assert v["x"] + v["width"] <= 1280
        assert v["y"] + v["height"] <= 720


def test_layout_zones_stay_in_defined_bands():
    section = {"visualContainers": []}
    _compose(section)
    visuals = section["visualContainers"]
    assert any(_visual_type(v) == "textbox" and v["x"] == 28 and v["y"] == 12 for v in visuals)
    assert any(_visual_type(v) == "textbox" and v["x"] == 28 and v["y"] == 42 for v in visuals)
    kpi_cards = [v for v in visuals if _visual_type(v) == "card" and v["y"] == 88]
    assert len(kpi_cards) == 4
    assert all(c["height"] == 116 for c in kpi_cards)
    kpi_shapes = [v for v in visuals if _visual_type(v) == "basicShape" and v["y"] == 88]
    assert len(kpi_shapes) == 4
    assert any(v["x"] == 24 and v["y"] == 226 and v["height"] == 260 for v in visuals)
    assert any(v["x"] == 24 and v["y"] == 508 and v["height"] == 188 for v in visuals)


# ---------- exception spine ----------


def test_exception_spine_is_native_tableex():
    visual = _build_exception_spine()
    config = json.loads(visual["config"])
    sv = config["singleVisual"]
    assert sv["visualType"] == "tableEx"
    assert "objects" in sv


def test_exception_spine_column_order_matches_lab_proof():
    """Region first, then the proven Zebra exception measure order."""
    visual = _build_exception_spine()
    config = json.loads(visual["config"])
    sv = config["singleVisual"]
    projections = sv["projections"]["Values"]
    field_names = [p["queryRef"].split(".")[-1] for p in projections]
    assert field_names == [
        "region",
        "Exception ARR",
        "Exception Opps Count",
        "At Risk Opps ARR",
        "Watch Opps ARR",
    ]


def test_exception_spine_position():
    visual = _build_exception_spine()
    assert visual["x"] == 40
    assert visual["y"] == 258
    assert visual["width"] == 736
    assert visual["height"] == 210


# ---------- no placeholder ----------


def test_compose_has_no_pr2_placeholder_text():
    section = {"visualContainers": []}
    _compose(section)
    text = "\n".join(v.get("config", "") for v in section["visualContainers"])
    assert "see PR2" not in text
    assert "Movement spine" not in text


# ---------- KPI strip ----------


def test_kpi_strip_yields_four_cards():
    visuals = _build_kpi_strip()
    cards = [v for v in visuals if _visual_type(v) == "card"]
    shapes = [v for v in visuals if _visual_type(v) == "basicShape"]
    assert len(visuals) == 8
    assert len(cards) == 4
    assert len(shapes) == 4


def test_kpi_strip_x_positions_are_evenly_spaced():
    cards = [v for v in _build_kpi_strip() if _visual_type(v) == "card"]
    xs = sorted(c["x"] for c in cards)
    assert xs == [24, 335.0, 646.0, 957.0]
    assert all(c["width"] == 299 for c in cards)


def test_kpi_strip_uses_expected_measures():
    assert KPI_STRIP_MEASURES == [
        "Total Closed Won ARR",
        "Win Rate ARR",
        "Exception ARR",
        "Renewal Retention Pct (Period)",
    ]


def test_stage_distribution_panel_uses_native_bar_chart():
    visuals = _build_stage_distribution_panel()
    chart = visuals[-1]
    config = json.loads(chart["config"])
    sv = config["singleVisual"]
    assert sv["visualType"] == "clusteredBarChart"
    assert sv["projections"]["Category"][0]["queryRef"] == "f_opportunity.stage_name"
    assert sv["projections"]["Y"][0]["queryRef"] == "f_opportunity.Total Open Pipeline ARR"


def test_stage_hygiene_panel_uses_native_matrix():
    visuals = _build_stage_hygiene_panel()
    matrix = visuals[-1]
    config = json.loads(matrix["config"])
    sv = config["singleVisual"]
    assert sv["visualType"] == "pivotTable"
    assert sv["projections"]["Rows"][0]["queryRef"] == "f_stage_transition.from_stage_name"
    field_names = [p["queryRef"].split(".")[-1] for p in sv["projections"]["Values"]]
    assert field_names == [
        "Stage Forward Pct (LE)",
        "Stage Backward Pct (LE)",
        "Avg Days In Prior Stage (LE)",
        "Stage Moves ARR 7d",
    ]


def test_movement_pulse_measures_are_existing_contract():
    assert MOVEMENT_PULSE_MEASURES == [
        "New Opps Count 7d",
        "Closed Won Count 7d",
        "Stage Moves ARR 7d",
        "Backward Moves Count 7d",
    ]
    cards = [v for v in _build_movement_pulse() if _visual_type(v) == "card"]
    assert len(cards) == 4


# ---------- contract: page name ----------


def test_page_constant_unchanged():
    assert PAGE == "VP Ops Scorecard"


def test_front_page_contains_no_custom_visual_types():
    section = {"visualContainers": []}
    _compose(section)
    custom = []
    allowed = {"basicShape", "textbox", "card", "tableEx", "clusteredBarChart", "pivotTable"}
    for vc in section["visualContainers"]:
        sv = json.loads(vc["config"])["singleVisual"]
        vt = sv["visualType"]
        if vt not in allowed:
            custom.append(vt)
    assert custom == []
