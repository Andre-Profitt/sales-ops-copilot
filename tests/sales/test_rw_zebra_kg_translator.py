"""Tests for the rw_zebra_kg_translator dispatcher."""

from __future__ import annotations


from scripts.sales.rw_zebra_kg_translator import BindMap, MeasureCatalog


def test_measure_catalog_has_returns_true_for_known_measure():
    cat = MeasureCatalog(
        by_scenario={"AC": "Total Closed Won ARR", "PY": "Closed Won ARR PY"},
        measure_to_table={
            "Total Closed Won ARR": "Measures",
            "Closed Won ARR PY": "Measures",
        },
    )
    assert cat.has("AC") is True
    assert cat.has("FC") is False


def test_measure_catalog_resolve_returns_table_qualified_ref():
    cat = MeasureCatalog(
        by_scenario={"AC": "Total Closed Won ARR"},
        measure_to_table={"Total Closed Won ARR": "Measures"},
    )
    assert cat.resolve("AC") == ("Measures", "Total Closed Won ARR")


def test_measure_catalog_resolve_missing_scenario_returns_none():
    cat = MeasureCatalog(by_scenario={}, measure_to_table={})
    assert cat.resolve("AC") is None


def test_bindmap_lookup_returns_rw_field_for_zebra_field():
    bm = BindMap(zebra_to_rw={"PnL.AC": "Measures.Total Closed Won ARR"})
    assert bm.lookup("PnL.AC") == "Measures.Total Closed Won ARR"
    assert bm.lookup("Unknown.X") is None


import json

from scripts.sales.rw_zebra_kg_translator import translate_visual


def _make_src_vc(visual_type: str, x=0, y=0, w=300, h=200) -> dict:
    """Helper: build a Layout-shape visualContainer (config is a JSON string)."""
    return {
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "config": json.dumps(
            {
                "name": "abc123",
                "singleVisual": {"visualType": visual_type, "projections": {}},
            }
        ),
    }


def test_translate_visual_textbox_passes_through():
    src = _make_src_vc("textbox")
    out = translate_visual(src, MeasureCatalog(), BindMap())
    assert len(out) == 1
    assert out[0] is src


def test_translate_visual_basicShape_passes_through():
    src = _make_src_vc("basicShape")
    out = translate_visual(src, MeasureCatalog(), BindMap())
    assert out == [src]


def test_translate_visual_slicer_passes_through():
    src = _make_src_vc("slicer")
    out = translate_visual(src, MeasureCatalog(), BindMap())
    assert out == [src]


def test_translate_visual_unknown_visualtype_passes_through():
    src = _make_src_vc("someUnknownVisual")
    out = translate_visual(src, MeasureCatalog(), BindMap())
    assert out == [src]


def test_translate_visual_invalid_config_string_passes_through():
    src = {"x": 0, "y": 0, "width": 300, "height": 200, "config": "not-json{"}
    out = translate_visual(src, MeasureCatalog(), BindMap())
    assert out == [src]
