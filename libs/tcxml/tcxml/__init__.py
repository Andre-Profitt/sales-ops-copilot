"""Reader and writer for think-cell's embedded chart XML (CFB-wrapped) in .pptx decks."""

from tcxml.cfb import extract_thinkcell_streams, pack_thinkcell_stream
from tcxml.reader import ParsedChart, ParsedElement, parse_thinkcell_xml
from tcxml.schema import Attribute, ChartClass, Element, Schema, load_schema
from tcxml.writer import serialize_thinkcell_xml

__all__ = [
    "Attribute",
    "ChartClass",
    "Element",
    "ParsedChart",
    "ParsedElement",
    "Schema",
    "extract_thinkcell_streams",
    "load_schema",
    "pack_thinkcell_stream",
    "parse_thinkcell_xml",
    "serialize_thinkcell_xml",
]
