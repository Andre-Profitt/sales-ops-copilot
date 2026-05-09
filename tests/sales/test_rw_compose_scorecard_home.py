"""Tests for scripts.sales.rw_compose_scorecard_home — PR1.5 contract.

The page is composed of exactly 7 visualContainers:
- 1 page-title textbox
- 1 exception spine (native tableEx; PR1.5 fallback from Zebra BI Tables
  because SimCorp tenant policy blocks uncertified AppSource visuals)
- 1 movement-spine placeholder textbox
- 4 KPI strip cards
"""

import json

from scripts.sales.rw_compose_scorecard_home import (
    KPI_STRIP_MEASURES,
    PAGE,
    _build_exception_spine,
    _build_kpi_strip,
    _build_movement_spine_placeholder,
    _compose,
)


# ---------- top-level shape ----------


def test_compose_emits_seven_visualcontainers():
    section = {"visualContainers": []}
    _compose(section)
    assert len(section["visualContainers"]) == 7


def test_compose_visuals_within_canvas():
    section = {"visualContainers": []}
    _compose(section)
    for v in section["visualContainers"]:
        assert v["x"] + v["width"] <= 1280
        assert v["y"] + v["height"] <= 720


def test_layout_zones_sum_to_720px():
    """Title 64 + 16 gap + Exception 264 + 16 gap + Movement 224 + 16 gap + KPI 120 = 720."""
    section = {"visualContainers": []}
    _compose(section)
    visuals = section["visualContainers"]
    title = next(v for v in visuals if v["y"] == 0)
    assert title["height"] == 64
    spine = next(v for v in visuals if v["y"] == 80)
    assert spine["height"] == 264
    placeholder = next(v for v in visuals if v["y"] == 360)
    assert placeholder["height"] == 224
    kpi_cards = [v for v in visuals if v["y"] == 600]
    assert len(kpi_cards) == 4
    assert all(c["height"] == 120 for c in kpi_cards)


# ---------- exception spine ----------


def test_exception_spine_is_native_tableex_per_pr15_fallback():
    """PR1.5 swaps the spine from Zebra BI Tables to native tableEx because
    SimCorp tenant policy blocks uncertified AppSource visuals in the Service.
    Once Zebra is whitelisted, PR3 swaps back via the KG-driven recipe pipeline.
    """
    visual = _build_exception_spine()
    config = json.loads(visual["config"])
    sv = config["singleVisual"]
    assert sv["visualType"] == "tableEx"


def test_exception_spine_column_order_matches_lab_proof():
    """The column projection order must still match Codex's proven Zebra lab
    binding so a swap-back to Zebra Tables (when tenant unblocks) is a one-line
    change. Region first (category), then 4 measures in lab order.
    """
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
    assert visual["x"] == 0
    assert visual["y"] == 80
    assert visual["width"] == 1280
    assert visual["height"] == 264


# ---------- movement placeholder ----------


def test_movement_placeholder_is_textbox_not_zebra():
    visual = _build_movement_spine_placeholder()
    config = json.loads(visual["config"])
    sv = config["singleVisual"]
    assert sv["visualType"] == "textbox"
    assert visual["y"] == 360
    assert visual["height"] == 224


# ---------- KPI strip ----------


def test_kpi_strip_yields_four_cards():
    cards = _build_kpi_strip()
    assert len(cards) == 4


def test_kpi_strip_x_positions_are_evenly_spaced():
    cards = _build_kpi_strip()
    xs = sorted(c["x"] for c in cards)
    assert xs == [0, 320, 640, 960]
    assert all(c["width"] == 320 for c in cards)


def test_kpi_strip_uses_expected_measures():
    assert KPI_STRIP_MEASURES == [
        "Total Closed Won ARR",
        "Win Rate ARR",
        "Stage Forward Pct (LE)",
        "Renewal Retention Pct (Period)",
    ]


# ---------- contract: page name ----------


def test_page_constant_unchanged():
    assert PAGE == "VP Ops Scorecard"
