"""Tests for scripts.sales.rw_zebra_kg_topology_atlas."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.sales import rw_zebra_kg_topology_atlas as topo

KG = Path(__file__).resolve().parents[2] / "data/zebra_kg"


def _node(template: str, name: str) -> dict:
    return {"id": f"tbl:{template}:{name}", "type": "Table", "name": name, "template": template}


def _rel(
    template: str,
    ft: str,
    fc: str,
    tt: str,
    tc: str,
    cardinality: str = "many_to_one",
    cross_filter: str = "single",
    active: bool = True,
) -> dict:
    return {
        "src": f"tbl:{template}:{ft}",
        "dst": f"tbl:{template}:{tt}",
        "type": "related_to",
        "props": {
            "from_col": fc,
            "to_col": tc,
            "cardinality": cardinality,
            "cross_filter": cross_filter,
            "active": active,
        },
    }


# ---------- pure unit tests ----------


def test_classify_template_topology_basic_star():
    """f_sales fact joined to d_calendar + d_region dims = simple star."""
    nodes = [
        _node("t1", "f_sales"),
        _node("t1", "d_calendar"),
        _node("t1", "d_region"),
    ]
    edges = [
        _rel("t1", "f_sales", "DateKey", "d_calendar", "Date"),
        _rel("t1", "f_sales", "RegionKey", "d_region", "Id"),
    ]
    result = topo.classify_template_topology("t1", nodes, edges)
    assert result["fact_tables"] == ["f_sales"]
    assert result["dim_tables"] == ["d_calendar", "d_region"]
    assert result["relationship_count"] == 2
    assert result["bidirectional_count"] == 0
    assert result["inactive_count"] == 0
    assert result["has_calendar_dim"] is True


def test_classify_picks_up_bidirectional_and_inactive():
    nodes = [_node("t1", "f"), _node("t1", "d")]
    edges = [
        _rel("t1", "f", "K1", "d", "Id", cross_filter="both"),
        _rel("t1", "f", "K2", "d", "Id", active=False),
    ]
    result = topo.classify_template_topology("t1", nodes, edges)
    assert result["bidirectional_count"] == 1
    assert result["inactive_count"] == 1


def test_classify_detects_role_playing_dim():
    """Same dim joined twice via different FK columns."""
    nodes = [_node("t1", "f"), _node("t1", "d_calendar")]
    edges = [
        _rel("t1", "f", "OrderDate", "d_calendar", "Date"),
        _rel("t1", "f", "ShipDate", "d_calendar", "Date"),
    ]
    result = topo.classify_template_topology("t1", nodes, edges)
    assert result["role_playing_dims"] == [
        {"from_table": "f", "to_table": "d_calendar", "from_cols": ["OrderDate", "ShipDate"]}
    ]


def test_classify_detects_calendar_dim():
    nodes = [_node("t1", "f"), _node("t1", "Calendar")]
    edges = [_rel("t1", "f", "DateKey", "Calendar", "Date")]
    result = topo.classify_template_topology("t1", nodes, edges)
    assert result["has_calendar_dim"] is True


def test_build_topology_atlas_aggregates_across_templates():
    nodes = [
        _node("t1", "f"),
        _node("t1", "d_calendar"),
        _node("t2", "f"),
        _node("t2", "d_region"),
    ]
    edges = [
        _rel("t1", "f", "K", "d_calendar", "Date"),
        _rel("t2", "f", "K", "d_region", "Id"),
    ]
    atlas = topo.build_topology_atlas(nodes, edges)
    assert atlas["template_count"] == 2
    assert "t1" in atlas["per_template"]
    assert "t2" in atlas["per_template"]
    # Cross-template summary fields
    assert "summary" in atlas
    assert atlas["summary"]["templates_with_calendar_dim"] >= 1


# ---------- corpus integration ----------


@pytest.mark.skipif(
    not (KG / "nodes_datamodel.jsonl").exists() or not (KG / "edges_datamodel.jsonl").exists(),
    reason="zebra_kg datamodel artifacts not present",
)
def test_build_topology_atlas_clusters_real_corpus():
    import json

    nodes = [json.loads(l) for l in (KG / "nodes_datamodel.jsonl").read_text().splitlines() if l]
    edges = [json.loads(l) for l in (KG / "edges_datamodel.jsonl").read_text().splitlines() if l]
    atlas = topo.build_topology_atlas(nodes, edges)
    # 20 Zebra templates expected
    assert atlas["template_count"] >= 15  # lenient — some templates may have no rels
    # Some templates should have a calendar dim
    assert atlas["summary"]["templates_with_calendar_dim"] >= 5
