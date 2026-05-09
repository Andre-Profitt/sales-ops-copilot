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
