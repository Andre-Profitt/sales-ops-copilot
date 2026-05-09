"""Tests for scripts.sales.rw_zebra_kg_query — read-only query CLI."""

from __future__ import annotations

import json

import pytest

from scripts.sales import rw_zebra_kg_query as q


@pytest.fixture
def kg_dir(tmp_path):
    nodes = [
        {
            "id": "msr:t1:Sales AC",
            "type": "Measure",
            "name": "Sales AC",
            "table": "f",
            "scenario": "AC",
            "is_variance": False,
            "template": "t1",
        },
        {
            "id": "msr:t1:Sales PY",
            "type": "Measure",
            "name": "Sales PY",
            "table": "f",
            "scenario": "PY",
            "is_variance": False,
            "template": "t1",
        },
        {
            "id": "msr:t1:Sales vs PY",
            "type": "Measure",
            "name": "Sales vs PY",
            "table": "f",
            "scenario": "AC",
            "is_variance": True,
            "template": "t1",
        },
        {"id": "tbl:t1:f", "type": "Table", "name": "f", "template": "t1"},
        {"id": "scn:PY", "type": "Scenario", "code": "PY"},
    ]
    edges = [
        {"src": "msr:t1:Sales vs PY", "dst": "msr:t1:Sales AC", "type": "depends_on", "props": {}},
        {"src": "msr:t1:Sales vs PY", "dst": "msr:t1:Sales PY", "type": "depends_on", "props": {}},
    ]
    (tmp_path / "nodes_datamodel.jsonl").write_text("\n".join(json.dumps(n) for n in nodes) + "\n")
    (tmp_path / "edges_datamodel.jsonl").write_text("\n".join(json.dumps(e) for e in edges) + "\n")
    (tmp_path / "style_tokens.json").write_text(
        json.dumps(
            [
                {
                    "kind": "color",
                    "value": "#000000",
                    "purpose": "ac",
                    "usage_count": 100,
                    "canonical": True,
                },
                {
                    "kind": "color",
                    "value": "#FF6600",
                    "purpose": "highlight",
                    "usage_count": 5,
                    "canonical": False,
                },
            ]
        )
    )
    return tmp_path


def test_load_nodes_returns_all_rows(kg_dir):
    nodes = q.load_nodes(kg_dir)
    assert len(nodes) == 5


def test_filter_measures_where_is_variance_true(kg_dir):
    rows = q.filter_measures(q.load_nodes(kg_dir), is_variance=True)
    names = {r["name"] for r in rows}
    assert names == {"Sales vs PY"}


def test_canonical_tokens_only(kg_dir):
    rows = q.filter_tokens(q.load_tokens(kg_dir), canonical_only=True)
    assert len(rows) == 1
    assert rows[0]["value"] == "#000000"
