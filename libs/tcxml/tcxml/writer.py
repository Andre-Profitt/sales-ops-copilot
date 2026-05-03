"""Serialize a ParsedChart back to think-cellXML bytes.

The grammar that real think-cell emits (observed empirically in the corpus):

* Single-line UTF-8, prologue `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`.
* No XML namespaces. Plain unprefixed elements / attributes throughout.
* Empty elements written self-closing (`<foo/>`); elements with children or text
  use explicit start/end tags.
* Attribute names are mixed-case Hungarian (`m_bstrShapeName`, `reqver`,
  `idref`, ...). Schema observation order is preserved when known so the output
  is byte-stable across runs; unknown attributes fall back to alphabetical.
* `reqver`/`endver` may appear on individual elements (per-element version
  gating); they are serialized like any other attribute.

This module does NOT attempt byte-equality with think-cell's own emitter.
The contract is *semantic equivalence*: re-parsing the output yields a
ParsedChart with the same root tag, reqver, element multiset, and id/idref
graph. See `tests/test_roundtrip.py`.
"""

from __future__ import annotations

from lxml import etree

from tcxml.reader import ParsedChart, ParsedElement
from tcxml.schema import Schema

_XML_DECLARATION = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def serialize_thinkcell_xml(parsed: ParsedChart, schema: Schema) -> bytes:
    """Emit `parsed` as think-cellXML bytes parseable by `parse_thinkcell_xml`.

    Output matches think-cell's observed grammar: no namespaces, single-line,
    self-closing empties, deterministic attribute order. Re-parsing the result
    against `schema` produces a logically equivalent `ParsedChart`.
    """
    attr_order = _attribute_order_index(schema)
    root_el = _to_lxml(parsed.root, attr_order)
    body = etree.tostring(root_el, encoding="utf-8", xml_declaration=False)
    return _XML_DECLARATION + body


def _attribute_order_index(schema: Schema) -> dict[str, int]:
    """Map attribute name -> position in `schema.attributes` (insertion order)."""
    return {name: idx for idx, name in enumerate(schema.attributes)}


def _to_lxml(node: ParsedElement, attr_order: dict[str, int]) -> etree._Element:
    """Convert a ParsedElement subtree to an lxml Element with stable attr order."""
    el = etree.Element(node.tag, attrib=_ordered_attrib(node.attrib, attr_order))
    if node.text is not None and node.text != "":
        el.text = node.text
    for child in node.children:
        el.append(_to_lxml(child, attr_order))
    return el


def _ordered_attrib(attrib: dict[str, str], attr_order: dict[str, int]) -> dict[str, str]:
    """Return attrib reordered: schema order first (when known), then alphabetical.

    lxml preserves insertion order in the dict passed to `Element(attrib=...)`,
    so this directly controls emit order. `_UNKNOWN` puts unschema'd attrs after
    all schema'd ones; within each group ties are broken alphabetically for
    determinism.
    """
    _UNKNOWN = len(attr_order)

    def sort_key(item: tuple[str, str]) -> tuple[int, str]:
        name, _ = item
        return (attr_order.get(name, _UNKNOWN), name)

    return dict(sorted(attrib.items(), key=sort_key))
