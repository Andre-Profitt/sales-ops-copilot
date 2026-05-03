"""Round-trip: parse think-cellXML -> serialize -> re-parse, assert equivalence."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tcxml import (
    load_schema,
    pack_thinkcell_stream,
    parse_thinkcell_xml,
    serialize_thinkcell_xml,
)
from tcxml.reader import ParsedElement

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


def _seed_xml() -> Path:
    seed_dir = _fixture_dir() / "LAND_thinkcell_seed"
    candidates = sorted(seed_dir.glob("ole_*_think-cellXML.xml"))
    if not candidates:
        candidates = sorted(_fixture_dir().rglob("*think-cellXML.xml"))
    if not candidates:
        pytest.skip(f"no think-cellXML fixtures under {_fixture_dir()}")
    return candidates[0]


def _collect_idrefs(node: ParsedElement, sink: set[str]) -> None:
    if "idref" in node.attrib:
        sink.add(node.attrib["idref"])
    for c in node.children:
        _collect_idrefs(c, sink)


def test_serialize_starts_with_declaration():
    schema = load_schema(_schema_path())
    chart = parse_thinkcell_xml(_seed_xml().read_bytes(), schema)
    out = serialize_thinkcell_xml(chart, schema)
    assert out.startswith(b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
    # No XML namespaces leaked into the body.
    assert b"xmlns" not in out


def test_roundtrip_semantic_equivalence():
    """Parse -> serialize -> re-parse yields a logically equivalent ParsedChart."""
    schema = load_schema(_schema_path())
    original_bytes = _seed_xml().read_bytes()
    original = parse_thinkcell_xml(original_bytes, schema)

    serialized = serialize_thinkcell_xml(original, schema)
    reparsed = parse_thinkcell_xml(serialized, schema)

    # Same root tag.
    assert reparsed.root.tag == original.root.tag
    # Same reqver gate.
    assert reparsed.reqver == original.reqver
    # Same nested <version val=...>.
    assert reparsed.version == original.version

    # Same multiset of element tags (every tag occurrence preserved).
    orig_tags = sorted(e.tag for e in original.elements)
    new_tags = sorted(e.tag for e in reparsed.elements)
    assert new_tags == orig_tags

    # Same set of declared ids.
    orig_ids = {e.attrib["id"] for e in original.elements if "id" in e.attrib}
    new_ids = {e.attrib["id"] for e in reparsed.elements if "id" in e.attrib}
    assert new_ids == orig_ids

    # Same set of idref targets used.
    orig_refs: set[str] = set()
    new_refs: set[str] = set()
    _collect_idrefs(original.root, orig_refs)
    _collect_idrefs(reparsed.root, new_refs)
    assert new_refs == orig_refs

    # Element count preserved exactly.
    assert len(reparsed.elements) == len(original.elements)


def test_serialize_is_deterministic():
    """Two serialization passes of the same parsed chart produce identical bytes."""
    schema = load_schema(_schema_path())
    chart = parse_thinkcell_xml(_seed_xml().read_bytes(), schema)
    a = serialize_thinkcell_xml(chart, schema)
    b = serialize_thinkcell_xml(chart, schema)
    assert a == b


def test_pack_thinkcell_stream_is_not_implemented():
    """CFB writing is honestly stubbed; assert the stub raises rather than fakes success."""
    with pytest.raises(NotImplementedError) as exc_info:
        pack_thinkcell_stream(b"<root/>", None)
    # The error message should point at the actual blocker, not be a generic stub.
    msg = str(exc_info.value)
    assert "CFB" in msg
    assert "olefile" in msg or "MS-CFB" in msg
