"""Tests for the rw_zebra_kg_translator dispatcher."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.sales.rw_zebra_kg_translator import BindMap, MeasureCatalog, translate_visual


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


FIXTURES = Path(__file__).parent / "fixtures" / "zebra_translator"


def _layout_vc_from_raw(raw_row: dict) -> dict:
    """Convert an infra-miner raw_configs.jsonl row into a Layout-shape vc.

    The miner stores singleVisual.objects + projections+visualType separately,
    not as an embedded config string. Re-pack them so the translator can parse.
    """
    pos = raw_row["position"]
    return {
        "x": pos["x"],
        "y": pos["y"],
        "width": pos["w"],
        "height": pos["h"],
        "config": json.dumps(
            {
                "name": "raw",
                "singleVisual": {
                    "visualType": raw_row["visual_type_full"],
                    "projections": {
                        role: [{"queryRef": q} for q in qs]
                        for role, qs in raw_row.get("projections", {}).items()
                    },
                    "objects": raw_row.get("objects", {}),
                },
            }
        ),
    }


def _catalog_for_refs(raw_row: dict) -> MeasureCatalog:
    """Build a catalog that resolves every queryRef in the raw row's projections.

    Each measure stays in its native table and is keyed by the field-name
    (which is what BindMap will lookup against).
    """
    by_scenario = {}
    measure_to_table = {}
    for refs in raw_row.get("projections", {}).values():
        for ref in refs:
            if "." not in ref:
                continue
            tbl, fld = ref.split(".", 1)
            by_scenario[fld] = fld
            measure_to_table[fld] = tbl
    return MeasureCatalog(by_scenario=by_scenario, measure_to_table=measure_to_table)


def _bindmap_for_refs(raw_row: dict) -> BindMap:
    return BindMap(
        zebra_to_rw={
            ref: ref
            for refs in raw_row.get("projections", {}).values()
            for ref in refs
            if "." in ref
        }
    )


def test_translate_visual_table_emits_native_tableEx():
    raw = json.loads((FIXTURES / "sample_table.json").read_text())
    src = _layout_vc_from_raw(raw)
    out = translate_visual(src, _catalog_for_refs(raw), _bindmap_for_refs(raw))
    assert len(out) == 1
    cfg = json.loads(out[0]["config"])
    assert cfg["singleVisual"]["visualType"] == "tableEx"


def test_translate_visual_table_preserves_position():
    raw = json.loads((FIXTURES / "sample_table.json").read_text())
    src = _layout_vc_from_raw(raw)
    out = translate_visual(src, _catalog_for_refs(raw), _bindmap_for_refs(raw))
    assert out[0]["x"] == src["x"]
    assert out[0]["y"] == src["y"]
    assert out[0]["width"] == src["width"]
    assert out[0]["height"] == src["height"]


def test_translate_visual_table_applies_zebra_databar_object():
    raw = json.loads((FIXTURES / "sample_table.json").read_text())
    src = _layout_vc_from_raw(raw)
    out = translate_visual(src, _catalog_for_refs(raw), _bindmap_for_refs(raw))
    cfg = json.loads(out[0]["config"])
    objects = cfg["singleVisual"].get("objects", {})
    assert "dataBars" in objects
    assert objects["dataBars"]["values"][0]["selector"]["metadata"] == "AC"


def test_translate_visual_table_keeps_ibcs_scenario_order():
    raw = json.loads((FIXTURES / "sample_table.json").read_text())
    src = _layout_vc_from_raw(raw)
    out = translate_visual(src, _catalog_for_refs(raw), _bindmap_for_refs(raw))
    cfg = json.loads(out[0]["config"])
    refs = [p["queryRef"] for p in cfg["singleVisual"]["projections"]["Values"]]
    assert refs[:3] == ["AccountHierarchy.Account", "∑ Key Measures.AC", "∑ Key Measures.PY"]


def test_translate_visual_card_with_group_emits_composite_tile():
    raw = json.loads((FIXTURES / "sample_card.json").read_text())
    src = _layout_vc_from_raw(raw)
    out = translate_visual(src, _catalog_for_refs(raw), _bindmap_for_refs(raw))
    visual_types = [json.loads(vc["config"])["singleVisual"]["visualType"] for vc in out]
    assert visual_types == ["textbox", "card", "card"]


def test_translate_visual_card_emits_native_card():
    raw = json.loads((FIXTURES / "sample_card.json").read_text())
    src = _layout_vc_from_raw(raw)
    out = translate_visual(src, _catalog_for_refs(raw), _bindmap_for_refs(raw))
    assert len(out) >= 1
    visual_types = {json.loads(vc["config"])["singleVisual"]["visualType"] for vc in out}
    assert visual_types & {"card", "multiRowCard"}


@pytest.mark.skipif(
    not (FIXTURES / "sample_waterfall.json").exists(),
    reason="ZebraWaterfall fixture not available in corpus",
)
def test_translate_visual_waterfall_emits_native_waterfallChart():
    raw = json.loads((FIXTURES / "sample_waterfall.json").read_text())
    src = _layout_vc_from_raw(raw)
    out = translate_visual(src, _catalog_for_refs(raw), _bindmap_for_refs(raw))
    cfg = json.loads(out[0]["config"])
    assert cfg["singleVisual"]["visualType"] == "waterfallChart"


def test_translate_visual_corpus_smoke_no_exceptions():
    """Every row in the 360-VC corpus translates without raising."""
    src = Path("data/zebra_kg/infrastructure/raw_configs.jsonl")
    if not src.exists():
        pytest.skip("infrastructure corpus not present")
    cat = MeasureCatalog()  # empty -> translator falls back gracefully
    bm = BindMap()
    count = 0
    with src.open() as f:
        for line in f:
            raw = json.loads(line)
            vc = _layout_vc_from_raw(raw)
            out = translate_visual(vc, cat, bm)
            assert isinstance(out, list)
            assert len(out) >= 1
            count += 1
    assert count > 0


def test_native_emit_emit_native_visuals_calls_translate_visual():
    """The refactor wires emit_native_visuals through translate_visual."""
    from scripts.sales.rw_zebra_kg_native_emit import emit_native_visuals
    from scripts.sales.rw_zebra_kg_recipe import Recipe, VisualRecipe

    recipe = Recipe(
        source_template="t",
        source_page="p",
        visuals=[
            VisualRecipe(
                visual_type="textbox",
                position={"x": 0, "y": 0, "w": 100, "h": 50},
                role_bindings={},
                scenarios_used=[],
                tables_referenced=[],
                measure_refs=[],
                text="hello",
            )
        ],
    )
    with patch(
        "scripts.sales.rw_zebra_kg_native_emit.translate_visual",
        wraps=__import__(
            "scripts.sales.rw_zebra_kg_translator", fromlist=["translate_visual"]
        ).translate_visual,
    ) as spy:
        emit_native_visuals(recipe, rw_map={})
        assert spy.call_count == 1


def test_swap_pbix_swap_layout_calls_translate_visual():
    """The refactor wires swap_layout through translate_visual."""
    from scripts.sales.rw_zebra_kg_swap_pbix import swap_layout

    layout = {
        "sections": [
            {
                "name": "p1",
                "displayName": "Page 1",
                "visualContainers": [
                    {
                        "x": 0,
                        "y": 0,
                        "width": 200,
                        "height": 100,
                        "config": json.dumps(
                            {
                                "name": "v1",
                                "singleVisual": {
                                    "visualType": "textbox",
                                    "projections": {},
                                },
                            }
                        ),
                    }
                ],
            }
        ]
    }
    rmap = {"measures_by_table": {}, "calendar_alias": "Calendar"}
    with patch(
        "scripts.sales.rw_zebra_kg_swap_pbix.translate_visual",
        wraps=__import__(
            "scripts.sales.rw_zebra_kg_translator", fromlist=["translate_visual"]
        ).translate_visual,
    ) as spy:
        swap_layout(layout, rmap)
        assert spy.call_count == 1
