"""Tests for IBCS column synthesis primitives."""

from __future__ import annotations


from scripts.sales.rw_zebra_kg_ibcs_synth import (
    ColumnSpec,
    format_string_for,
    synthesize_dax,
)
from scripts.sales.rw_zebra_kg_translator import MeasureCatalog


def test_format_string_for_known_codes():
    assert format_string_for(0) == "#,##0"
    assert format_string_for(1) == "+#,##0;-#,##0"
    assert format_string_for(2) == "+0.0%;-0.0%"
    assert format_string_for(3) == "+#,##0.0;-#,##0.0"


def test_format_string_for_unknown_code_returns_default():
    assert format_string_for(99) == "#,##0"


def test_synthesize_dax_absolute_returns_existing_measure_ref():
    cat = MeasureCatalog(
        by_scenario={"AC": "ARR_AC"},
        measure_to_table={"ARR_AC": "Measures"},
    )
    spec = ColumnSpec(name="AC", role="absolute", base=("AC",), format_code=0)
    assert synthesize_dax(spec, cat) == "[ARR_AC]"


def test_synthesize_dax_delta_emits_subtraction():
    cat = MeasureCatalog(
        by_scenario={"AC": "ARR_AC", "PY": "ARR_PY"},
        measure_to_table={"ARR_AC": "Measures", "ARR_PY": "Measures"},
    )
    spec = ColumnSpec(name="AC-PY", role="delta", base=("AC", "PY"), format_code=1)
    assert synthesize_dax(spec, cat) == "[ARR_AC] - [ARR_PY]"


def test_synthesize_dax_relative_emits_divide_abs():
    cat = MeasureCatalog(
        by_scenario={"AC": "ARR_AC", "PY": "ARR_PY"},
        measure_to_table={"ARR_AC": "Measures", "ARR_PY": "Measures"},
    )
    spec = ColumnSpec(name="AC-PY %", role="relative", base=("AC", "PY"), format_code=2)
    assert synthesize_dax(spec, cat) == "DIVIDE([ARR_AC] - [ARR_PY], ABS([ARR_PY]))"


def test_synthesize_dax_cost_flips_sign():
    cat = MeasureCatalog(
        by_scenario={"AC": "Cost_AC", "PL": "Cost_PL"},
        measure_to_table={"Cost_AC": "Measures", "Cost_PL": "Measures"},
    )
    spec = ColumnSpec(name="AC-PL", role="delta", base=("AC", "PL"), format_code=1, is_cost=True)
    assert synthesize_dax(spec, cat) == "([Cost_AC] - [Cost_PL]) * -1"


def test_synthesize_dax_missing_scenario_returns_none():
    cat = MeasureCatalog(by_scenario={"AC": "ARR_AC"}, measure_to_table={"ARR_AC": "Measures"})
    spec = ColumnSpec(name="PY", role="absolute", base=("PY",), format_code=0)
    assert synthesize_dax(spec, cat) is None


from scripts.sales.rw_zebra_kg_ibcs_synth import synthesize_ibcs_columns


def test_synthesize_ibcs_columns_single_scenario():
    cols = synthesize_ibcs_columns({"AC"})
    assert [c.name for c in cols] == ["AC"]
    assert [c.role for c in cols] == ["absolute"]


def test_synthesize_ibcs_columns_ac_py_emits_delta_and_relative():
    cols = synthesize_ibcs_columns({"AC", "PY"})
    assert [c.name for c in cols] == ["AC", "PY", "AC-PY", "AC-PY %"]
    assert [c.role for c in cols] == ["absolute", "absolute", "delta", "relative"]
    assert [c.format_code for c in cols] == [0, 0, 1, 2]


def test_synthesize_ibcs_columns_ac_pl_pair():
    cols = synthesize_ibcs_columns({"AC", "PL"})
    assert [c.name for c in cols] == ["AC", "PL", "AC-PL", "AC-PL %"]


def test_synthesize_ibcs_columns_three_way_emits_pairs_in_canonical_order():
    cols = synthesize_ibcs_columns({"AC", "PY", "PL"})
    names = [c.name for c in cols]
    # AC absolutes first, then PY, then PL, then AC-PY pair, then AC-PL pair
    assert names == [
        "AC",
        "PY",
        "PL",
        "AC-PY",
        "AC-PY %",
        "AC-PL",
        "AC-PL %",
    ]


def test_synthesize_ibcs_columns_includes_fc_pair_last():
    cols = synthesize_ibcs_columns({"AC", "FC"})
    assert [c.name for c in cols] == ["AC", "FC", "AC-FC", "AC-FC %"]


def test_synthesize_ibcs_columns_unknown_scenario_dropped():
    cols = synthesize_ibcs_columns({"AC", "XYZ"})
    assert [c.name for c in cols] == ["AC"]


def test_synthesize_ibcs_columns_propagates_is_cost_flag():
    cols = synthesize_ibcs_columns({"AC", "PY"}, is_cost=True)
    assert all(c.is_cost is True for c in cols)


def test_synthesize_ibcs_columns_no_ac_returns_only_absolutes():
    """Variance pairs only synthesized when AC is present."""
    cols = synthesize_ibcs_columns({"PY", "PL"})
    assert [c.name for c in cols] == ["PY", "PL"]
    assert all(c.role == "absolute" for c in cols)


from scripts.sales.rw_zebra_kg_ibcs_synth import build_databar_cf_objects


def test_build_databar_cf_objects_returns_values_block():
    cf = build_databar_cf_objects(
        column_name="ARR",
        max_field="Measures.scaleGroup_max",
        positive_color="#1F77B4",
    )
    assert "values" in cf
    assert isinstance(cf["values"], list)
    assert len(cf["values"]) == 1


def test_build_databar_cf_objects_carries_column_selector():
    cf = build_databar_cf_objects(
        column_name="ARR",
        max_field="Measures.scaleGroup_max",
        positive_color="#1F77B4",
    )
    entry = cf["values"][0]
    selector = entry["selector"]["metadata"]
    assert selector == "ARR"


def test_build_databar_cf_objects_carries_positive_color():
    cf = build_databar_cf_objects(
        column_name="ARR",
        max_field="Measures.scaleGroup_max",
        positive_color="#1F77B4",
    )
    props = cf["values"][0]["properties"]
    assert props["axis"]["solid"]["color"]["expr"]["Literal"]["Value"] == "'#1F77B4'"


def test_build_databar_cf_objects_default_negative_color():
    cf = build_databar_cf_objects(
        column_name="ARR",
        max_field="Measures.scaleGroup_max",
        positive_color="#1F77B4",
    )
    props = cf["values"][0]["properties"]
    assert props["negativeBarColor"]["solid"]["color"]["expr"]["Literal"]["Value"] == "'#C00000'"


def test_build_databar_cf_objects_field_driven_max_present():
    cf = build_databar_cf_objects(
        column_name="ARR",
        max_field="Measures.scaleGroup_max",
        positive_color="#1F77B4",
    )
    props = cf["values"][0]["properties"]
    assert "maxValue" in props


from scripts.sales.rw_zebra_kg_ibcs_synth import build_composite_kpi_tile


def test_build_composite_kpi_tile_returns_3_vcs_when_variance_provided():
    vcs = build_composite_kpi_tile(
        label="Pipeline ARR",
        value_table="Measures",
        value_measure="Total Pipeline ARR",
        variance_table="Measures",
        variance_measure="Pipeline ARR vs PY",
        x=10,
        y=20,
        w=300,
        h=120,
    )
    assert len(vcs) == 3


def test_build_composite_kpi_tile_returns_2_vcs_when_no_variance():
    vcs = build_composite_kpi_tile(
        label="Pipeline ARR",
        value_table="Measures",
        value_measure="Total Pipeline ARR",
        variance_table=None,
        variance_measure=None,
        x=10,
        y=20,
        w=300,
        h=120,
    )
    assert len(vcs) == 2


def test_build_composite_kpi_tile_all_vcs_within_outer_bbox():
    vcs = build_composite_kpi_tile(
        label="Pipeline ARR",
        value_table="Measures",
        value_measure="Total Pipeline ARR",
        variance_table="Measures",
        variance_measure="Pipeline ARR vs PY",
        x=10,
        y=20,
        w=300,
        h=120,
    )
    for vc in vcs:
        assert vc["x"] >= 10
        assert vc["y"] >= 20
        assert vc["x"] + vc["width"] <= 10 + 300
        assert vc["y"] + vc["height"] <= 20 + 120


def test_build_composite_kpi_tile_overall_bbox_matches_w_h():
    vcs = build_composite_kpi_tile(
        label="Pipeline ARR",
        value_table="Measures",
        value_measure="Total Pipeline ARR",
        variance_table="Measures",
        variance_measure="Pipeline ARR vs PY",
        x=10,
        y=20,
        w=300,
        h=120,
    )
    max_right = max(vc["x"] + vc["width"] for vc in vcs)
    max_bottom = max(vc["y"] + vc["height"] for vc in vcs)
    assert max_right == 10 + 300
    assert max_bottom == 20 + 120
