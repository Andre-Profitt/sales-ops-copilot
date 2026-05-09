"""Tests for scripts.sales.rw_zebra_kg_datamodel — pure shaping layer."""

from __future__ import annotations

import pytest
from pathlib import Path

from scripts.sales import rw_zebra_kg_datamodel as kg
from tests.sales.fixtures.zebra_kg_datamodel_stub import make_stub_sales_funnel


def test_shape_returns_datamodel_with_expected_counts():
    pbix = make_stub_sales_funnel()
    dm = kg.shape_datamodel(pbix, template_slug="sales-funnel")

    assert dm.template_slug == "sales-funnel"
    assert {t.name for t in dm.tables} == {"f_opp", "d_stage"}
    assert {m.name for m in dm.measures} == {
        "Stage Forward Pct",
        "Forward Moves",
        "Total Transitions",
        "ARR PY",
    }
    assert len(dm.columns) == 4
    assert len(dm.relationships) == 1


def test_relationship_carries_cardinality_and_active():
    pbix = make_stub_sales_funnel()
    dm = kg.shape_datamodel(pbix, template_slug="sales-funnel")

    rel = dm.relationships[0]
    assert rel.from_table == "f_opp"
    assert rel.from_col == "StageId"
    assert rel.to_table == "d_stage"
    assert rel.to_col == "Id"
    assert rel.cardinality == "many_to_one"
    assert rel.cross_filter == "single"
    assert rel.active is True


def test_measure_carries_table_and_format():
    pbix = make_stub_sales_funnel()
    dm = kg.shape_datamodel(pbix, template_slug="sales-funnel")

    m = next(m for m in dm.measures if m.name == "Stage Forward Pct")
    assert m.table == "f_opp"
    assert m.format_string == "0.0%"
    assert m.expression.startswith("DIVIDE(")


ZEBRA_PBIX = Path(
    "/Users/test/Downloads/rw-zebra-bi-template-research-20260509/pbix-test/"
    "sales-funnel-power-bi-template__sales-pipeline-crm-template__"
    "Zebra BI - CRM Sales pipeline demo v2.pbix"
)


@pytest.mark.skipif(
    not ZEBRA_PBIX.exists(),
    reason="real Zebra PBIX corpus not present (download dump missing)",
)
def test_shape_real_pbix_smoke():
    """Sanity check pbixray + shape_datamodel against a real Zebra PBIX.

    pbixray returns pandas DataFrames; shape_datamodel wants list[dict].
    The _Adapter class converts at this boundary so the shaping layer
    stays pure-stdlib. Also, pbixray.tables is a pandas StringArray,
    not list[str], so we call list() on it.
    """
    from pbixray import PBIXRay  # local import keeps stub-only tests cheap

    raw = PBIXRay(str(ZEBRA_PBIX))

    class _Adapter:
        tables = list(raw.tables)
        dax_measures = raw.dax_measures.to_dict("records")
        relationships = raw.relationships.to_dict("records")
        schema = raw.schema.to_dict("records")

    dm = kg.shape_datamodel(_Adapter, template_slug="sales-funnel")

    assert len(dm.tables) > 0
    assert len(dm.measures) > 0
    assert all(m.table for m in dm.measures)
    assert all(
        r.cardinality
        in {
            "many_to_one",
            "one_to_many",
            "one_to_one",
            "many_to_many",
            "unknown",
        }
        for r in dm.relationships
    )


def test_classify_scenario_recognises_py_pl_fc_ac():
    classify = kg.classify_scenario
    assert classify("ARR PY") == "PY"
    assert classify("Sales Plan") == "PL"
    assert classify("Forecast FY") == "FC"
    assert classify("Stage Forward Pct") == "AC"
    assert classify("Total Transitions") == "AC"


def test_classify_variance_flags_var_diff_delta():
    is_var = kg.is_variance
    assert is_var("ARR vs PY") is True
    assert is_var("Var % vs Plan") is True
    assert is_var("Delta ARR") is True
    assert is_var("Total Transitions") is False


def test_node_ids_are_stable_and_namespaced():
    pbix = make_stub_sales_funnel()
    dm = kg.shape_datamodel(pbix, template_slug="sales-funnel")
    nodes = list(kg.iter_nodes(dm))
    ids = {n["id"] for n in nodes}

    assert "tbl:sales-funnel:f_opp" in ids
    assert "msr:sales-funnel:Stage Forward Pct" in ids
    assert "col:sales-funnel:f_opp:StageId" in ids
    assert "rel:sales-funnel:f_opp.StageId->d_stage.Id" in ids
    # Scenario nodes — emitted once per template, only for scenarios actually used
    assert "scn:PY" in ids


def test_edges_link_measure_to_dependent_measure():
    pbix = make_stub_sales_funnel()
    dm = kg.shape_datamodel(pbix, template_slug="sales-funnel")
    edges = list(kg.iter_edges(dm))

    # Stage Forward Pct DAX references [Forward Moves] and [Total Transitions]
    deps = {
        (e["src"], e["dst"])
        for e in edges
        if e["type"] == "depends_on" and e["src"] == "msr:sales-funnel:Stage Forward Pct"
    }
    assert (
        "msr:sales-funnel:Stage Forward Pct",
        "msr:sales-funnel:Forward Moves",
    ) in deps
    assert (
        "msr:sales-funnel:Stage Forward Pct",
        "msr:sales-funnel:Total Transitions",
    ) in deps


def test_edges_include_relationship_and_scenario_links():
    pbix = make_stub_sales_funnel()
    dm = kg.shape_datamodel(pbix, template_slug="sales-funnel")
    edges = list(kg.iter_edges(dm))
    edge_types = {e["type"] for e in edges}

    assert "related_to" in edge_types
    assert "scenario_of" in edge_types  # ARR PY measure → scn:PY


def test_measure_catalog_rows_have_dedupe_keys():
    pbix = make_stub_sales_funnel()
    dm = kg.shape_datamodel(pbix, template_slug="sales-funnel")
    rows = list(kg.measure_catalog_rows(dm))
    assert len(rows) == 4
    keys = {(r["template_slug"], r["table"], r["name"]) for r in rows}
    assert ("sales-funnel", "f_opp", "Stage Forward Pct") in keys
    assert all("expression" in r and "format_string" in r for r in rows)
