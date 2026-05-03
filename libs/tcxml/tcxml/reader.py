"""Parse think-cellXML bytes into a typed tree, validated against the schema."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

from lxml import etree

from tcxml.schema import Schema


@dataclass(slots=True)
class ParsedElement:
    tag: str
    attrib: dict[str, str]
    text: str | None
    children: list["ParsedElement"] = field(default_factory=list)


@dataclass(slots=True)
class ParsedChart:
    reqver: str | None
    version: str | None
    root: ParsedElement
    elements: list[ParsedElement]
    unknown_tags: set[str]
    unknown_attrs: set[str]


def parse_thinkcell_xml(xml_bytes: bytes, schema: Schema) -> ParsedChart:
    """Parse a `think-cellXML` blob; warn (don't crash) on tags/attrs absent from schema."""
    parser = etree.XMLParser(huge_tree=True, recover=False)
    tree = etree.fromstring(xml_bytes, parser=parser)

    unknown_tags: set[str] = set()
    unknown_attrs: set[str] = set()
    elements: list[ParsedElement] = []

    def walk(node: etree._Element) -> ParsedElement:
        tag = etree.QName(node).localname
        if not schema.has_element(tag):
            unknown_tags.add(tag)
        attrib: dict[str, str] = {}
        for k, v in node.attrib.items():
            local = etree.QName(k).localname if k.startswith("{") else k
            if not schema.has_attribute(local):
                unknown_attrs.add(local)
            attrib[local] = v
        parsed = ParsedElement(
            tag=tag,
            attrib=attrib,
            text=node.text,
            children=[walk(c) for c in node],
        )
        elements.append(parsed)
        return parsed

    root = walk(tree)

    if unknown_tags:
        warnings.warn(
            f"think-cellXML contained {len(unknown_tags)} unknown elements: "
            f"{sorted(unknown_tags)[:8]}{'...' if len(unknown_tags) > 8 else ''}",
            stacklevel=2,
        )
    if unknown_attrs:
        warnings.warn(
            f"think-cellXML contained {len(unknown_attrs)} unknown attributes: "
            f"{sorted(unknown_attrs)[:8]}{'...' if len(unknown_attrs) > 8 else ''}",
            stacklevel=2,
        )

    return ParsedChart(
        reqver=root.attrib.get("reqver"),
        version=_first_version(root),
        root=root,
        elements=elements,
        unknown_tags=unknown_tags,
        unknown_attrs=unknown_attrs,
    )


def _first_version(root: ParsedElement) -> str | None:
    for child in root.children:
        if child.tag == "version":
            return child.attrib.get("val")
    return None
