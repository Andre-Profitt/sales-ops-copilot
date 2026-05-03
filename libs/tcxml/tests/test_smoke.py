"""Smoke test: load schema, parse a real think-cellXML blob from the corpus."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tcxml import load_schema, parse_thinkcell_xml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CORPUS = (
    _REPO_ROOT / "state" / "thinkcell_bridge" / "thinkcellxml_corpus" / "20260502-071725"
)


def _schema_path() -> Path:
    override = os.environ.get("TCXML_SCHEMA")
    return Path(override) if override else _DEFAULT_CORPUS / "schema_inventory.json"


def _fixture_dir() -> Path:
    override = os.environ.get("TCXML_FIXTURE_DIR")
    return Path(override) if override else _DEFAULT_CORPUS / "by_deck"


def _pick_xml() -> Path:
    fixture_dir = _fixture_dir()
    candidates = sorted(fixture_dir.rglob("*think-cellXML.xml"))
    if not candidates:
        pytest.skip(f"no think-cellXML fixtures under {fixture_dir}")
    for p in candidates:
        if p.stat().st_size > 5_000:
            return p
    return candidates[0]


def test_schema_loads():
    schema = load_schema(_schema_path())
    assert len(schema.elements) >= 300
    assert "CSmartGrid" in schema.chart_classes
    assert "val" in schema.attributes
    assert 28224 in schema.build_versions


def test_parse_real_chart():
    schema = load_schema(_schema_path())
    xml_bytes = _pick_xml().read_bytes()
    chart = parse_thinkcell_xml(xml_bytes, schema)
    assert chart.root.tag == "root"
    assert chart.reqver is not None
    assert len(chart.elements) > 0
    schema_tags = set(schema.elements) | set(schema.chart_classes)
    seen = {e.tag for e in chart.elements}
    assert seen & schema_tags, "expected some recognised tags"


def test_missing_schema_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_schema(tmp_path / "does-not-exist.json")
